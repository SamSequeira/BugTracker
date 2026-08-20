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