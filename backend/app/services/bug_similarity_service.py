"""Persistent duplicate and similar bug detection for static-analysis issues.

The duplicate threshold defaults to 0.85.  It is intentionally configurable via
``BUG_SIMILARITY_THRESHOLD`` and must be calibrated against real issue examples
before it is treated as a final product decision.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

from app.services.static_analyzer.models import CandidateIssue


DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_COLLECTION_NAME = "candidate_issues"
DEFAULT_THRESHOLD = 0.85
DEFAULT_PERSIST_DIR = "./data/chroma"


logger = logging.getLogger(__name__)


class BugSimilarityService:
    """Stores CandidateIssue embeddings and finds cosine-similar issues."""

    def __init__(
        self,
        persist_dir: str | Path | None = None,
        threshold: float | None = None,
        model: Any | None = None,
        client: Any | None = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        self.persist_dir = Path(
            persist_dir or os.getenv("CHROMA_PERSIST_DIR", DEFAULT_PERSIST_DIR)
        )
        self.threshold = (
            float(os.getenv("BUG_SIMILARITY_THRESHOLD", str(DEFAULT_THRESHOLD)))
            if threshold is None
            else threshold
        )
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("BUG_SIMILARITY_THRESHOLD must be between 0 and 1.")

        self._model = model
        self._client = client or chromadb.PersistentClient(path=str(self.persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def model(self) -> Any:
        """Load MiniLM only when the service is actually used."""
        if self._model is None:
            self._model = SentenceTransformer(DEFAULT_MODEL_NAME)
        return self._model

    @staticmethod
    def issue_id(issue: CandidateIssue, repository_id: str) -> str:
        """Return a stable Chroma ID for one issue at one repository location."""
        stable_parts = (
            repository_id,
            issue.rule_id,
            issue.file_path,
            str(issue.line_number),
            issue.issue_type,
            issue.message,
        )
        value = "\x1f".join(stable_parts).encode("utf-8")
        return hashlib.sha256(value).hexdigest()

    @staticmethod
    def build_issue_text(issue: CandidateIssue) -> str:
        """Build a normalized semantic representation without object repr output."""
        fields = (
            ("rule", issue.rule_id),
            ("type", issue.issue_type),
            ("severity", issue.severity),
            ("message", issue.message),
            ("code", issue.code_snippet),
        )
        return "\n".join(
            f"{name}: {BugSimilarityService._normalize_text(value)}"
            for name, value in fields
            if value
        )

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    def store_issue(self, issue: CandidateIssue, repository_id: str) -> str:
        """Upsert an issue so re-analysis updates, rather than duplicates, its vector."""
        issue_id = self.issue_id(issue, repository_id)
        text = self.build_issue_text(issue)
        self._collection.upsert(
            ids=[issue_id],
            embeddings=[self._embedding(text)],
            documents=[text],
            metadatas=[self._metadata(issue, repository_id)],
        )
        return issue_id

    def find_similar_issues(
        self,
        issue: CandidateIssue,
        repository_id: str,
        top_k: int = 5,
        exclude_issue_id: str | None = None,
    ) -> dict[str, Any]:
        """Find the most similar stored issues, optionally excluding one ID.

        Chroma cosine collections return *cosine distance* (``1 - cosine
        similarity``), not a percentage.  Scores below are therefore converted
        with ``similarity = 1 - distance`` and clamped to [0, 1].
        """
        if top_k < 1:
            raise ValueError("top_k must be at least 1.")

        count = self._collection.count()
        if count == 0:
            return self._result(False, 0.0, [])

        query_count = min(count, top_k + (1 if exclude_issue_id else 0))
        result = self._collection.query(
            query_embeddings=[self._embedding(self.build_issue_text(issue))],
            n_results=query_count,
            include=["metadatas", "distances"],
        )

        matches = []
        ids = result.get("ids", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for stored_id, metadata, distance in zip(ids, metadatas, distances):
            if stored_id == exclude_issue_id:
                continue
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            matches.append(self._match(stored_id, metadata, similarity))
            if len(matches) == top_k:
                break

        highest_similarity = matches[0]["similarity"] if matches else 0.0
        return self._result(highest_similarity >= self.threshold, highest_similarity, matches)

    def add_and_find(self, issue: CandidateIssue, repository_id: str, top_k: int = 5) -> dict[str, Any]:
        """Find prior matches, then persist the issue without self-matching."""
        try:
            issue_id = self.issue_id(issue, repository_id)
            result = self.find_similar_issues(
                issue, repository_id, top_k=top_k, exclude_issue_id=issue_id
            )
            self.store_issue(issue, repository_id)
            return self.safe_result(result)
        except Exception:  # noqa: BLE001 - static findings must remain available
            logger.warning(
                "Similarity processing failed for repository=%s rule=%s file=%s line=%s",
                repository_id,
                issue.rule_id,
                issue.file_path,
                issue.line_number,
                exc_info=True,
            )
            return self.unavailable_result()

    def _embedding(self, text: str) -> list[float]:
        try:
            embedding = self.model.encode(text, normalize_embeddings=True)
            values = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
            return [float(value) for value in values]
        except Exception:
            logger.exception("MiniLM embedding generation failed")
            raise

    @staticmethod
    def unavailable_result() -> dict[str, Any]:
        """Return the stable, public result for an unavailable similarity backend."""
        return {
            "available": False,
            "duplicate": False,
            "similarity": 0.0,
            "similar_bugs": [],
            "error": "Similarity processing unavailable.",
        }

    @staticmethod
    def _result(
        duplicate: bool, similarity: float, similar_bugs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "duplicate": bool(duplicate),
            "similarity": float(similarity),
            "similar_bugs": similar_bugs,
        }

    @staticmethod
    def _match(stored_id: Any, metadata: Any, similarity: float) -> dict[str, Any]:
        """Copy only explicitly supported scalar fields out of a Chroma result."""
        metadata = metadata if isinstance(metadata, dict) else {}
        return {
            "issue_id": str(stored_id),
            "repository_id": str(metadata.get("repository_id", "")),
            "similarity": float(similarity),
            "issue_type": str(metadata.get("issue_type", "")),
            "message": str(metadata.get("message", "")),
            "file_path": str(metadata.get("file_path", "")),
            "line_number": int(metadata.get("line_number", 0)),
        }

    @classmethod
    def safe_result(cls, result: Any) -> dict[str, Any]:
        """Canonicalize a similarity result before it is attached to an API response.

        This intentionally copies only the public scalar fields instead of walking
        arbitrary objects returned by dependencies.  It prevents Chroma/model
        objects (or cyclic objects) from reaching FastAPI/Pydantic serialization.
        """
        if not isinstance(result, dict):
            return cls.unavailable_result()
        try:
            matches = result.get("similar_bugs", [])
            if not isinstance(matches, list):
                raise TypeError("similar_bugs must be a list")
            if any(match is result for match in matches):
                raise ValueError("similar_bugs contains a circular result reference")
            safe_matches = [
                cls._match(
                    match.get("issue_id", "") if isinstance(match, dict) else "",
                    match,
                    float(match.get("similarity", 0.0)) if isinstance(match, dict) else 0.0,
                )
                for match in matches
                if isinstance(match, dict)
            ]
            return cls._result(
                bool(result.get("duplicate", False)),
                float(result.get("similarity", 0.0)),
                safe_matches,
            )
        except (TypeError, ValueError, OverflowError):
            logger.warning("Discarding malformed similarity result", exc_info=True)
            return cls.unavailable_result()

    @staticmethod
    def _metadata(issue: CandidateIssue, repository_id: str) -> dict[str, str | int]:
        """Return Chroma-compatible primitive metadata only."""
        return {
            "repository_id": repository_id,
            "rule_id": issue.rule_id,
            "issue_type": issue.issue_type,
            "file_path": issue.file_path,
            "line_number": issue.line_number,
            "severity": issue.severity,
            "message": issue.message,
        }
