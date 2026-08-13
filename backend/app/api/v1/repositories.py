from fastapi import APIRouter, HTTPException, status

from app.schemas.repositories import (
    RepositoryCloneRequest,
    RepositoryCloneResponse,
)
from app.services.repository_service import repository_service
from app.utils.git import GitCloneError

from fastapi import APIRouter, File, HTTPException, UploadFile, status

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

    except GitCloneError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unable to access or clone the repository. "
                "The repository may be private, unavailable, "
                "invalid, or inaccessible."
            ),
        )

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


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
        )