from datetime import datetime, timezone
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import tempfile
import os

logger = logging.getLogger(__name__)

from app.schemas.repository import (
    RepositoryCloneRequest,
    RepositoryCloneResponse,
    RepositoryResponse,
)
from app.schemas.analysis_response import AnalyzeRepositoryResponse
from app.services.repository_service import repository_service
from app.services.repository_analysis_service import repository_analysis_service
from app.services.s3_service import S3UploadError
from app.utils.git import GitCloneError
from app.models.analysis_run import AnalysisRun
from app.models.repository import Repository
from app.repositories.repository_repo import repository_repository
from data.dbconnection.session import get_db, AsyncSessionLocal

from app.services.repository_upload_service import (
    RepositoryUploadError,
    repository_upload_service,
)
from sqlalchemy import select
from app.repositories.architecture_component_repo import architecture_component_repository
from app.repositories.architecture_summary_repo import architecture_summary_repository
from app.repositories.source_file_repo import source_file_repository
from app.repositories.technology_repo import technology_repository
from app.schemas.architecture import (
    ArchitectureComponentSchema,
    ArchitectureSummarySchema,
    ArchitectureTopologyResponse,
    SourceFileSchema,
    TechnologySchema,
)


router = APIRouter(
    prefix="/repositories",
    tags=["Repositories"],
)


# ============================================================
# SHARED BACKGROUND ANALYSIS HELPER
# Called automatically after every clone or upload so that
# architecture data is always persisted without blocking the
# clone/upload HTTP response.
# ============================================================

async def _run_analysis_for_repository(repository_id: str, repository_name: str) -> None:
    """
    Full three-phase analysis pipeline run as a background task.
    Creates an AnalysisRun, executes AST + static analysis, persists all
    architecture entities, and marks the run as completed (or failed).
    Uses its own DB session so it is fully independent of the request session.
    """
    async with AsyncSessionLocal() as db:
        # PHASE 1: Create AnalysisRun record (status = "running")
        analysis_run = AnalysisRun(
            id=str(uuid.uuid4()),
            repository_id=repository_id,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        try:
            db.add(analysis_run)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error(
                "background_analysis: failed to create AnalysisRun for %s: %s",
                repository_id, exc,
            )
            return

        analysis_run_id = analysis_run.id

        # PHASE 2: AST generation + static analysis
        try:
            repository_path = repository_analysis_service.get_local_repository_path(
                repository_id, repository_name
            )
            analysis_result = await repository_analysis_service.analyze_repository(
                str(repository_path),
            )
        except Exception as exc:
            await repository_analysis_service.record_analysis_failure(
                db, analysis_run_id, str(exc),
            )
            logger.error(
                "background_analysis: analysis phase failed for %s (run %s): %s",
                repository_id, analysis_run_id, exc,
            )
            return

        # PHASE 3: Persist all architecture entities and mark completed
        try:
            await repository_analysis_service.complete_analysis_run(
                db, analysis_run_id, analysis_result,
            )
            logger.info(
                "background_analysis: completed for repository %s (run %s)",
                repository_id, analysis_run_id,
            )
        except Exception as exc:
            logger.error(
                "background_analysis: persistence failed for %s (run %s): %s",
                repository_id, analysis_run_id, exc,
            )


# ============================================================
# LIST REPOSITORIES  (used by the frontend Architecture tab as a
# temporary fallback when no repository has been scanned yet in the
# current session — returns repos ordered newest-first)
# ============================================================

@router.get(
    "/",
    response_model=list[RepositoryResponse],
    status_code=status.HTTP_200_OK,
)
async def list_repositories(
    db: AsyncSession = Depends(get_db),
) -> list[RepositoryResponse]:
    """
    Return all repositories ordered by creation date descending.
    The first item is the most recently created repository.
    """
    repos = await repository_repository.list_all(db)
    return repos


# ============================================================
# CLONE REPOSITORY
# GitHub URL → Clone locally → ZIP → S3
# ============================================================

@router.post(
    "/clone",
    response_model=RepositoryCloneResponse,
    status_code=status.HTTP_201_CREATED,
)
async def clone_repository(
    request: RepositoryCloneRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> RepositoryCloneResponse:

    try:
        result = await repository_service.clone_repository(
            str(request.repository_url), db
        )

        # Automatically trigger full analysis pipeline in the background.
        # The clone response returns immediately; architecture data will be
        # available in PostgreSQL once the background task completes.
        background_tasks.add_task(
            _run_analysis_for_repository,
            result["repository_id"],
            result["repository_name"],
        )
        return RepositoryCloneResponse(
            message="Repository downloaded successfully.",
            **result,
        )

    except GitCloneError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unable to access or clone the repository. "
                "The repository may be private, unavailable, "
                "invalid, or inaccessible."
            ),
        ) from e

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    except S3UploadError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Repository archive could not be stored: {error}",
        ) from error


# ============================================================
# UPLOAD REPOSITORY
# ZIP → local extract → S3
# ============================================================

@router.post(
    "/upload",
    response_model=RepositoryCloneResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_repository(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> RepositoryCloneResponse:

    try:
        result = await repository_upload_service.upload_file(file, db)

        # Automatically trigger full analysis pipeline in the background.
        background_tasks.add_task(
            _run_analysis_for_repository,
            result["repository_id"],
            result["repository_name"],
        )

        return RepositoryCloneResponse(
            message="Repository uploaded successfully.",
            **result,
        )

    except RepositoryUploadError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    except S3UploadError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Repository archive could not be stored: {error}",
        ) from error


# ============================================================
# ANALYZE REPOSITORY
# ============================================================

@router.post(
    "/analyze/{repository_id}",
    response_model=AnalyzeRepositoryResponse,
    status_code=status.HTTP_200_OK,
)
async def analyze_repository(
    repository_id: str,
    db: AsyncSession = Depends(get_db),
) -> AnalyzeRepositoryResponse:
    repository = await repository_repository.get_by_id(db, repository_id)
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    # PHASE 1: INITIALIZATION
    analysis_run = AnalysisRun(
        id=str(uuid.uuid4()),
        repository_id=repository.id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    try:
        db.add(analysis_run)
        await db.commit()
    except Exception as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize analysis run: {str(error)}",
        ) from error

    analysis_run_id = analysis_run.id

    # PHASE 2: LONG-RUNNING STATIC ANALYSIS
    try:
        repository_path = repository_analysis_service.get_local_repository_path(
            repository.id, repository.name
        )
        analysis_result = await repository_analysis_service.analyze_repository(
            str(repository_path),
        )
    except Exception as error:
        # CASE 1: Static analysis itself failed
        await repository_analysis_service.record_analysis_failure(
            db,
            analysis_run_id,
            str(error),
        )
        if isinstance(error, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(error)}",
        ) from error

    # PHASE 3: PERSIST FINDINGS & COMPLETE ANALYSIS RUN
    try:
        updated_analysis_run = await repository_analysis_service.complete_analysis_run(
            db,
            analysis_run_id,
            analysis_result,
        )
        return {
            "repository_id": repository_id,
            "analysis_run_id": updated_analysis_run.id,
            "message": "Repository analyzed successfully.",
            "analysis": analysis_result,
        }
    except Exception as error:
        # CASE 2: Database persistence failed
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis persistence failed: {str(error)}",
        ) from error


# ============================================================
# ANALYZE SINGLE FILE
# ============================================================

@router.post(
    "/analyze-file",
    status_code=status.HTTP_200_OK,
)
async def analyze_file(
    file: UploadFile = File(...),
) -> dict:

    try:
        contents = await file.read()

        with tempfile.NamedTemporaryFile(
            suffix=Path(file.filename).suffix if file.filename else "",
            delete=False,
        ) as tmp_file:
            tmp_file.write(contents)
            tmp_path = tmp_file.name

        try:
            analysis_result = await repository_analysis_service.analyze_file(tmp_path)
            return {
                "filename": file.filename,
                "message": "File analyzed successfully.",
                "analysis": analysis_result,
            }
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(error)}",
        ) from error


# ============================================================
# EXPORT REPOSITORY REPORT
# ============================================================

@router.get(
    "/export/{repository_id}",
    status_code=status.HTTP_200_OK,
)
async def export_repository_analysis(
    repository_id: str,
    repository_path: str,
    format: str = "pdf",
):
    """
    Export repository analysis and bug reports in various formats:
    Supported formats: pdf, csv, json, md, html
    """
    from fastapi.responses import Response
    from app.services.bug_report_service import bug_report_service

    path = Path(repository_path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository path not found: {repository_path}",
        )

    try:
        analysis_result = await repository_analysis_service.analyze_repository(
            repository_path,
            repository_id=repository_id,
        )

        content, media_type, filename = bug_report_service.export_reports(
            reports=analysis_result.get("bug_reports", []),
            format_type=format,
            summary_stats=analysis_result.get("summary_stats"),
            repo_info={
                "id": repository_id,
                "path": repository_path,
                "name": path.name,
            },
        )

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        }
        return Response(content=content, media_type=media_type, headers=headers)

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(error)}",
        ) from error


# ============================================================
# ARCHITECTURE & TOPOLOGY (TAB 2)
# ============================================================

async def _build_architecture_topology_response(
    db: AsyncSession,
    analysis_run: AnalysisRun,
) -> ArchitectureTopologyResponse:
    """Helper to query all architecture and topology entities and build response."""
    summary = await architecture_summary_repository.get_by_analysis_run_id(
        db, analysis_run.id
    )
    technologies = await technology_repository.list_by_analysis_run_id(
        db, analysis_run.id
    )
    components = await architecture_component_repository.list_by_analysis_run_id(
        db, analysis_run.id
    )
    source_files = await source_file_repository.list_by_analysis_run_id(
        db, analysis_run.id
    )

    # Group source files by component_id
    files_by_component: dict[str, list[SourceFileSchema]] = {}
    uncategorized: list[SourceFileSchema] = []

    for sf in source_files:
        sf_schema = SourceFileSchema(
            id=sf.id,
            file_path=sf.file_path,
            file_name=sf.file_name,
            extension=sf.extension,
            language=sf.language,
            line_count=sf.line_count,
            role=sf.role,
            intent=sf.intent,
            is_supported=sf.is_supported,
        )
        if sf.component_id:
            files_by_component.setdefault(sf.component_id, []).append(sf_schema)
        else:
            uncategorized.append(sf_schema)

    component_schemas = [
        ArchitectureComponentSchema(
            id=comp.id,
            name=comp.name,
            component_type=comp.component_type,
            description=comp.description,
            root_path=comp.root_path,
            source_files=files_by_component.get(comp.id, []),
        )
        for comp in components
    ]

    from app.services.technology_detector import CATEGORY_PRIORITY, PRIMARY_CATEGORIES

    # Sort technologies deterministically by category priority and name
    sorted_techs = sorted(
        technologies,
        key=lambda t: (
            CATEGORY_PRIORITY.get(t.category, 99),
            t.name.lower(),
        ),
    )

    technology_schemas = []
    primary_tech_schemas = []
    secondary_tech_schemas = []

    for tech in sorted_techs:
        is_primary = tech.category in PRIMARY_CATEGORIES
        ts = TechnologySchema(
            id=tech.id,
            name=tech.name,
            category=tech.category,
            version=tech.version,
            detection_source=tech.detection_source,
            is_primary=is_primary,
        )
        technology_schemas.append(ts)
        if is_primary:
            primary_tech_schemas.append(ts)
        else:
            secondary_tech_schemas.append(ts)

    summary_schema = (
        ArchitectureSummarySchema(
            intent=summary.intent,
            architecture_overview=summary.architecture_overview,
            health_assessment=summary.health_assessment,
            parser_version=summary.parser_version,
        )
        if summary
        else None
    )

    return ArchitectureTopologyResponse(
        analysis_run_id=analysis_run.id,
        repository_id=analysis_run.repository_id,
        summary=summary_schema,
        technologies=technology_schemas,
        primary_technologies=primary_tech_schemas,
        secondary_technologies=secondary_tech_schemas,
        components=component_schemas,
        uncategorized_files=uncategorized,
        total_source_files=len(source_files),
        total_components=len(component_schemas),
        total_technologies=len(technology_schemas),
        total_primary_technologies=len(primary_tech_schemas),
        total_secondary_technologies=len(secondary_tech_schemas),
    )


@router.get(
    "/analysis/{analysis_run_id}/architecture",
    response_model=ArchitectureTopologyResponse,
    status_code=status.HTTP_200_OK,
)
async def get_analysis_run_architecture(
    analysis_run_id: str,
    db: AsyncSession = Depends(get_db),
) -> ArchitectureTopologyResponse:
    """
    Retrieve full codebase architecture summary, component topology,
    technology stack, and categorized source files for a specific analysis run.
    """
    analysis_run = await db.get(AnalysisRun, analysis_run_id)
    if analysis_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis run not found: {analysis_run_id}",
        )

    return await _build_architecture_topology_response(db, analysis_run)


@router.get(
    "/{repository_id}/architecture",
    response_model=ArchitectureTopologyResponse,
    status_code=status.HTTP_200_OK,
)
async def get_repository_architecture(
    repository_id: str,
    db: AsyncSession = Depends(get_db),
) -> ArchitectureTopologyResponse:
    """
    Retrieve latest architecture summary and topology for a repository.
    """
    repo = await repository_repository.get_by_id(db, repository_id)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    stmt = (
        select(AnalysisRun)
        .where(
            AnalysisRun.repository_id == repository_id,
            AnalysisRun.status == "completed",
        )
        .order_by(AnalysisRun.created_at.desc())
    )
    result = await db.execute(stmt)
    latest_run = result.scalars().first()

    if latest_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed analysis run found for this repository.",
        )

    return await _build_architecture_topology_response(db, latest_run)
