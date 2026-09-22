"""
resolve.py
----------
FastAPI router for the LangGraph-powered resolution pipeline and GitHub PR bot.

Endpoints
---------
POST /api/v1/resolve/{bug_id}
    Runs the full LangGraph resolution graph for a bug_id.
    Accepts the raw bug dict as JSON body; returns full trace + final state.

POST /api/v1/pr-analyse
    Runs the GitHub PR bot on a PR URL or owner/repo/number.
    Returns the structured comment and analysis reports.

GET  /api/v1/pr-analyse/comment-preview
    Same as POST but returns the rendered Markdown comment only (for previewing).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="",
    tags=["Resolution & PR Analysis"],
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ResolveBugRequest(BaseModel):
    """
    Payload for POST /resolve/{bug_id}.
    All fields except raw_issue are optional — the graph will infer them
    from raw_issue if present.
    """
    raw_issue: Dict[str, Any] = Field(
        default_factory=dict,
        description="The candidate issue dict (from static analysis / enrichment).",
    )
    rule_id: Optional[str] = Field(None, description="Rule ID (e.g. PY_DIV_001). Inferred from raw_issue if absent.")
    language: Optional[str] = Field(None, description="Language (Python / JavaScript / Java).")
    file_path: Optional[str] = Field(None, description="Source file path.")
    code_snippet: Optional[str] = Field(None, description="Code snippet containing the bug.")
    severity: Optional[str] = Field(None, description="Severity override.")


class ResolveBugResponse(BaseModel):
    """Full resolution trace returned to the caller."""
    bug_id: str
    terminal_status: str
    validation_status: str
    ai_confidence: float
    routing_decision: str
    routing_rationale: str
    root_cause: str
    fix_diff: Dict[str, Any]
    reviewer_critique: str
    crew_approved: bool
    test_source: str
    pre_fix_passed: Optional[bool]
    post_fix_passed: Optional[bool]
    test_error: Optional[str]
    retry_count: int
    trace: List[str]


class PRAnalyseRequest(BaseModel):
    """Payload for POST /pr-analyse."""
    pr_url: Optional[str] = Field(None, description="Full GitHub PR URL.")
    owner: Optional[str] = Field(None, description="Repository owner.")
    repo: Optional[str] = Field(None, description="Repository name.")
    pr_number: Optional[int] = Field(None, description="PR number.")
    post_comment: bool = Field(
        False,
        description="Whether to actually post the comment to GitHub (requires GITHUB_TOKEN).",
    )


class PRAnalyseResponse(BaseModel):
    owner: str
    repo: str
    pr_number: int
    total_issues: int
    posted: bool
    comment_body: str
    reports: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# /resolve/{bug_id}
# ---------------------------------------------------------------------------

@router.post(
    "/resolve/{bug_id}",
    response_model=ResolveBugResponse,
    status_code=status.HTTP_200_OK,
    summary="Run LangGraph resolution pipeline for a single bug",
)
async def resolve_bug(
    bug_id: str,
    request: ResolveBugRequest,
) -> ResolveBugResponse:
    """
    Runs the full LangGraph resolution graph:
    classify → route → [resolution crew] → test harness → (retry loop) → terminal

    Returns the full trace so the response is self-documenting for demos.
    """
    import asyncio
    from app.services.orchestration.resolution_graph import run_resolution

    raw_issue = dict(request.raw_issue)

    initial_state = {
        "bug_id": bug_id,
        "rule_id": request.rule_id or raw_issue.get("rule_id", "UNKNOWN"),
        "language": request.language or raw_issue.get("language", "Python"),
        "file_path": request.file_path or raw_issue.get("file_path", ""),
        "code_snippet": request.code_snippet or raw_issue.get("code_snippet", ""),
        "severity": request.severity or raw_issue.get("severity", "medium"),
        "raw_issue": raw_issue,
    }

    try:
        # run_resolution is synchronous; wrap in thread pool to stay async-safe
        final_state = await asyncio.to_thread(run_resolution, initial_state)
    except Exception as exc:
        logger.exception("Resolution graph failed for bug_id=%s: %s", bug_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Resolution pipeline failed: {exc}",
        ) from exc

    return ResolveBugResponse(
        bug_id=bug_id,
        terminal_status=final_state.get("terminal_status", "UNKNOWN"),
        validation_status=final_state.get("validation_status", "UNVERIFIED"),
        ai_confidence=float(final_state.get("ai_confidence", 0.0)),
        routing_decision=final_state.get("routing_decision", ""),
        routing_rationale=final_state.get("routing_rationale", ""),
        root_cause=final_state.get("root_cause", ""),
        fix_diff=final_state.get("fix_diff") or {},
        reviewer_critique=final_state.get("reviewer_critique", ""),
        crew_approved=bool(final_state.get("crew_approved", False)),
        test_source=final_state.get("test_source", ""),
        pre_fix_passed=final_state.get("pre_fix_passed"),
        post_fix_passed=final_state.get("post_fix_passed"),
        test_error=final_state.get("test_error"),
        retry_count=int(final_state.get("retry_count", 0)),
        trace=list(final_state.get("trace", [])),
    )


# ---------------------------------------------------------------------------
# /pr-analyse
# ---------------------------------------------------------------------------

@router.post(
    "/pr-analyse",
    response_model=PRAnalyseResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyse a GitHub PR and optionally post a review comment",
)
async def analyse_pr(request: PRAnalyseRequest) -> PRAnalyseResponse:
    """
    Fetches the PR diff from GitHub, runs it through the full analysis
    pipeline (static analysis + enrichment + test harness), and returns
    (and optionally posts) a structured Markdown comment.

    Requires GITHUB_TOKEN env-var to fetch private repos or post comments.
    """
    import asyncio
    from app.services.github_pr_bot import github_pr_bot

    if not request.pr_url and not (request.owner and request.repo and request.pr_number):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Supply either pr_url or all of: owner, repo, pr_number.",
        )

    try:
        result = await asyncio.to_thread(
            github_pr_bot.analyse_and_comment,
            request.pr_url,
            request.owner,
            request.repo,
            request.pr_number,
            request.post_comment,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("PR analysis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PR analysis failed: {exc}",
        ) from exc

    return PRAnalyseResponse(
        owner=result["owner"],
        repo=result["repo"],
        pr_number=result["pr_number"],
        total_issues=len(result.get("reports", [])),
        posted=result.get("posted", False),
        comment_body=result.get("comment_body", ""),
        reports=result.get("reports", []),
    )
