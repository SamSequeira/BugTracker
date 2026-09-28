"""
Deterministic Semantic Candidate Selector.

Scores functions by semantic risk using pure AST and static heuristic analysis
(zero LLM cost) to ensure LLM analysis focuses exclusively on high-value business logic.
"""

import ast
import re
from dataclasses import dataclass, field
from typing import Optional, List, Set

from app.services.llm_logic_reviewer import config
from app.services.llm_logic_reviewer.repository_index import FunctionIndexEntry, RepositoryIndex

MONEY_KEYWORDS = {
    "balance", "amount", "money", "currency", "wallet", "transaction",
    "credit", "debit", "payment", "payout", "refund", "price", "fee",
    "withdraw", "deposit", "transfer", "reconcile"
}

AUTH_KEYWORDS = {
    "auth", "permission", "token", "role", "credential", "login",
    "authenticate", "authorize", "secret", "password", "jwt", "session"
}

DB_WRITE_PATTERNS = [
    r"\bdb\.(commit|add|delete|flush|rollback)\b",
    r"\bsession\.(commit|add|delete|flush|rollback)\b",
    r"\b(session|db)\.execute\(",
    r"\.(save|delete|update)\(\)",
]

STATE_MUTATION_PATTERNS = [
    r"\b\w+\.(status|state|is_active|is_deleted|completed|verified|role)\s*=",
]

AGGREGATION_PATTERNS = [
    r"\b(sum|count|avg|min|max)\s*\(",
    r"\.count\(\)",
    r"\.aggregate\(",
]

PAGINATION_PATTERNS = [
    r"\b(limit|offset|page|skip|page_size)\b",
]

FILTER_PATTERNS = [
    r"\b(filter|where|query)\b",
    r"\[\s*\w+\s+for\s+\w+\s+in\s+",  # list comprehension filter
]


@dataclass
class CandidateScore:
    score: int
    reasons: List[str]
    is_candidate: bool
    function_name: str
    file_path: str
    qualname: str = ""


def score_function_candidate(
    code: str,
    function_name: str,
    file_path: str,
    repo_index: Optional[RepositoryIndex] = None,
    fn_entry: Optional[FunctionIndexEntry] = None,
    threshold: Optional[int] = None,
) -> CandidateScore:
    """
    Score a function by semantic risk (additive points):
    - DB write operations (+3)
    - Module-level / shared cache access (+3)
    - Money / balance / wallet keywords (+3)
    - Auth / permission keywords (+2)
    - API route handler (+2)
    - Filtering + pagination (+2)
    - Aggregations (+2)
    - Cross-file callee (+2)
    - State mutation (+2)
    - External API call (+1)
    - Error handling (+1)

    A score >= threshold (default 3) qualifies as a candidate for semantic LLM review.
    """
    if threshold is None:
        threshold = config.SEMANTIC_CANDIDATE_SCORE_THRESHOLD

    score = 0
    reasons: List[str] = []
    lower_code = code.lower()
    lower_name = function_name.lower()
    qualname = fn_entry.qualname if fn_entry else f"{file_path}::{function_name}"

    # 1. DB write operations (+3)
    if any(re.search(pat, code) for pat in DB_WRITE_PATTERNS):
        score += 3
        reasons.append("Database write/commit/mutation operation detected (+3)")

    # 2. Module-level / shared cache access (+3)
    has_cache = False
    if repo_index:
        norm_fp = file_path.replace("\\", "/")
        module_states = repo_index.get_module_level_state(norm_fp)
        for state in module_states:
            if re.search(r"\b" + re.escape(state.name) + r"\b", code):
                score += 3
                reasons.append(f"Reads/writes module-level state variable '{state.name}' (+3)")
                has_cache = True
                break
    if not has_cache and ("cache" in lower_code or "cache" in lower_name):
        score += 3
        reasons.append("Contains cache interaction keywords (+3)")

    # 3. Money / balance / financial keywords (+3)
    matched_money = [kw for kw in MONEY_KEYWORDS if kw in lower_name or kw in lower_code]
    if matched_money:
        score += 3
        reasons.append(f"Financial / balance domain keywords: {', '.join(matched_money[:3])} (+3)")

    # 4. Auth / permission keywords (+2)
    matched_auth = [kw for kw in AUTH_KEYWORDS if kw in lower_name or kw in lower_code]
    if matched_auth:
        score += 2
        reasons.append(f"Security / authentication keywords: {', '.join(matched_auth[:3])} (+2)")

    # 5. API route handler (+2)
    is_route = False
    if fn_entry and fn_entry.api_references:
        is_route = True
    elif re.search(r"@\w*router|\b@(app|api|blueprint)\b", code):
        is_route = True
    if is_route:
        score += 2
        reasons.append("Exposed API route handler (+2)")

    # 6. Filtering + pagination (+2)
    has_pagination = any(re.search(pat, lower_code) for pat in PAGINATION_PATTERNS)
    has_filtering = any(re.search(pat, lower_code) for pat in FILTER_PATTERNS)
    if has_pagination and has_filtering:
        score += 2
        reasons.append("Performs filtering combined with pagination/limits (+2)")

    # 7. Aggregations (+2)
    if any(re.search(pat, code) for pat in AGGREGATION_PATTERNS):
        score += 2
        reasons.append("Performs aggregation/summary computation (+2)")

    # 8. Cross-file callee (+2)
    if repo_index and qualname in repo_index.callees_of:
        callees = repo_index.callees_of.get(qualname, set())
        has_cross_file = any(
            "::" in c and not c.startswith(file_path.replace("\\", "/"))
            for c in callees
        )
        if has_cross_file:
            score += 2
            reasons.append("Calls functions across file boundaries (+2)")

    # 9. State mutation (+2)
    if any(re.search(pat, code) for pat in STATE_MUTATION_PATTERNS):
        score += 2
        reasons.append("Mutates business object state attributes (+2)")

    # 10. External API calls (+1)
    if re.search(r"\b(requests\.|httpx\.|urllib\.|aiohttp\.)", code):
        score += 1
        reasons.append("Performs external HTTP network requests (+1)")

    # 11. Error handling (+1)
    if "try:" in code and ("except" in code or "finally:" in code):
        score += 1
        reasons.append("Contains error handling / exception blocks (+1)")

    is_candidate = score >= threshold

    return CandidateScore(
        score=score,
        reasons=reasons,
        is_candidate=is_candidate,
        function_name=function_name,
        file_path=file_path,
        qualname=qualname,
    )
