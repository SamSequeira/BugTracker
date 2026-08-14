from fastapi import APIRouter, HTTPException, status, File, UploadFile
from pathlib import Path
import tempfile
import os

from app.schemas.repositories import (
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


@router.post(
    "/upload",
    response_model=RepositoryCloneResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_repository(
    file: UploadFile = File(...),
) -> RepositoryCloneResponse:

    try:
        result = await repository_upload_service.upload_file(
            file
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


@router.post(
    "/analyze/{repository_id}",
    status_code=status.HTTP_200_OK,
)
async def analyze_repository(
    repository_id: str,
    repository_path: str,
) -> dict:
    """
    Analyze a repository for language detection and AST generation.
    
    Args:
        repository_id: ID of the repository
        repository_path: Path to the repository directory
        
    Returns:
        Analysis results with detected languages and AST for each file
    """
    try:
        analysis_result = await repository_analysis_service.analyze_repository(
            repository_path
        )
        
        return {
            "repository_id": repository_id,
            "message": "Repository analyzed successfully.",
            "analysis": analysis_result,
        }
    
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


@router.post(
    "/analyze-file",
    status_code=status.HTTP_200_OK,
)
async def analyze_file(
    file: UploadFile = File(...),
) -> dict:
    """
    Analyze a single uploaded file for language detection and AST generation.
    
    Args:
        file: The code file to analyze
        
    Returns:
        Analysis results with language and AST
    """
    try:
        # Save file temporarily
        contents = await file.read()
        
        with tempfile.NamedTemporaryFile(
            suffix=Path(file.filename).suffix if file.filename else "",
            delete=False
        ) as tmp_file:
            tmp_file.write(contents)
            tmp_path = tmp_file.name
        
        try:
            # Analyze the file
            analysis_result = await repository_analysis_service.analyze_file(tmp_path)
            
            return {
                "filename": file.filename,
                "message": "File analyzed successfully.",
                "analysis": analysis_result,
            }
        finally:
            # Clean up temporary file
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