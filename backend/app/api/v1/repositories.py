from fastapi import APIRouter, HTTPException, status, File, UploadFile
from fastapi.responses import JSONResponse
from pathlib import Path
import tempfile
import os

from app.schemas.repository import (
    RepositoryCloneRequest,
    RepositoryCloneResponse,
)
from app.services.repository_service import repository_service
from app.services.repository_analysis_service import repository_analysis_service
from app.utils.git import GitCloneError

from app.services.repository_upload_service import (
    RepositoryUploadError,
    repository_upload_service,
)


router = APIRouter(
    prefix="/repositories",
    tags=["Repositories"],
)


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
) -> RepositoryCloneResponse:

    try:
        result = await repository_service.clone_repository(
            str(request.repository_url)
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
    file: UploadFile = File(...),
) -> RepositoryCloneResponse:

    try:
        result = await repository_upload_service.upload_file(file)
        return RepositoryCloneResponse(
            message="Repository uploaded successfully.",
            **result,
        )

    except RepositoryUploadError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error


# ============================================================
# ANALYZE REPOSITORY
# ============================================================

@router.post(
    "/analyze/{repository_id}",
    status_code=status.HTTP_200_OK,
)
async def analyze_repository(
    repository_id: str,
    repository_path: str,
) -> dict:

    try:
        analysis_result = await repository_analysis_service.analyze_repository(
            repository_path,
        )
        return JSONResponse(content={
            "repository_id": repository_id,
            "message": "Repository analyzed successfully.",
            "analysis": analysis_result,
        })

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
