"""
resolution_crew.py
------------------
CrewAI resolution crew for the BugTracker pipeline.

Three agents run sequentially (Process.sequential):

  1. RootCauseAgent  — produces a root-cause explanation
                       (reuses BugEnrichmentService._build_explanation logic
                        as its underlying tool, so no prompt duplication)

  2. FixAgent        — given root cause (+ prior failure on retry),
                       produces a fix diff
                       (reuses BugEnrichmentService._generate_suggested_fix)

  3. ReviewerAgent   — sanity-checks the fix diff and either approves or
                       sends a critique back to FixAgent (one pass only)

The crew's scope is narrow: generate and internally review one fix.
It does NOT duplicate classification, severity, or routing logic.

If CrewAI is not installed the module still imports — run_resolution_crew()
falls back to existing BugEnrichmentService calls so the LangGraph node
degrades gracefully.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Underlying tool functions (thin wrappers on existing services)
# These can be called directly by the fallback path AND passed as CrewAI tools.
# ---------------------------------------------------------------------------

def _tool_build_explanation(
    rule_id: str,
    language: str,
    code_snippet: str,
    severity: str,
    raw_issue: Dict[str, Any],
) -> str:
    """
    Tool: call BugEnrichmentService to produce a root-cause explanation.
    Returns the explanation full_text string.
    """
    try:
        from app.services.bug_enrichment_service import BugEnrichmentService
        svc = BugEnrichmentService()

        # Build a minimal issue dict so the enrichment service can run
        minimal_issue = {
            "rule_id": rule_id,
            "issue_type": raw_issue.get("issue_type", "general_issue"),
            "message": raw_issue.get("message", "Potential issue detected"),
            "file_path": raw_issue.get("file_path", ""),
            "line_number": raw_issue.get("line_number", 1),
            "column": raw_issue.get("column", 0),
            "code_snippet": code_snippet,
            "severity": severity,
            "evidence": raw_issue.get("evidence", {}),
        }

        report = svc.enrich_issue(
            issue=minimal_issue,
            repository_id="crew_tool",
        )
        return report.explanation.full_text
    except Exception as exc:
        logger.warning("_tool_build_explanation failed: %s", exc)
        return (
            f"Rule {rule_id} detected an issue in the code. "
            f"Snippet: {code_snippet[:200]}. Severity: {severity}."
        )


def _tool_generate_fix(
    rule_id: str,
    issue_type: str,
    code_snippet: str,
    evidence: Dict[str, Any],
    language: str,
) -> Dict[str, Any]:
    """
    Tool: call BugEnrichmentService._generate_suggested_fix and return a dict.
    """
    try:
        from app.services.bug_enrichment_service import BugEnrichmentService
        svc = BugEnrichmentService()
        fix = svc._generate_suggested_fix(
            rule_id=rule_id,
            issue_type=issue_type,
            snippet=code_snippet,
            evidence=evidence,
            language=language,
        )
        if hasattr(fix, "model_dump"):
            return fix.model_dump()
        return {"remove": None, "add": None, "note": str(fix)}
    except Exception as exc:
        logger.warning("_tool_generate_fix failed: %s", exc)
        return {"remove": None, "add": None, "note": f"Could not generate fix: {exc}"}


def _tool_review_fix(
    rule_id: str,
    root_cause: str,
    fix_diff: Dict[str, Any],
) -> Dict[str, str]:
    """
    Tool: lightweight sanity check of a fix diff.
    Returns {"approved": "true"/"false", "critique": "..."}.

    Heuristics (no LLM required when running offline):
      • Reject if fix_diff is empty (no add/remove)
      • Reject if 'add' line count is suspiciously large (>20 lines)
      • Reject if the fix diff looks completely unrelated to the rule
      • Otherwise approve
    """
    add = (fix_diff.get("add") or "").strip()
    remove = (fix_diff.get("remove") or "").strip()
    note = (fix_diff.get("note") or "").strip()

    if not add and not remove and not note:
        return {
            "approved": "false",
            "critique": "Fix diff is empty — no changes were proposed.",
        }

    if add and add.count("\n") > 20:
        return {
            "approved": "false",
            "critique": (
                f"Fix diff touches {add.count(chr(10))+1} lines — "
                "unexpectedly large. Verify it addresses only the root cause."
            ),
        }

    # Rule-specific quick checks
    RULE_KEYWORDS = {
        "PY_DIV_001":  ["0", "zero", "divisor", "!=", "if"],
        "PY_RES_001":  ["with", "as f", "open"],
        "PY_EXC_001":  ["except", "ValueError", "Exception"],
        "PY_ASS_001":  ["raise", "ValueError", "if"],
        "PY_MUT_001":  ["None", "if"],
        "JS_EQ_001":   ["===", "!=="],
        "JS_DIV_001":  ["0", "throw", "==="],
        "JS_AWA_001":  ["Promise.all"],
        "JAVA_EXC_001":["catch", "logger", "log"],
        "JAVA_EQ_001": ["equals", "Objects"],
        "JAVA_RES_001":["try", "resources"],
    }
    keywords = RULE_KEYWORDS.get(rule_id, [])
    combined = (add + " " + remove + " " + note).lower()
    if keywords:
        hits = [kw for kw in keywords if kw.lower() in combined]
        if not hits:
            return {
                "approved": "false",
                "critique": (
                    f"Fix diff does not seem to address rule {rule_id}. "
                    f"Expected keywords: {keywords}. "
                    "Please revise to target the root cause."
                ),
            }

    return {"approved": "true", "critique": ""}


# ---------------------------------------------------------------------------
# CrewAI crew — with graceful fallback
# ---------------------------------------------------------------------------

def run_resolution_crew(
    rule_id: str,
    language: str,
    code_snippet: str,
    severity: str,
    raw_issue: Dict[str, Any],
    prior_failure: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the three-agent resolution crew and return a result dict:
    {
        "root_cause": str,
        "fix_diff":   {remove, add, note},
        "reviewer_critique": str,
        "approved": bool,
    }

    Falls back to direct tool calls if crewai is not installed.
    """
    try:
        return _run_with_crewai(
            rule_id, language, code_snippet, severity, raw_issue, prior_failure
        )
    except ImportError:
        logger.info("crewai not installed — using direct tool fallback")
        return _run_direct(
            rule_id, language, code_snippet, severity, raw_issue, prior_failure
        )
    except Exception as exc:
        logger.warning("CrewAI crew failed: %s — using direct tool fallback", exc)
        return _run_direct(
            rule_id, language, code_snippet, severity, raw_issue, prior_failure
        )


def _run_direct(
    rule_id: str,
    language: str,
    code_snippet: str,
    severity: str,
    raw_issue: Dict[str, Any],
    prior_failure: Optional[str],
) -> Dict[str, Any]:
    """
    Fallback: call the three tool functions directly, applying the same
    reviewer-critique loop (at most one revision pass).
    """
    evidence = raw_issue.get("evidence", {})
    issue_type = raw_issue.get("issue_type", "general_issue")

    # Step 1 — Root Cause
    root_cause = _tool_build_explanation(
        rule_id=rule_id,
        language=language,
        code_snippet=code_snippet,
        severity=severity,
        raw_issue=raw_issue,
    )

    # Step 2 — Fix (with prior failure context injected into evidence if present)
    if prior_failure:
        evidence = {**evidence, "prior_test_failure": prior_failure}

    fix_diff = _tool_generate_fix(
        rule_id=rule_id,
        issue_type=issue_type,
        code_snippet=code_snippet,
        evidence=evidence,
        language=language,
    )

    # Step 3 — Review
    review = _tool_review_fix(
        rule_id=rule_id,
        root_cause=root_cause,
        fix_diff=fix_diff,
    )
    approved = review["approved"] == "true"
    critique = review["critique"]

    # One revision pass if reviewer rejected
    if not approved:
        logger.info(
            "Reviewer rejected fix for %s: %s — attempting one revision", rule_id, critique
        )
        revised_evidence = {**evidence, "reviewer_critique": critique}
        fix_diff = _tool_generate_fix(
            rule_id=rule_id,
            issue_type=issue_type,
            code_snippet=code_snippet,
            evidence=revised_evidence,
            language=language,
        )
        review2 = _tool_review_fix(rule_id=rule_id, root_cause=root_cause, fix_diff=fix_diff)
        approved = review2["approved"] == "true"
        critique = review2["critique"]

    return {
        "root_cause": root_cause,
        "fix_diff": fix_diff,
        "reviewer_critique": critique,
        "approved": approved,
    }


def _run_with_crewai(
    rule_id: str,
    language: str,
    code_snippet: str,
    severity: str,
    raw_issue: Dict[str, Any],
    prior_failure: Optional[str],
) -> Dict[str, Any]:
    """
    Run the full CrewAI crew.  Only called when crewai IS installed.

    Agent roles:
      RootCauseAgent  — uses _tool_build_explanation
      FixAgent        — uses _tool_generate_fix (+ prior_failure context)
      ReviewerAgent   — uses _tool_review_fix; if critique non-empty, sends
                        back once so FixAgent can revise
    """
    from crewai import Agent, Task, Crew, Process
    from crewai.tools import tool as crewai_tool
    import os

    evidence = raw_issue.get("evidence", {})
    issue_type = raw_issue.get("issue_type", "general_issue")

    # --- Wrap tool functions as CrewAI tools ---------------------------------
    @crewai_tool("build_explanation")
    def build_explanation_tool(input: str) -> str:  # noqa: A002
        """Generate a root-cause explanation for the bug using BugEnrichmentService."""
        return _tool_build_explanation(
            rule_id=rule_id,
            language=language,
            code_snippet=code_snippet,
            severity=severity,
            raw_issue=raw_issue,
        )

    @crewai_tool("generate_fix")
    def generate_fix_tool(input: str) -> str:  # noqa: A002
        """Generate a fix diff for the bug using BugEnrichmentService."""
        import json
        ev = {**evidence}
        if prior_failure:
            ev["prior_test_failure"] = prior_failure
        if "reviewer_critique" in input:
            ev["reviewer_critique"] = input
        result = _tool_generate_fix(
            rule_id=rule_id,
            issue_type=issue_type,
            code_snippet=code_snippet,
            evidence=ev,
            language=language,
        )
        return json.dumps(result)

    @crewai_tool("review_fix")
    def review_fix_tool(fix_json: str) -> str:
        """Review a proposed fix diff for correctness and relevance."""
        import json
        try:
            fix = json.loads(fix_json)
        except Exception:
            fix = {"add": fix_json, "remove": "", "note": ""}
        result = _tool_review_fix(
            rule_id=rule_id,
            root_cause="",  # tool has no access to state directly
            fix_diff=fix,
        )
        return json.dumps(result)

    # --- Define the LLM (uses env-var; falls back to mock if unset) ----------
    llm_model = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")

    # --- Agents --------------------------------------------------------------
    root_cause_agent = Agent(
        role="Root Cause Analyst",
        goal=(
            f"Identify the precise root cause of rule {rule_id} firing in "
            f"{language} code and produce a concise, accurate explanation."
        ),
        backstory=(
            "You are a senior static analysis engineer specialising in "
            f"{language} bugs. You use the build_explanation tool to leverage "
            "the project's existing enrichment pipeline rather than guessing."
        ),
        tools=[build_explanation_tool],
        verbose=False,
        allow_delegation=False,
        llm=llm_model,
    )

    fix_agent = Agent(
        role="Fix Engineer",
        goal=(
            "Given the root cause, produce the minimal correct fix diff "
            "that resolves the bug without introducing new issues."
        ),
        backstory=(
            f"You are a {language} engineer who writes precise, targeted fixes. "
            "You use the generate_fix tool to produce a unified-diff patch. "
            "When a prior test failure is provided, incorporate that feedback."
        ),
        tools=[generate_fix_tool],
        verbose=False,
        allow_delegation=False,
        llm=llm_model,
    )

    reviewer_agent = Agent(
        role="Fix Reviewer",
        goal=(
            "Verify the proposed fix actually addresses the root cause and "
            "flag any concerns. Approve or request one revision."
        ),
        backstory=(
            "You are a code reviewer who ensures fixes are minimal, "
            "correct, and directly related to the reported issue. "
            "Use the review_fix tool to evaluate the fix diff."
        ),
        tools=[review_fix_tool],
        verbose=False,
        allow_delegation=False,
        llm=llm_model,
    )

    # --- Tasks ---------------------------------------------------------------
    task_root_cause = Task(
        description=(
            f"Use the build_explanation tool to produce a root-cause explanation "
            f"for rule {rule_id} triggered in this snippet:\n```\n{code_snippet}\n```"
            + (f"\nPrior fix attempt failed: {prior_failure}" if prior_failure else "")
        ),
        agent=root_cause_agent,
        expected_output="A concise root-cause explanation string.",
    )

    task_fix = Task(
        description=(
            "Using the root cause from the previous task, call generate_fix "
            "to produce a fix diff JSON with keys: remove, add, note."
        ),
        agent=fix_agent,
        expected_output="A JSON string with keys remove, add, note.",
        context=[task_root_cause],
    )

    task_review = Task(
        description=(
            "Call review_fix with the fix diff JSON from the previous task. "
            "Return the review result JSON ({approved, critique})."
        ),
        agent=reviewer_agent,
        expected_output="A JSON string with keys approved and critique.",
        context=[task_fix],
    )

    # --- Crew ----------------------------------------------------------------
    crew = Crew(
        agents=[root_cause_agent, fix_agent, reviewer_agent],
        tasks=[task_root_cause, task_fix, task_review],
        process=Process.sequential,
        verbose=False,
    )

    try:
        crew.kickoff()
    except Exception as exc:
        logger.warning("CrewAI kickoff raised: %s — using fallback", exc)
        return _run_direct(
            rule_id, language, code_snippet, severity, raw_issue, prior_failure
        )

    # Extract outputs from task results
    import json

    root_cause = (
        str(task_root_cause.output.raw)
        if hasattr(task_root_cause, "output") and task_root_cause.output
        else _tool_build_explanation(rule_id, language, code_snippet, severity, raw_issue)
    )

    fix_dict: Dict[str, Any] = {}
    if hasattr(task_fix, "output") and task_fix.output:
        try:
            fix_dict = json.loads(task_fix.output.raw)
        except Exception:
            fix_dict = _tool_generate_fix(
                rule_id, issue_type, code_snippet, evidence, language
            )
    else:
        fix_dict = _tool_generate_fix(rule_id, issue_type, code_snippet, evidence, language)

    review_dict: Dict[str, Any] = {"approved": "true", "critique": ""}
    if hasattr(task_review, "output") and task_review.output:
        try:
            review_dict = json.loads(task_review.output.raw)
        except Exception:
            review_dict = _tool_review_fix(rule_id, root_cause, fix_dict)
    else:
        review_dict = _tool_review_fix(rule_id, root_cause, fix_dict)

    approved = str(review_dict.get("approved", "true")).lower() == "true"
    critique = review_dict.get("critique", "")

    # One revision pass if reviewer rejected
    if not approved and prior_failure is None:
        revised_ev = {**evidence, "reviewer_critique": critique}
        fix_dict = _tool_generate_fix(
            rule_id, issue_type, code_snippet, revised_ev, language
        )
        review2 = _tool_review_fix(rule_id, root_cause, fix_dict)
        approved = str(review2.get("approved", "true")).lower() == "true"
        critique = review2.get("critique", "")

    return {
        "root_cause": root_cause,
        "fix_diff": fix_dict,
        "reviewer_critique": critique,
        "approved": approved,
    }
