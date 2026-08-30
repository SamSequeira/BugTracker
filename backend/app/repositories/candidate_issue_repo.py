"""
candidate_issue_repo.py
------------------------
Data Access Layer (DAL) repository for CandidateIssue entity.
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate_issues import CandidateIssue


class CandidateIssueRepository:
    """Encapsulates database access queries for CandidateIssue ORM model."""

    async def create_bulk(
        self,
        db: AsyncSession,
        issues: List[CandidateIssue],
    ) -> List[CandidateIssue]:
        """
        Add a list of CandidateIssue ORM instances to the session and flush/commit.
        """
        if not issues:
            return []

        db.add_all(issues)
        await db.flush()
        return issues

    async def get_by_id(
        self,
        db: AsyncSession,
        issue_id: str,
    ) -> Optional[CandidateIssue]:
        """Retrieve a CandidateIssue by its primary key ID."""
        return await db.get(CandidateIssue, issue_id)

    async def list_by_analysis_run_id(
        self,
        db: AsyncSession,
        analysis_run_id: str,
    ) -> List[CandidateIssue]:
        """Retrieve all CandidateIssues associated with a specific analysis run."""
        stmt = (
            select(CandidateIssue)
            .where(CandidateIssue.analysis_run_id == analysis_run_id)
            .order_by(CandidateIssue.created_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


candidate_issue_repository = CandidateIssueRepository()

"""
candidate_issue_repo.py
------------------------
Data Access Layer (DAL) repository for CandidateIssue entity.
Supports review queue filtering by verification state, progress statistics,
and potential duplicate cluster detection without destructive operations.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_run import AnalysisRun
from app.models.candidate_issues import CandidateIssue
from app.models.repository import Repository


class CandidateIssueRepository:
    """Encapsulates database access queries for CandidateIssue ORM model."""

    async def create(
        self,
        db: AsyncSession,
        issue: CandidateIssue,
    ) -> CandidateIssue:
        """Add a single CandidateIssue ORM instance to the session and flush."""
        db.add(issue)
        await db.flush()
        return issue

    async def create_bulk(
        self,
        db: AsyncSession,
        issues: List[CandidateIssue],
    ) -> List[CandidateIssue]:
        """
        Add a list of CandidateIssue ORM instances to the session and flush.
        Preserves caller transaction boundaries (no internal commit).
        """
        if not issues:
            return []

        db.add_all(issues)
        await db.flush()
        return issues

    async def get_by_id(
        self,
        db: AsyncSession,
        issue_id: str,
    ) -> Optional[CandidateIssue]:
        """Retrieve a CandidateIssue by its primary key ID."""
        return await db.get(CandidateIssue, issue_id)

    async def list_by_analysis_run_id(
        self,
        db: AsyncSession,
        analysis_run_id: str,
    ) -> List[CandidateIssue]:
        """Retrieve all CandidateIssues associated with a specific analysis run."""
        stmt = (
            select(CandidateIssue)
            .where(CandidateIssue.analysis_run_id == analysis_run_id)
            .order_by(CandidateIssue.created_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_issues(
        self,
        db: AsyncSession,
        analysis_run_id: Optional[str] = None,
        language: Optional[str] = None,
        rule_id: Optional[str] = None,
        verification_status: Optional[str] = None,
        verified_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[CandidateIssue], int]:
        """
        List CandidateIssues with optional filters and pagination.
        Supports verification_status: 'unverified', 'partial', 'verified', 'false_positive', 'all'.
        Returns a tuple of (items, total_count).
        """
        base_query = select(CandidateIssue)
        count_query = select(func.count(CandidateIssue.id))

        filters = []

        if analysis_run_id:
            filters.append(CandidateIssue.analysis_run_id == analysis_run_id)

        if language:
            filters.append(CandidateIssue.language == language)

        if rule_id:
            filters.append(CandidateIssue.rule_id == rule_id)

        # Handle verification_status filter
        status_filter = verification_status.lower() if verification_status else None
        if status_filter == "unverified":
            filters.append(
                and_(
                    CandidateIssue.verified_severity.is_(None),
                    CandidateIssue.verified_priority.is_(None),
                    CandidateIssue.verified_at.is_(None),
                )
            )
        elif status_filter == "false_positive":
            filters.append(
                and_(
                    CandidateIssue.verified_severity.is_(None),
                    CandidateIssue.verified_priority.is_(None),
                    CandidateIssue.verified_at.is_not(None),
                )
            )
        elif status_filter == "partial":
            filters.append(
                or_(
                    and_(
                        CandidateIssue.verified_severity.is_not(None),
                        CandidateIssue.verified_priority.is_(None),
                    ),
                    and_(
                        CandidateIssue.verified_severity.is_(None),
                        CandidateIssue.verified_priority.is_not(None),
                    ),
                )
            )
        elif status_filter == "verified" or verified_only:
            filters.append(
                and_(
                    CandidateIssue.verified_severity.is_not(None),
                    CandidateIssue.verified_priority.is_not(None),
                )
            )

        if filters:
            base_query = base_query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # Count total matching records
        total = (await db.execute(count_query)).scalar_one()

        # Query paginated records
        items_query = (
            base_query
            .order_by(CandidateIssue.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list((await db.execute(items_query)).scalars().all())

        return items, total

    async def update_labels(
        self,
        db: AsyncSession,
        issue_id: str,
        verified_severity: Optional[str] = None,
        verified_priority: Optional[str] = None,
        verification_notes: Optional[str] = None,
        is_false_positive: Optional[bool] = None,
    ) -> Optional[CandidateIssue]:
        """
        Update manual verified labels for a candidate issue.
        Does NOT modify the original detector severity.
        If is_false_positive is True, clears verified labels and marks verified_at timestamp with notes.
        """
        issue = await db.get(CandidateIssue, issue_id)
        if not issue:
            return None

        if is_false_positive:
            issue.verified_severity = None
            issue.verified_priority = None
            notes = verification_notes or "Marked as false positive by reviewer."
            if not notes.startswith("[FALSE_POSITIVE]"):
                notes = f"[FALSE_POSITIVE] {notes}"
            issue.verification_notes = notes
        else:
            if verified_severity is not None:
                issue.verified_severity = verified_severity
            if verified_priority is not None:
                issue.verified_priority = verified_priority
            if verification_notes is not None:
                issue.verification_notes = verification_notes

        issue.verified_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(issue)
        return issue

    async def get_all_unverified_issues_with_repo(
        self,
        db: AsyncSession,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all unverified candidate issues joined with AnalysisRun and Repository.
        """
        stmt = (
            select(
                CandidateIssue,
                AnalysisRun.repository_id,
                Repository.name.label("repository_name"),
            )
            .outerjoin(AnalysisRun, CandidateIssue.analysis_run_id == AnalysisRun.id)
            .outerjoin(Repository, AnalysisRun.repository_id == Repository.id)
            .where(
                CandidateIssue.verified_severity.is_(None),
                CandidateIssue.verified_priority.is_(None),
                CandidateIssue.verified_at.is_(None),
            )
            .order_by(CandidateIssue.created_at.asc())
        )
        result = await db.execute(stmt)
        rows = result.all()

        records = []
        for issue, repo_id, repo_name in rows:
            records.append({
                "id": issue.id,
                "analysis_run_id": issue.analysis_run_id,
                "repository_id": repo_id or "",
                "repository_name": repo_name or "",
                "title": issue.title,
                "description": issue.description,
                "file_path": issue.file_path,
                "line_number": issue.line_number,
                "column": issue.column,
                "rule_id": issue.rule_id or "",
                "issue_type": issue.issue_type or "",
                "message": issue.message or issue.description or "",
                "code_snippet": issue.code_snippet or "",
                "evidence": issue.evidence or {},
                "language": issue.language or "Unknown",
                "severity": issue.severity,
                "urgency": issue.urgency,
                "verified_severity": issue.verified_severity,
                "verified_priority": issue.verified_priority,
                "verified_at": issue.verified_at,
                "verification_notes": issue.verification_notes,
                "created_at": issue.created_at,
            })
        return records

    async def get_verified_training_dataset(
        self,
        db: AsyncSession,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve ONLY fully verified candidate issues where BOTH verified_severity AND
        verified_priority are non-null.

        Mapping:
          - 'severity' -> verified_severity (manually verified ground truth)
          - 'priority' -> verified_priority (manually verified ground truth)
          - 'detector_severity' -> severity (original static analyzer prediction)
          - 'repository_id' -> joined from AnalysisRun
        """
        stmt = (
            select(CandidateIssue, AnalysisRun.repository_id)
            .outerjoin(AnalysisRun, CandidateIssue.analysis_run_id == AnalysisRun.id)
            .where(
                CandidateIssue.verified_severity.is_not(None),
                CandidateIssue.verified_priority.is_not(None),
            )
            .order_by(CandidateIssue.created_at.asc())
        )

        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        rows = result.all()

        records: List[Dict[str, Any]] = []
        for issue, repo_id in rows:
            records.append({
                "id": issue.id,
                "analysis_run_id": issue.analysis_run_id,
                "repository_id": repo_id or "",
                "language": issue.language or "Unknown",
                "rule_id": issue.rule_id or "",
                "issue_type": issue.issue_type or "",
                "message": issue.message or issue.description or "",
                "file_path": issue.file_path,
                "line_number": issue.line_number,
                "column": issue.column,
                "code_snippet": issue.code_snippet or "",
                "evidence": issue.evidence or {},
                # Original static analyzer prediction preserved for evaluation/comparison
                "detector_severity": issue.severity,
                # Ground-truth targets for ML model training
                "severity": issue.verified_severity,
                "priority": issue.verified_priority,
                "verified_at": issue.verified_at,
                "verification_notes": issue.verification_notes,
            })

        return records

    async def get_dataset_stats(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Calculate dataset labeling progress and category distributions.
        Severity and priority distributions count ONLY fully verified records.
        """
        # Overall status counts
        total_stmt = select(func.count(CandidateIssue.id))
        total_count = (await db.execute(total_stmt)).scalar_one()

        unverified_cond = and_(
            CandidateIssue.verified_severity.is_(None),
            CandidateIssue.verified_priority.is_(None),
            CandidateIssue.verified_at.is_(None),
        )
        unverified_stmt = select(func.count(CandidateIssue.id)).where(unverified_cond)
        unverified_count = (await db.execute(unverified_stmt)).scalar_one()

        false_positive_cond = and_(
            CandidateIssue.verified_severity.is_(None),
            CandidateIssue.verified_priority.is_(None),
            CandidateIssue.verified_at.is_not(None),
        )
        false_positive_stmt = select(func.count(CandidateIssue.id)).where(false_positive_cond)
        false_positive_count = (await db.execute(false_positive_stmt)).scalar_one()

        partially_verified_cond = or_(
            and_(
                CandidateIssue.verified_severity.is_not(None),
                CandidateIssue.verified_priority.is_(None),
            ),
            and_(
                CandidateIssue.verified_severity.is_(None),
                CandidateIssue.verified_priority.is_not(None),
            ),
        )
        partially_verified_stmt = select(func.count(CandidateIssue.id)).where(partially_verified_cond)
        partially_verified_count = (await db.execute(partially_verified_stmt)).scalar_one()

        fully_verified_cond = and_(
            CandidateIssue.verified_severity.is_not(None),
            CandidateIssue.verified_priority.is_not(None),
        )
        fully_verified_stmt = select(func.count(CandidateIssue.id)).where(fully_verified_cond)
        fully_verified_count = (await db.execute(fully_verified_stmt)).scalar_one()

        # Severity distribution for fully verified records
        sev_dist_stmt = (
            select(CandidateIssue.verified_severity, func.count(CandidateIssue.id))
            .where(fully_verified_cond)
            .group_by(CandidateIssue.verified_severity)
        )
        sev_rows = (await db.execute(sev_dist_stmt)).all()
        sev_dist = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for sev, count in sev_rows:
            if sev in sev_dist:
                sev_dist[sev] = count

        # Priority distribution for fully verified records
        prio_dist_stmt = (
            select(CandidateIssue.verified_priority, func.count(CandidateIssue.id))
            .where(fully_verified_cond)
            .group_by(CandidateIssue.verified_priority)
        )
        prio_rows = (await db.execute(prio_dist_stmt)).all()
        prio_dist = {"p1": 0, "p2": 0, "p3": 0, "p4": 0}
        for prio, count in prio_rows:
            if prio in prio_dist:
                prio_dist[prio] = count

        # Diversity counts across fully verified records
        div_stmt = select(
            func.count(func.distinct(CandidateIssue.rule_id)),
            func.count(func.distinct(CandidateIssue.language)),
            func.count(func.distinct(CandidateIssue.file_path)),
            func.count(func.distinct(CandidateIssue.code_snippet)),
            func.count(func.distinct(CandidateIssue.analysis_run_id)),
            func.count(func.distinct(AnalysisRun.repository_id)),
        ).outerjoin(AnalysisRun, CandidateIssue.analysis_run_id == AnalysisRun.id).where(fully_verified_cond)
        div_row = (await db.execute(div_stmt)).one()

        diversity_counts = {
            "unique_rules": div_row[0],
            "unique_languages": div_row[1],
            "unique_file_paths": div_row[2],
            "unique_code_snippets": div_row[3],
            "unique_analysis_runs": div_row[4],
            "unique_repositories": div_row[5],
        }

        # Provenance breakdown for fully verified records
        incomplete_stmt = select(func.count(CandidateIssue.id)).where(
            and_(
                fully_verified_cond,
                or_(
                    CandidateIssue.code_snippet.is_(None),
                    CandidateIssue.code_snippet == "",
                    CandidateIssue.rule_id.is_(None),
                    CandidateIssue.rule_id == "",
                ),
            )
        )
        incomplete_count = (await db.execute(incomplete_stmt)).scalar_one()

        provenance_breakdown = {
            "real_usable": max(0, fully_verified_count - incomplete_count),
            "real_incomplete": incomplete_count,
        }

        # Cross-tab distribution (Severity x Priority) for fully verified records
        crosstab_stmt = (
            select(
                CandidateIssue.verified_severity,
                CandidateIssue.verified_priority,
                func.count(CandidateIssue.id),
            )
            .where(fully_verified_cond)
            .group_by(CandidateIssue.verified_severity, CandidateIssue.verified_priority)
        )
        crosstab_rows = (await db.execute(crosstab_stmt)).all()
        crosstab = {}
        for s in ["critical", "high", "medium", "low"]:
            for p in ["p1", "p2", "p3", "p4"]:
                crosstab[f"{s} + {p}"] = 0
        for s, p, count in crosstab_rows:
            if s and p:
                crosstab[f"{s.lower()} + {p.lower()}"] = count

        readiness_summary = {
            "is_ready_for_training": fully_verified_count >= 150 and incomplete_count == 0,
            "target_threshold": 150,
            "current_usable": max(0, fully_verified_count - incomplete_count),
        }

        return {
            "total_candidate_issues": total_count,
            "unverified": unverified_count,
            "false_positives": false_positive_count,
            "partially_verified": partially_verified_count,
            "fully_verified": fully_verified_count,
            "severity_distribution": sev_dist,
            "priority_distribution": prio_dist,
            "crosstab": crosstab,
            "provenance_breakdown": provenance_breakdown,
            "diversity_counts": diversity_counts,
            "readiness_summary": readiness_summary,
        }

    async def get_potential_duplicates(
        self,
        db: AsyncSession,
        analysis_run_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Identify clusters of candidate issues sharing identical signatures:
        (rule_id, file_path, line_number, code_snippet) with count > 1.
        Does NOT modify or delete records.
        """
        # Find signatures having duplicates
        dup_subq = (
            select(
                CandidateIssue.rule_id,
                CandidateIssue.file_path,
                CandidateIssue.line_number,
                CandidateIssue.code_snippet,
                func.count(CandidateIssue.id).label("match_count"),
            )
            .group_by(
                CandidateIssue.rule_id,
                CandidateIssue.file_path,
                CandidateIssue.line_number,
                CandidateIssue.code_snippet,
            )
            .having(func.count(CandidateIssue.id) > 1)
        )

        if analysis_run_id:
            dup_subq = dup_subq.where(CandidateIssue.analysis_run_id == analysis_run_id)

        dup_subq_alias = dup_subq.subquery()

        # Count total duplicate groups
        total_groups_stmt = select(func.count()).select_from(dup_subq_alias)
        total_groups = (await db.execute(total_groups_stmt)).scalar_one()

        # Paginate signature groups
        paged_groups_stmt = (
            select(dup_subq_alias)
            .order_by(dup_subq_alias.c.match_count.desc())
            .offset(offset)
            .limit(limit)
        )
        group_rows = (await db.execute(paged_groups_stmt)).all()

        groups: List[Dict[str, Any]] = []
        total_duplicate_issues = 0

        for r in group_rows:
            rule_id, file_path, line_number, code_snippet, count = (
                r.rule_id,
                r.file_path,
                r.line_number,
                r.code_snippet,
                r.match_count,
            )
            total_duplicate_issues += count

            # Fetch member issues for this cluster
            issues_stmt = select(CandidateIssue).where(
                CandidateIssue.rule_id == rule_id,
                CandidateIssue.file_path == file_path,
                CandidateIssue.line_number == line_number,
                CandidateIssue.code_snippet == code_snippet,
            )
            if analysis_run_id:
                issues_stmt = issues_stmt.where(CandidateIssue.analysis_run_id == analysis_run_id)

            cluster_issues = list((await db.execute(issues_stmt)).scalars().all())

            groups.append({
                "rule_id": rule_id,
                "file_path": file_path,
                "line_number": line_number,
                "code_snippet": code_snippet,
                "count": count,
                "issue_ids": [i.id for i in cluster_issues],
                "issues": cluster_issues,
            })

        return {
            "total_duplicate_groups": total_groups,
            "total_duplicate_issues": total_duplicate_issues,
            "groups": groups,
        }


candidate_issue_repository = CandidateIssueRepository()
