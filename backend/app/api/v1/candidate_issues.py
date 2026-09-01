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
        Γåô
    AST Generation
        Γåô
    Static Analysis
        Γåô
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
