from fastapi import APIRouter, HTTPException, status

from app.schemas.repositories import (
    RepositoryCloneRequest,
    RepositoryCloneResponse,
)
from app.services.repository_service import repository_service
from app.utils.git import GitCloneError


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