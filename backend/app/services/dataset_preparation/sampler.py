"""
sampler.py — Deterministic Review Sampling Strategy for Ground-Truth Dataset Construction.
==========================================================================================
Selects a balanced, diverse subset of unverified REAL_USABLE candidate issues across
languages, repositories, rules, issue types, and file locations for human review.
"""
from __future__ import annotations

from collections import defaultdict
import random
from typing import Any, Dict, List, Optional, Tuple

from .validator import classify_provenance


class ReviewSampler:
    """
    Deterministically samples candidate issues for human-in-the-loop review.
    Maximizes cross-language, cross-repository, and cross-rule diversity while
    capping over-represented rule clusters.
    """

    def __init__(self, random_seed: int = 42) -> None:
        self.random_seed = random_seed

    def sample(
        self,
        records: List[Dict[str, Any]],
        target_size: int = 200,
        max_per_rule_per_repo: int = 25,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Deterministically sample `target_size` unverified REAL_USABLE issues.

        Parameters
        ----------
        records : List of candidate issue dictionaries from DB
        target_size : Target total number of review candidates (default: 200)
        max_per_rule_per_repo : Maximum items to select from any single (repo, rule) stratum

        Returns
        -------
        Tuple of (sampled_records, sampling_report)
        """
        rng = random.Random(self.random_seed)

        # 1. Filter to unverified REAL_USABLE records
        unverified_real: List[Dict[str, Any]] = []
        for rec in records:
            # Exclude already verified or false positive records
            if rec.get("verified_severity") is not None or rec.get("verified_priority") is not None:
                continue
            if rec.get("verified_at") is not None:
                continue

            # Must be classified as REAL_USABLE
            prov = classify_provenance(rec)
            if prov == "REAL_USABLE":
                unverified_real.append(rec)

        if not unverified_real:
            return [], {
                "total_available_unverified_real": 0,
                "sampled_count": 0,
                "seed": self.random_seed,
                "repositories_distribution": {},
                "languages_distribution": {},
                "rules_distribution": {},
                "issue_types_distribution": {},
                "strata_count": 0,
            }

        # 2. Group into strata: (language, repository_name/id, rule_id)
        strata: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
        for rec in unverified_real:
            lang = rec.get("language") or "Unknown"
            repo = rec.get("repository_name") or rec.get("repository_id") or "Unknown"
            rule = rec.get("rule_id") or "UNKNOWN_RULE"
            strata[(lang, repo, rule)].append(rec)

        # 3. Sort each stratum by (confidence_weight, file_path, line_number, id)
        # Prioritize HIGH > MEDIUM > LOW confidence records within each stratum
        conf_weights = {"high": 0, "medium": 1, "low": 2}
        for key in strata:
            strata[key].sort(
                key=lambda x: (
                    conf_weights.get(str(x.get("confidence") or x.get("evidence", {}).get("confidence", "medium")).lower(), 1),
                    str(x.get("file_path")),
                    int(x.get("line_number") or 0),
                    str(x.get("id")),
                )
            )

        # 4. Multi-pass balanced round-robin allocation across strata
        sampled: List[Dict[str, Any]] = []
        strata_keys = sorted(list(strata.keys()))
        rng.shuffle(strata_keys)

        strata_indices = {key: 0 for key in strata_keys}
        strata_counts = {key: 0 for key in strata_keys}

        # Pass 1: Guarantee at least min(len(items), 3) from each stratum without exceeding target_size
        for key in strata_keys:
            if len(sampled) >= target_size:
                break
            items = strata[key]
            initial_pick = min(len(items), 3, max_per_rule_per_repo)
            for _ in range(initial_pick):
                if len(sampled) >= target_size:
                    break
                idx = strata_indices[key]
                sampled.append(items[idx])
                strata_indices[key] += 1
                strata_counts[key] += 1

        # Pass 2: Round-robin until target_size is reached or all caps hit
        made_progress = True
        while len(sampled) < target_size and made_progress:
            made_progress = False
            for key in strata_keys:
                if len(sampled) >= target_size:
                    break
                items = strata[key]
                idx = strata_indices[key]
                if idx < len(items) and strata_counts[key] < max_per_rule_per_repo:
                    sampled.append(items[idx])
                    strata_indices[key] += 1
                    strata_counts[key] += 1
                    made_progress = True

        # Pass 3: If still under target_size, relax cap
        if len(sampled) < target_size:
            for key in strata_keys:
                if len(sampled) >= target_size:
                    break
                items = strata[key]
                while strata_indices[key] < len(items) and len(sampled) < target_size:
                    idx = strata_indices[key]
                    sampled.append(items[idx])
                    strata_indices[key] += 1

        # 5. Compute sampling distribution metrics
        repo_dist: Dict[str, int] = defaultdict(int)
        lang_dist: Dict[str, int] = defaultdict(int)
        rule_dist: Dict[str, int] = defaultdict(int)
        type_dist: Dict[str, int] = defaultdict(int)
        conf_dist: Dict[str, int] = defaultdict(int)

        for rec in sampled:
            repo_dist[rec.get("repository_name") or rec.get("repository_id") or "Unknown"] += 1
            lang_dist[rec.get("language") or "Unknown"] += 1
            rule_dist[rec.get("rule_id") or "UNKNOWN"] += 1
            type_dist[rec.get("issue_type") or "UNKNOWN"] += 1
            conf = str(rec.get("confidence") or rec.get("evidence", {}).get("confidence", "medium")).lower()
            conf_dist[conf] += 1

        report = {
            "total_available_unverified_real": len(unverified_real),
            "sampled_count": len(sampled),
            "seed": self.random_seed,
            "strata_count": len(strata_keys),
            "repositories_distribution": dict(repo_dist),
            "languages_distribution": dict(lang_dist),
            "rules_distribution": dict(rule_dist),
            "issue_types_distribution": dict(type_dist),
            "confidence_distribution": dict(conf_dist),
        }

        return sampled, report

