"""
resolution_graph.py
-------------------
LangGraph StateGraph orchestrator for the BugTracker resolution pipeline.

Graph topology
--------------

  [start]
     │
  classify_node   ← ML classification + routing (wraps existing services)
     │
  route_node      ← 5-way conditional edge (AUTO_ACCEPT / SECONDARY_MODEL /
     │               HUMAN_REVIEW / OOD_REJECT / SYSTEM_ERROR)
     │
  ┌──┴──────────────────────┐
  │                         │
  (HUMAN_REVIEW /        (AUTO_ACCEPT /
   OOD_REJECT /           SECONDARY_MODEL)
   SYSTEM_ERROR)              │
     │                    resolution_node  ← CrewAI crew
     │                       │
     │                    test_node        ← test_generation_service
     │                       │
     │            ┌─── post_fix passed? ───┐
     │            │                        │
     │            │ yes                no + retry < 3
     │         [end: VERIFIED]         loop back to resolution_node
     │                                 with failure context
     │                                 if retry == 3 → [end: UNVERIFIED]
     │
  [end: terminal status]

Design decisions
----------------
- All nodes call EXISTING services — zero logic duplication.
- The graph state is a plain TypedDict so it serialises to JSON for the
  API response without extra work.
- LangGraph is imported lazily; if not installed the graph degrades
  gracefully to a linear function that still calls the same services.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Graph state schema
# ---------------------------------------------------------------------------

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore


class ResolutionState(TypedDict, total=False):
    # Input
    bug_id: str
    rule_id: str
    language: str
    file_path: str
    code_snippet: str
    severity: str
    raw_issue: Dict[str, Any]

    # ML classification + routing
    svm_prob: float
    drift_score: float
    is_drift: bool
    distilbert_prob: Optional[float]
    routing_decision: str        # AUTO_ACCEPT / SECONDARY_MODEL / HUMAN_REVIEW / OOD_REJECT / SYSTEM_ERROR
    routing_rationale: str
    ai_confidence: float

    # CrewAI resolution
    root_cause: str
    fix_diff: Dict[str, Any]    # {remove, add, note}
    reviewer_critique: str
    crew_approved: bool

    # Test harness
    test_source: str
    pre_fix_passed: Optional[bool]
    post_fix_passed: Optional[bool]
    test_error: Optional[str]

    # Outcome
    validation_status: str       # VERIFIED / UNVERIFIED
    retry_count: int
    failure_reason: str
    terminal_status: str         # final graph exit label
    trace: List[str]             # ordered human-readable step log


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

def classify_node(state: ResolutionState) -> ResolutionState:
    """
    Runs ML classification and the existing 5-way risk router.
    Wraps app.services.ml.routing.route_candidate_issue exactly as-is.
    """
    from app.services.ml.routing import route_candidate_issue
    from app.services.ml.severity import predict_production_severity

    raw = state.get("raw_issue", {})
    trace = list(state.get("trace", []))

    # Compute severity via existing deterministic engine
    severity = predict_production_severity(raw)

    # Extract routing inputs — use classification block if ML ran, else defaults
    classif = raw.get("classification", {})
    sev_block = classif.get("severity", {}) if classif else {}
    prio_block = classif.get("priority", {}) if classif else {}

    svm_prob = float(sev_block.get("confidence", 0.85))
    drift_score = float(raw.get("drift_score", 0.0))
    is_drift = bool(raw.get("is_drift", False))
    distilbert_prob = raw.get("distilbert_prob")
    payload_bytes = len(str(raw).encode("utf-8"))

    routing_decision, routing_rationale, ai_confidence = route_candidate_issue(
        record=raw,
        svm_prob=svm_prob,
        drift_score=drift_score,
        is_drift=is_drift,
        distilbert_prob=distilbert_prob,
        payload_bytes=payload_bytes,
    )

    trace.append(
        f"[classify] routing={routing_decision} confidence={ai_confidence:.2f} "
        f"severity={severity}"
    )

    return {
        **state,
        "severity": severity,
        "svm_prob": svm_prob,
        "drift_score": drift_score,
        "is_drift": is_drift,
        "routing_decision": routing_decision,
        "routing_rationale": routing_rationale,
        "ai_confidence": ai_confidence,
        "trace": trace,
    }


def route_node(state: ResolutionState) -> str:
    """
    Conditional edge: maps routing_decision → next node name.

    Returns one of the string node names that LangGraph will follow.
    """
    decision = state.get("routing_decision", "HUMAN_REVIEW")
    mapping = {
        "AUTO_ACCEPT":      "resolution_node",
        "SECONDARY_MODEL":  "resolution_node",
        "HUMAN_REVIEW":     "terminal_human_review",
        "OOD_REJECT":       "terminal_ood_reject",
        "SYSTEM_ERROR":     "terminal_system_error",
    }
    return mapping.get(decision, "terminal_human_review")


def resolution_node(state: ResolutionState) -> ResolutionState:
    """
    Calls the CrewAI resolution crew (root cause + fix + review).
    Falls back to existing BugEnrichmentService explanation/fix if CrewAI unavailable.
    """
    from app.services.orchestration.resolution_crew import run_resolution_crew

    trace = list(state.get("trace", []))
    retry = state.get("retry_count", 0)
    failure_reason = state.get("failure_reason", "")

    try:
        crew_result = run_resolution_crew(
            rule_id=state.get("rule_id", ""),
            language=state.get("language", ""),
            code_snippet=state.get("code_snippet", ""),
            severity=state.get("severity", "medium"),
            raw_issue=state.get("raw_issue", {}),
            prior_failure=failure_reason if retry > 0 else None,
        )
        root_cause = crew_result.get("root_cause", "")
        fix_diff = crew_result.get("fix_diff", {})
        reviewer_critique = crew_result.get("reviewer_critique", "")
        crew_approved = crew_result.get("approved", True)

        trace.append(
            f"[resolution] retry={retry} crew_approved={crew_approved} "
            f"root_cause_len={len(root_cause)}"
        )
    except Exception as exc:
        logger.warning("CrewAI resolution failed, falling back to enrichment service: %s", exc)
        # Fallback: use existing BugEnrichmentService fix generation
        from app.services.bug_enrichment_service import BugEnrichmentService
        svc = BugEnrichmentService()
        raw = state.get("raw_issue", {})
        fix = svc._generate_suggested_fix(
            rule_id=state.get("rule_id", ""),
            issue_type=raw.get("issue_type", "general"),
            snippet=state.get("code_snippet", ""),
            evidence=raw.get("evidence", {}),
            language=state.get("language", "Python"),
        )
        root_cause = raw.get("message", "Issue detected by static analysis.")
        fix_diff = fix.model_dump() if hasattr(fix, "model_dump") else {}
        reviewer_critique = ""
        crew_approved = True
        trace.append(f"[resolution] crew_fallback retry={retry}")

    return {
        **state,
        "root_cause": root_cause,
        "fix_diff": fix_diff,
        "reviewer_critique": reviewer_critique,
        "crew_approved": crew_approved,
        "trace": trace,
    }


def run_test_node(state: ResolutionState) -> ResolutionState:
    """
    Runs the regression test harness (Feature 1).
    Wraps test_generation_service.generate_and_run() exactly as-is.
    """
    from app.services.test_generation_service import test_generation_service

    trace = list(state.get("trace", []))
    fix_diff = state.get("fix_diff") or {}

    try:
        result = test_generation_service.generate_and_run(
            rule_id=state.get("rule_id", ""),
            language=state.get("language", "Python"),
            suggested_fix=fix_diff,
            file_path=state.get("file_path"),
            code_snippet=state.get("code_snippet"),
        )
        pre = result.pre_fix_run
        post = result.post_fix_run
        pre_passed = pre.passed if pre else None
        post_passed = post.passed if post else None
        test_error = result.error
        test_source = result.generated_test_source
        trace.append(
            f"[test] pre_fix_passed={pre_passed} post_fix_passed={post_passed} "
            f"validated={result.validated}"
        )
    except Exception as exc:
        logger.warning("run_test_node harness error: %s", exc)
        pre_passed = None
        post_passed = False
        test_error = str(exc)
        test_source = ""
        trace.append(f"[test] error={exc}")

    return {
        **state,
        "test_source": test_source,
        "pre_fix_passed": pre_passed,
        "post_fix_passed": post_passed,
        "test_error": test_error,
        "trace": trace,
    }


# Keep backward-compatible name for the LangGraph node registry string "test_node" —
# the *function* is run_test_node; the graph references it by string name only.



def should_retry(state: ResolutionState) -> str:
    """
    After test_node: decide whether to loop back or terminate.

    Returns:
      "end_verified"   → post-fix passed
      "retry"          → post-fix failed, retry count < MAX_RETRIES
      "end_unverified" → post-fix failed, exhausted retries
    """
    post_passed = state.get("post_fix_passed")
    retry = state.get("retry_count", 0)

    if post_passed:
        return "end_verified"
    if retry < MAX_RETRIES:
        return "retry"
    return "end_unverified"


def increment_retry(state: ResolutionState) -> ResolutionState:
    """Bump retry counter and record failure reason before re-entering resolution_node."""
    pre = state.get("pre_fix_passed")
    post = state.get("post_fix_passed")
    test_err = state.get("test_error", "")
    failure = (
        test_err
        or f"pre_fix_passed={pre}, post_fix_passed={post}"
    )
    trace = list(state.get("trace", []))
    trace.append(f"[retry] count={state.get('retry_count',0)+1} reason={failure[:120]}")
    return {
        **state,
        "retry_count": state.get("retry_count", 0) + 1,
        "failure_reason": failure,
        "trace": trace,
    }


def terminal_verified(state: ResolutionState) -> ResolutionState:
    trace = list(state.get("trace", []))
    trace.append("[terminal] status=VERIFIED")
    return {**state, "validation_status": "VERIFIED", "terminal_status": "VERIFIED", "trace": trace}


def terminal_unverified(state: ResolutionState) -> ResolutionState:
    trace = list(state.get("trace", []))
    trace.append("[terminal] status=UNVERIFIED (retries exhausted)")
    return {**state, "validation_status": "UNVERIFIED", "terminal_status": "UNVERIFIED", "trace": trace}


def terminal_human_review(state: ResolutionState) -> ResolutionState:
    trace = list(state.get("trace", []))
    trace.append(f"[terminal] status=HUMAN_REVIEW reason={state.get('routing_rationale', '')}")
    return {**state, "validation_status": "UNVERIFIED", "terminal_status": "HUMAN_REVIEW", "trace": trace}


def terminal_ood_reject(state: ResolutionState) -> ResolutionState:
    trace = list(state.get("trace", []))
    trace.append(f"[terminal] status=OOD_REJECT reason={state.get('routing_rationale', '')}")
    return {**state, "validation_status": "UNVERIFIED", "terminal_status": "OOD_REJECT", "trace": trace}


def terminal_system_error(state: ResolutionState) -> ResolutionState:
    trace = list(state.get("trace", []))
    trace.append(f"[terminal] status=SYSTEM_ERROR reason={state.get('routing_rationale', '')}")
    return {**state, "validation_status": "UNVERIFIED", "terminal_status": "SYSTEM_ERROR", "trace": trace}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_resolution_graph():
    """
    Construct and compile the LangGraph StateGraph.

    Returns the compiled graph (callable as graph.invoke(state)).
    If langgraph is not installed, returns a fallback linear runner.
    """
    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        logger.warning(
            "langgraph not installed — using linear fallback pipeline. "
            "Install with: pip install langgraph"
        )
        return _LinearFallback()

    graph = StateGraph(ResolutionState)

    # Register nodes
    graph.add_node("classify_node",         classify_node)
    graph.add_node("resolution_node",       resolution_node)
    graph.add_node("test_node",             run_test_node)
    graph.add_node("increment_retry",       increment_retry)
    graph.add_node("terminal_human_review", terminal_human_review)
    graph.add_node("terminal_ood_reject",   terminal_ood_reject)
    graph.add_node("terminal_system_error", terminal_system_error)
    graph.add_node("terminal_verified",     terminal_verified)
    graph.add_node("terminal_unverified",   terminal_unverified)

    # Entry
    graph.set_entry_point("classify_node")

    # Classify → conditional routing
    graph.add_conditional_edges(
        "classify_node",
        route_node,
        {
            "resolution_node":     "resolution_node",
            "terminal_human_review": "terminal_human_review",
            "terminal_ood_reject":   "terminal_ood_reject",
            "terminal_system_error": "terminal_system_error",
        },
    )

    # Resolution → test
    graph.add_edge("resolution_node", "test_node")

    # Test → conditional: verified / retry / unverified
    graph.add_conditional_edges(
        "test_node",
        should_retry,
        {
            "end_verified":   "terminal_verified",
            "retry":          "increment_retry",
            "end_unverified": "terminal_unverified",
        },
    )

    # Retry → back to resolution
    graph.add_edge("increment_retry", "resolution_node")

    # Terminals → END
    for terminal in [
        "terminal_human_review",
        "terminal_ood_reject",
        "terminal_system_error",
        "terminal_verified",
        "terminal_unverified",
    ]:
        graph.add_edge(terminal, END)

    return graph.compile()


class _LinearFallback:
    """
    Drop-in replacement when langgraph is unavailable.
    Runs the same nodes in sequence without conditional branching.
    """

    def invoke(self, state: ResolutionState) -> ResolutionState:
        state = dict(state)
        state.setdefault("trace", [])
        state.setdefault("retry_count", 0)

        # 1. Classify
        state = classify_node(state)

        decision = state.get("routing_decision", "AUTO_ACCEPT")
        if decision in ("HUMAN_REVIEW", "OOD_REJECT", "SYSTEM_ERROR"):
            return terminal_human_review(state)

        # 2. Resolution + test with retry loop
        for attempt in range(MAX_RETRIES + 1):
            state = resolution_node(state)
            state = run_test_node(state)
            outcome = should_retry(state)
            if outcome == "end_verified":
                return terminal_verified(state)
            if outcome == "end_unverified" or attempt == MAX_RETRIES:
                return terminal_unverified(state)
            state = increment_retry(state)

        return terminal_unverified(state)


# Module-level compiled graph (lazily built on first call)
_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_resolution_graph()
    return _GRAPH


def run_resolution(initial_state: Dict[str, Any]) -> ResolutionState:
    """
    Convenience entry point.  Runs the graph end-to-end and returns final state.
    """
    state: ResolutionState = {
        "retry_count": 0,
        "trace": [],
        "failure_reason": "",
        "terminal_status": "",
        **initial_state,
    }
    return get_graph().invoke(state)
