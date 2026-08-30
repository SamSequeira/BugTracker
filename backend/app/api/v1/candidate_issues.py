import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.services.ast_generator import ast_generator
from app.services.candidate_issue_service import (
    candidate_issue_service
)


router = APIRouter(
    prefix="/candidate-issues",
    tags=["Candidate Issues"]
)


@router.post("/analyze")
async def analyze_candidate_issues(
    repository_path: str
):
    """
    Generate candidate issues for a repository.

    Pipeline:

    Repository
        ↓
    AST Generation
        ↓
    Static Analysis
        ↓
    Candidate Issue Generation
    """

    path = Path(repository_path)

    # -----------------------------------------
    # Validate repository path
    # -----------------------------------------

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

        # -----------------------------------------
        # STEP 1: Generate AST
        # -----------------------------------------

        ast_result = await asyncio.to_thread(
            ast_generator.generate_ast_for_repository,
            repository_path
        )

        # -----------------------------------------
        # STEP 2: Candidate Issue Generation
        # -----------------------------------------

        result = await asyncio.to_thread(
            candidate_issue_service
            .generate_from_repository,
            ast_result
        )

        # -----------------------------------------
        # STEP 3: Return result
        # -----------------------------------------

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

    Pipeline:
    Repository -> AST -> Static Analysis -> Candidate Issues -> Classification -> Enrichment -> Complete Bug Reports
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
    from fastapi.responses import Response
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
    from fastapi.responses import Response
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
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.candidate_issue_repo import candidate_issue_repository
from app.schemas.candidate_issues import (
    CandidateIssueLabelUpdate,
    CandidateIssueListResponse,
    CandidateIssueResponse,
    DatasetPrepareRequest,
    DatasetPrepareResponse,
    DatasetReadinessResponse,
    DatasetStatsResponse,
    DuplicateIssuesResponse,
    ReviewBatchItem,   
    ReviewBatchRequest,
    ReviewBatchResponse,
    SourceContextLine,
    SourceContextResponse,
    VerifiedDatasetResponse,
    VerifiedTrainingRecord,
    VerificationStatusFilter,
)
from app.services.ast_generator import ast_generator
from app.services.candidate_issue_service import candidate_issue_service
from app.services.dataset_preparation import ReviewSampler, dataset_preparation_service
from app.services.source_context import get_structured_source_context
from data.dbconnection.session import get_db


router = APIRouter(
    prefix="/candidate-issues",
    tags=["Candidate Issues"]
)


# ===========================================================================
# STATIC ROUTES (MUST BE DECLARED BEFORE PARAMETERIZED /{issue_id} ROUTES)
# ===========================================================================

@router.post(
    "/review/batch",
    response_model=ReviewBatchResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_review_batch(
    payload: ReviewBatchRequest = ReviewBatchRequest(),
    db: AsyncSession = Depends(get_db),
) -> ReviewBatchResponse:
    """
    Generate a deterministic, balanced review batch of REAL_USABLE candidate issues
    for human-in-the-loop verification across languages, repositories, and rules.
    """
    all_unverified = await candidate_issue_repository.get_all_unverified_issues_with_repo(db)
    sampler = ReviewSampler(random_seed=payload.random_seed)
    sampled_items, report = sampler.sample(
        records=all_unverified,
        target_size=payload.target_size,
        max_per_rule_per_repo=payload.max_per_rule_per_repo,
    )
    return ReviewBatchResponse(
        total_available_unverified_real=report["total_available_unverified_real"],
        sampled_count=report["sampled_count"],
        seed=report["seed"],
        strata_count=report["strata_count"],
        repositories_distribution=report["repositories_distribution"],
        languages_distribution=report["languages_distribution"],
        rules_distribution=report["rules_distribution"],
        issue_types_distribution=report["issue_types_distribution"],
        items=[ReviewBatchItem(**item) for item in sampled_items],
    )


@router.get(
    "/dataset/readiness",
    response_model=DatasetReadinessResponse,
    status_code=status.HTTP_200_OK,
)
async def get_dataset_readiness_scorecard(
    db: AsyncSession = Depends(get_db),
) -> DatasetReadinessResponse:
    """
    Evaluate dataset readiness against strict DistilBERT training prerequisites:
    - Usable unique sample volume (>= 150)
    - Repository and language diversity
    - Class balance & cross-tab diversity
    - Missingness and test/synthetic contamination
    - Group isolation and zero leakage
    """
    result = await dataset_preparation_service.evaluate_readiness(db)
    return DatasetReadinessResponse(**result)


@router.get(
    "/dataset/stats",
    response_model=DatasetStatsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_dataset_statistics(
    db: AsyncSession = Depends(get_db),
) -> DatasetStatsResponse:
    """
    Calculate progress metrics for ground-truth dataset collection.
    - Total candidate issues
    - Unverified count
    - Partially verified count
    - Fully verified count
    - Category distributions for fully verified records (critical/high/medium/low and p1/p2/p3/p4)
    - Provenance breakdown and diversity counts
    """
    stats = await candidate_issue_repository.get_dataset_stats(db)
    return DatasetStatsResponse(**stats)


@router.post("/analyze")
async def analyze_candidate_issues(
    repository_path: str
):
    """
    Generate candidate issues for a repository.

    Pipeline:
    Repository -> AST Generation -> Static Analysis -> Candidate Issue Generation
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
    from fastapi.responses import Response
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
    from fastapi.responses import Response
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




# ===========================================================================
# POTENTIAL DUPLICATES CHECK ENDPOINT
# ===========================================================================

@router.get(
    "/duplicates",
    response_model=DuplicateIssuesResponse,
    status_code=status.HTTP_200_OK,
)
async def get_duplicate_candidate_issues(
    analysis_run_id: Optional[str] = Query(default=None, description="Optional analysis run ID filter"),
    limit: int = Query(default=50, ge=1, le=500, description="Max duplicate groups to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
) -> DuplicateIssuesResponse:
    """
    Identify potential duplicate candidate issues sharing identical signatures:
    (rule_id, file_path, line_number, code_snippet).
    Returns clusters for manual review without modifying or deleting records.
    """
    data = await candidate_issue_repository.get_potential_duplicates(
        db, analysis_run_id=analysis_run_id, limit=limit, offset=offset
    )
    return DuplicateIssuesResponse(
        total_duplicate_groups=data["total_duplicate_groups"],
        total_duplicate_issues=data["total_duplicate_issues"],
        groups=[
            {
                "rule_id": g["rule_id"],
                "file_path": g["file_path"],
                "line_number": g["line_number"],
                "code_snippet": g["code_snippet"],
                "count": g["count"],
                "issue_ids": g["issue_ids"],
                "issues": [CandidateIssueResponse.model_validate(i) for i in g["issues"]],
            }
            for g in data["groups"]
        ],
    )


# ===========================================================================
# DATASET PREPARATION & EXPORT ENDPOINTS
# ===========================================================================

@router.post(
    "/dataset/prepare",
    response_model=DatasetPrepareResponse,
    status_code=status.HTTP_200_OK,
)
async def prepare_training_dataset(
    request: DatasetPrepareRequest,
    db: AsyncSession = Depends(get_db),
) -> DatasetPrepareResponse:
    """
    Prepare a high-quality, reproducible DistilBERT dataset from verified PostgreSQL records:
    - Validates data quality, missingness, and label classes
    - Removes exact duplicate records from the ML export without modifying PostgreSQL
    - Builds structured text context with zero target label leakage
    - Performs group-aware stratified train/val/test splitting with zero cross-split leakage
    - Exports train.jsonl, validation.jsonl, test.jsonl, metadata.json, quality_report.json
    """
    try:
        result = await dataset_preparation_service.prepare_dataset(
            db=db,
            dataset_version=request.dataset_version,
            random_seed=request.random_seed,
            train_ratio=request.train_ratio,
            validation_ratio=request.validation_ratio,
            test_ratio=request.test_ratio,
            min_samples_per_class=request.min_samples_per_class,
            export_dir=request.export_dir,
            overwrite=request.overwrite,
        )
        return DatasetPrepareResponse(**result)
    except FileExistsError as fe:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(fe),
        ) from fe
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dataset preparation failed: {str(e)}",
        ) from e


@router.get(
    "/dataset/prepared/{dataset_version}/metadata",
    status_code=status.HTTP_200_OK,
)
async def get_prepared_dataset_metadata(
    dataset_version: str,
) -> dict:
    """Retrieve metadata.json for a prepared dataset version."""
    meta = dataset_preparation_service.get_dataset_metadata(dataset_version)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metadata for dataset version '{dataset_version}' not found",
        )
    return meta


@router.get(
    "/dataset/prepared/{dataset_version}/quality-report",
    status_code=status.HTTP_200_OK,
)
async def get_prepared_dataset_quality_report(
    dataset_version: str,
) -> dict:
    """Retrieve quality_report.json for a prepared dataset version."""
    report = dataset_preparation_service.get_dataset_quality_report(dataset_version)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quality report for dataset version '{dataset_version}' not found",
        )
    return report


# ===========================================================================
# VERIFIED DATASET RETRIEVAL (STATIC ROUTES)
# ===========================================================================

@router.get(
    "/dataset/verified",
    response_model=VerifiedDatasetResponse,
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/verified",
    response_model=VerifiedDatasetResponse,
    status_code=status.HTTP_200_OK,
)
async def get_verified_dataset(
    limit: Optional[int] = Query(default=None, ge=1, le=10000, description="Max records to return"),
    offset: int = Query(default=0, ge=0, description="Records offset for pagination"),
    db: AsyncSession = Depends(get_db),
) -> VerifiedDatasetResponse:
    """
    Retrieve ONLY fully verified candidate issues where BOTH verified_severity AND
    verified_priority are non-null.

    Explicitly formatted for DistilBERT training:
      - 'severity' = verified_severity (ground truth target)
      - 'priority' = verified_priority (ground truth target)
      - 'detector_severity' = original static analyzer prediction (for evaluation/comparison)
    """
    records = await candidate_issue_repository.get_verified_training_dataset(
        db, limit=limit, offset=offset
    )
    return VerifiedDatasetResponse(
        total=len(records),
        records=[VerifiedTrainingRecord(**r) for r in records],
    )


# ===========================================================================
# CANDIDATE ISSUES COLLECTION ROUTE
# ===========================================================================

@router.get(
    "",
    response_model=CandidateIssueListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_candidate_issues(
    analysis_run_id: Optional[str] = Query(default=None, description="Filter by analysis run ID"),
    language: Optional[str] = Query(default=None, description="Filter by language"),
    rule_id: Optional[str] = Query(default=None, description="Filter by rule ID"),
    verification_status: Optional[VerificationStatusFilter] = Query(
        default=None,
        description="Filter by verification state: unverified, partial, verified, all"
    ),
    verified_only: bool = Query(default=False, description="Filter to only fully verified issues"),
    limit: int = Query(default=50, ge=1, le=500, description="Page limit"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    db: AsyncSession = Depends(get_db),
) -> CandidateIssueListResponse:
    """
    List candidate issues with review queue status filtering and pagination.
    """
    items, total = await candidate_issue_repository.list_issues(
        db=db,
        analysis_run_id=analysis_run_id,
        language=language,
        rule_id=rule_id,
        verification_status=verification_status,
        verified_only=verified_only,
        limit=limit,
        offset=offset,
    )
    return CandidateIssueListResponse(
        total=total,
        items=[CandidateIssueResponse.model_validate(item) for item in items],
    )


# ===========================================================================
# PARAMETERIZED ROUTES (DECLARED AFTER STATIC ROUTES)
# ===========================================================================

@router.get(
    "/{issue_id}",
    response_model=CandidateIssueResponse,
    status_code=status.HTTP_200_OK,
)
async def get_candidate_issue(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
) -> CandidateIssueResponse:
    """
    Retrieve a single candidate issue by ID, showing both detector predictions and verified labels.
    """
    issue = await candidate_issue_repository.get_by_id(db, issue_id)
    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate issue '{issue_id}' not found",
        )
    return CandidateIssueResponse.model_validate(issue)


@router.post(
    "/{issue_id}/labels",
    response_model=CandidateIssueResponse,
    status_code=status.HTTP_200_OK,
)
@router.put(
    "/{issue_id}/labels",
    response_model=CandidateIssueResponse,
    status_code=status.HTTP_200_OK,
)
@router.patch(
    "/{issue_id}/labels",
    response_model=CandidateIssueResponse,
    status_code=status.HTTP_200_OK,
)
async def update_candidate_issue_labels(
    issue_id: str,
    payload: CandidateIssueLabelUpdate,
    db: AsyncSession = Depends(get_db),
) -> CandidateIssueResponse:
    """
    Manually assign or update verified ground-truth labels for a candidate issue.
    Supports partial updates (only severity, only priority, or both).

    - Does NOT modify or overwrite the original detector severity.
    - Rejects invalid values via Pydantic & database check constraints.
    - Sets verified_at timestamp upon label assignment.
    """
    # Check issue exists
    existing = await candidate_issue_repository.get_by_id(db, issue_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate issue '{issue_id}' not found",
        )

    updated = await candidate_issue_repository.update_labels(
        db=db,
        issue_id=issue_id,
        verified_severity=payload.verified_severity,
        verified_priority=payload.verified_priority,
        verification_notes=payload.verification_notes,
        is_false_positive=payload.is_false_positive,
    )

    return CandidateIssueResponse.model_validate(updated)


@router.get(
    "/{issue_id}/context",
    response_model=SourceContextResponse,
    status_code=status.HTTP_200_OK,
)
async def get_candidate_issue_context(
    issue_id: str,
    context_lines: int = Query(default=15, ge=1, le=50, description="Lines of context before and after"),
    db: AsyncSession = Depends(get_db),
) -> SourceContextResponse:
    """
    Safely retrieve source code context around a candidate issue's flagged line.
    Returns 10-20 surrounding lines with the flagged line identified.
    Does not modify database state or throw unhandled exceptions if the source snapshot is absent.
    """
    issue = await candidate_issue_repository.get_by_id(db, issue_id)
    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate issue '{issue_id}' not found",
        )

    res = get_structured_source_context(
        file_path=issue.file_path,
        line_number=issue.line_number,
        context_lines=context_lines,
    )

    return SourceContextResponse(
        issue_id=issue_id,
        found=res["found"],
        message=res["message"],
        formatted_text=res["formatted_text"],
        file_path=res["file_path"],
        line_number=res["line_number"],
        start_line=res.get("start_line"),
        end_line=res.get("end_line"),
        total_lines=res.get("total_lines"),
        lines=[SourceContextLine(**l) for l in res.get("lines", [])],
    )