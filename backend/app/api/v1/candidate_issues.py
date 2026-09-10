import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from data.dbconnection.session import get_db
from app.models.candidate_issues import CandidateIssue
from app.models.issue_status import IssueStatus
from app.models.analysis_run import AnalysisRun
from app.repositories.candidate_issue_repo import candidate_issue_repository
from app.repositories.issue_status_repo import issue_status_repository
from app.schemas.candidate_issues import (
    CandidateIssueLabelUpdate,
    CandidateIssueListResponse,
    CandidateIssueResponse,
    DatasetStatsResponse,
    DuplicateIssuesResponse,
    ReviewBatchItem,
    ReviewBatchRequest,
    ReviewBatchResponse,
    SourceContextLine,
    SourceContextResponse,
    VerifiedDatasetResponse,
    VerifiedTrainingRecord,
)
from app.services.ast_generator import ast_generator
from app.services.candidate_issue_service import candidate_issue_service
from app.services.dataset_preparation.sampler import ReviewSampler
from app.services.source_context import get_structured_source_context


router = APIRouter(
    prefix="/candidate-issues",
    tags=["Candidate Issues"]
)


# =========================================================================
# 1. CANDIDATE ISSUES CRUD & FILTERING
# =========================================================================

@router.get("", response_model=CandidateIssueListResponse)
@router.get("/", response_model=CandidateIssueListResponse)
async def list_candidate_issues(
    analysis_run_id: Optional[str] = Query(None, description="Filter by Analysis Run ID"),
    repository_id: Optional[str] = Query(None, description="Filter by Repository ID"),
    language: Optional[str] = Query(None, description="Filter by programming language"),
    rule_id: Optional[str] = Query(None, description="Filter by rule ID"),
    severity: Optional[str] = Query(None, description="Filter by detector severity"),
    verification_status: Optional[str] = Query(None, description="Filter by verification state: unverified, partial, verified, false_positive, all"),
    verified_only: bool = Query(False, description="Only return fully verified issues"),
    limit: int = Query(100, ge=1, le=1000, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    db: AsyncSession = Depends(get_db),
):
    """
    List candidate issues from PostgreSQL with optional filtering and pagination.
    """
    # If repository_id is provided without analysis_run_id, resolve latest run id
    target_run_id = analysis_run_id
    if repository_id and not target_run_id:
        from sqlalchemy import select
        run_stmt = (
            select(AnalysisRun.id)
            .where(AnalysisRun.repository_id == repository_id)
            .order_by(AnalysisRun.created_at.desc())
            .limit(1)
        )
        res = await db.execute(run_stmt)
        target_run_id = res.scalar_one_or_none()
        if not target_run_id:
            return CandidateIssueListResponse(total=0, items=[])

    items, total = await candidate_issue_repository.list_issues(
        db=db,
        analysis_run_id=target_run_id,
        language=language,
        rule_id=rule_id,
        verification_status=verification_status,
        verified_only=verified_only,
        limit=limit,
        offset=offset,
    )

    if severity:
        items = [i for i in items if (i.severity or "").lower() == severity.lower()]
        total = len(items)

    serialized = [CandidateIssueResponse.model_validate(i) for i in items]
    return CandidateIssueListResponse(total=total, items=serialized)


@router.get("/dataset/stats", response_model=DatasetStatsResponse)
async def get_dataset_statistics(
    db: AsyncSession = Depends(get_db),
):
    """
    Get global ground-truth verification progress and distribution metrics.
    """
    stats = await candidate_issue_repository.get_dataset_stats(db)
    return DatasetStatsResponse(**stats)


@router.get("/dataset/verified", response_model=VerifiedDatasetResponse)
async def get_verified_training_dataset(
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve all fully-verified candidate issues formatted for ML model training.
    """
    records = await candidate_issue_repository.get_verified_training_dataset(db)
    serialized = [VerifiedTrainingRecord.model_validate(r) for r in records]
    return VerifiedDatasetResponse(total=len(serialized), records=serialized)


@router.get("/dataset/readiness")
async def get_dataset_readiness(
    db: AsyncSession = Depends(get_db),
):
    """
    Evaluate dataset readiness against PostgreSQL verified records for ML training.
    """
    from app.services.dataset_preparation.service import DatasetPreparationService
    service = DatasetPreparationService()
    return await service.evaluate_readiness(db)


@router.post("/dataset/prepare")
async def prepare_dataset(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    """
    Execute the full dataset preparation pipeline from PostgreSQL verified records.
    """
    from app.services.dataset_preparation.service import DatasetPreparationService
    service = DatasetPreparationService()
    return await service.prepare_dataset(
        db=db,
        dataset_version=payload.get("dataset_version", "dataset_v1"),
        random_seed=payload.get("random_seed", 42),
        train_ratio=payload.get("train_ratio", 0.70),
        validation_ratio=payload.get("validation_ratio", 0.15),
        test_ratio=payload.get("test_ratio", 0.15),
        min_samples_per_class=payload.get("min_samples_per_class", 1),
        exclude_test_synthetic=payload.get("exclude_test_synthetic", True),
        export_dir=payload.get("export_dir"),
        overwrite=payload.get("overwrite", False),
    )


@router.get("/dataset/metadata/{dataset_version}")
async def get_dataset_metadata(
    dataset_version: str,
    export_dir: Optional[str] = Query(None),
):
    """
    Retrieve saved dataset metadata.json for a prepared dataset version.
    """
    from app.services.dataset_preparation.service import DatasetPreparationService
    service = DatasetPreparationService()
    meta = service.get_dataset_metadata(dataset_version, custom_dir=export_dir)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Metadata for dataset version '{dataset_version}' not found.")
    return meta


@router.get("/dataset/quality-report/{dataset_version}")
async def get_dataset_quality_report(
    dataset_version: str,
    export_dir: Optional[str] = Query(None),
):
    """
    Retrieve saved dataset quality_report.json for a prepared dataset version.
    """
    from app.services.dataset_preparation.service import DatasetPreparationService
    service = DatasetPreparationService()
    report = service.get_dataset_quality_report(dataset_version, custom_dir=export_dir)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Quality report for dataset version '{dataset_version}' not found.")
    return report


@router.get("/duplicates", response_model=DuplicateIssuesResponse)
async def get_duplicate_issues(
    db: AsyncSession = Depends(get_db),
):
    """
    Identify duplicate candidate issue clusters sharing the same file, line, and rule signature.
    """
    dups_data = await candidate_issue_repository.get_potential_duplicates(db)
    return DuplicateIssuesResponse(**dups_data)


@router.post("/review/batch", response_model=ReviewBatchResponse)
async def generate_review_batch(
    payload: ReviewBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a deterministic, diverse 200-item candidate issue review batch.
    """
    records = await candidate_issue_repository.get_all_unverified_issues_with_repo(db)
    sampler = ReviewSampler(random_seed=payload.random_seed)
    sampled_records, report = sampler.sample(
        records=records,
        target_size=payload.target_size,
        max_per_rule_per_repo=payload.max_per_rule_per_repo,
    )

    items = [ReviewBatchItem(**rec) for rec in sampled_records]
    return ReviewBatchResponse(
        total_available_unverified_real=report["total_available_unverified_real"],
        sampled_count=report["sampled_count"],
        seed=report["seed"],
        strata_count=report["strata_count"],
        repositories_distribution=report["repositories_distribution"],
        languages_distribution=report["languages_distribution"],
        rules_distribution=report["rules_distribution"],
        issue_types_distribution=report["issue_types_distribution"],
        items=items,
    )


@router.get("/{issue_id}", response_model=CandidateIssueResponse)
async def get_candidate_issue(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a single candidate issue by ID.
    """
    issue = await candidate_issue_repository.get_by_id(db, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail=f"Candidate issue '{issue_id}' not found.")
    return CandidateIssueResponse.model_validate(issue)


@router.get("/{issue_id}/context", response_model=SourceContextResponse)
async def get_candidate_issue_context(
    issue_id: str,
    context_lines: int = Query(15, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve surrounding source code context for a candidate issue.
    """
    issue = await candidate_issue_repository.get_by_id(db, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail=f"Candidate issue '{issue_id}' not found.")

    ctx = get_structured_source_context(
        file_path=issue.file_path,
        line_number=issue.line_number,
        context_lines=context_lines,
    )

    lines = [SourceContextLine(**l) for l in ctx.get("lines", [])]
    return SourceContextResponse(
        issue_id=issue.id,
        found=ctx.get("found", False),
        message=ctx.get("message", ""),
        formatted_text=ctx.get("formatted_text", ""),
        file_path=ctx.get("file_path", issue.file_path),
        line_number=ctx.get("line_number", issue.line_number),
        start_line=ctx.get("start_line"),
        end_line=ctx.get("end_line"),
        total_lines=ctx.get("total_lines"),
        lines=lines,
    )


@router.patch("/{issue_id}/labels", response_model=CandidateIssueResponse)
async def update_candidate_issue_labels(
    issue_id: str,
    payload: CandidateIssueLabelUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update human ground-truth verification labels for a candidate issue.
    Preserves original detector severity.
    """
    updated = await candidate_issue_repository.update_labels(
        db=db,
        issue_id=issue_id,
        verified_severity=payload.verified_severity,
        verified_priority=payload.verified_priority,
        verification_notes=payload.verification_notes,
        is_false_positive=payload.is_false_positive,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Candidate issue '{issue_id}' not found.")
    return CandidateIssueResponse.model_validate(updated)


@router.patch("/{issue_id}/status")
@router.patch("/{issue_id}/resolve")
async def update_candidate_issue_status(
    issue_id: str,
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    """
    Toggle or update the issue status (e.g. Open / Resolved / In Progress).
    Persists resolution to the PostgreSQL issue_statuses table.
    """
    issue = await candidate_issue_repository.get_by_id(db, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail=f"Candidate issue '{issue_id}' not found.")

    next_status = (payload.get("status") or "Resolved").lower()

    # Retrieve or create IssueStatus
    status_record = await issue_status_repository.get_by_candidate_issue_id(db, issue_id)
    if status_record:
        status_record.status = next_status
    else:
        status_record = IssueStatus(
            id=str(uuid4()),
            candidate_issue_id=issue_id,
            status=next_status,
        )
        db.add(status_record)

    await db.commit()
    await db.refresh(status_record)

    return {
        "id": issue_id,
        "status": status_record.status.capitalize(),
    }


@router.patch("/{issue_id}/notes")
async def update_candidate_issue_notes(
    issue_id: str,
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    """
    Update engineer remediation remarks and notes for a candidate issue.
    Persists to PostgreSQL candidate_issues.verification_notes.
    """
    issue = await candidate_issue_repository.get_by_id(db, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail=f"Candidate issue '{issue_id}' not found.")

    remarks = payload.get("remarks") or payload.get("engineerNotes") or payload.get("verification_notes") or ""

    issue.verification_notes = remarks

    await db.commit()
    await db.refresh(issue)

    return {
        "id": issue_id,
        "remarks": remarks,
        "engineerNotes": remarks,
        "verification_notes": issue.verification_notes,
    }


@router.patch("/{issue_id}/severity")
async def update_candidate_issue_severity(
    issue_id: str,
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    """
    Update candidate issue severity (High / Medium / Low).
    Persists to PostgreSQL candidate_issues.severity.
    """
    issue = await candidate_issue_repository.get_by_id(db, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail=f"Candidate issue '{issue_id}' not found.")

    raw_severity = (payload.get("severity") or "").lower().strip()
    if raw_severity not in ("high", "medium", "low"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid severity '{raw_severity}'. Must be one of: 'high', 'medium', 'low'.",
        )

    issue.severity = raw_severity
    await db.commit()
    await db.refresh(issue)

    return {
        "id": issue_id,
        "severity": issue.severity.capitalize(),
    }


# =========================================================================
# 2. PIPELINE ANALYSIS, ENRICHMENT & EXPORT
# =========================================================================

@router.post("/analyze")
async def analyze_candidate_issues(
    repository_path: str
):
    """
    Generate candidate issues for a repository.
    """
    path = Path(repository_path)

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Repository path not found: {repository_path}"
        )

    if not path.is_dir():
        raise HTTPException(
            status_code=400,
            detail="Provided path is not a directory"
        )

    try:
        ast_result = await asyncio.to_thread(
            ast_generator.generate_ast_for_repository,
            repository_path
        )

        result = await asyncio.to_thread(
            candidate_issue_service.generate_from_repository,
            ast_result
        )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.post("/reports")
async def generate_candidate_issue_reports(
    repository_path: str,
    repository_id: str | None = None,
):
    """
    Generate complete enriched bug reports for a repository.
    """
    from app.services.bug_report_service import bug_report_service

    path = Path(repository_path)

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Repository path not found: {repository_path}"
        )

    if not path.is_dir():
        raise HTTPException(
            status_code=400,
            detail="Provided path is not a directory"
        )

    try:
        ast_result = await asyncio.to_thread(
            ast_generator.generate_ast_for_repository,
            repository_path
        )

        candidate_result = await asyncio.to_thread(
            candidate_issue_service.generate_from_repository,
            ast_result
        )

        reports_data = await asyncio.to_thread(
            bug_report_service.generate_repository_reports,
            ast_result,
            candidate_result,
            repository_id,
            repository_path,
        )

        return reports_data

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {str(e)}"
        )


@router.post("/enrich")
async def enrich_candidate_issues(
    issues: list[dict],
    repository_id: str | None = None,
    repository_path: str | None = None,
):
    """
    Enrich an arbitrary list of candidate issue dictionaries into complete bug reports.
    """
    from app.services.bug_report_service import bug_report_service

    try:
        reports = await asyncio.to_thread(
            bug_report_service.generate_reports_from_candidate_issues,
            issues,
            None,
            repository_id,
            repository_path,
        )
        return {
            "total_reports": len(reports),
            "bug_reports": [r.model_dump(mode="json") for r in reports],
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Enrichment failed: {str(e)}"
        )


@router.get("/export")
async def export_candidate_issue_reports(
    repository_path: str,
    format: str = "pdf",
    repository_id: str | None = None,
):
    """
    Generate and download bug reports for a repository in various formats:
    Supported formats: pdf, csv, json, md, html
    """
    from app.services.bug_report_service import bug_report_service

    path = Path(repository_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Repository path not found: {repository_path}")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="Provided path is not a directory")

    try:
        ast_result = await asyncio.to_thread(
            ast_generator.generate_ast_for_repository,
            repository_path
        )
        candidate_result = await asyncio.to_thread(
            candidate_issue_service.generate_from_repository,
            ast_result
        )
        reports_data = await asyncio.to_thread(
            bug_report_service.generate_repository_reports,
            ast_result,
            candidate_result,
            repository_id,
            repository_path,
        )

        content, media_type, filename = bug_report_service.export_reports(
            reports=reports_data.get("bug_reports", []),
            format_type=format,
            summary_stats=reports_data.get("summary_stats"),
            repo_info={"id": repository_id, "path": repository_path, "name": path.name},
        )

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        }
        return Response(content=content, media_type=media_type, headers=headers)

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.post("/export")
async def export_custom_bug_reports(
    reports: list[dict],
    format: str = "pdf",
    repository_name: str | None = None,
):
    """
    Download given bug reports payload in various formats:
    Supported formats: pdf, csv, json, md, html
    """
    from app.services.report_exporter import report_exporter

    try:
        content, media_type, filename = report_exporter.export(
            reports=reports,
            format_type=format,
            summary_stats=None,
            repo_info={"name": repository_name or "bug_report"},
        )
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        }
        return Response(content=content, media_type=media_type, headers=headers)

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
