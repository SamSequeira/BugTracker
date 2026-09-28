"""
High-precision semantic LLM bug detector focused on concrete defects.

MISSION: Identify ONLY genuine semantic bugs, not potential improvements.

Detects:
1. WRONG_DATA_FLOW ΓÇö wrong value/variable used
2. WRONG_CONDITION ΓÇö inverted/contradictory logic
3. WRONG_STATE_TRANSITION ΓÇö invalid state progression
4. WRONG_OPERATION_ORDER ΓÇö operations in wrong sequence
5. CROSS_FUNCTION_MISMATCH ΓÇö caller/callee semantic mismatch

Rejects:
- Style, naming, formatting
- Missing docs, comments
- Generic validation/security/performance advice
- Refactoring suggestions
- Hypothetical edge cases
- Uncertainty ("might", "could")
- Test improvements
- Maintainability concerns

Principle: 1 genuine bug beats 10 speculative findings.
Confidence < 0.95 is not sufficient without strong source evidence.
Source evidence > self-reported confidence.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

from app.services.llm_logic_reviewer import config
from app.services.llm_logic_reviewer.llm_provider import create_llm_provider
from app.services.llm_logic_reviewer.source_validator import validate_candidate_against_source
from app.services.llm_logic_reviewer.semantic_facts import extract_semantic_facts
from app.services.llm_logic_reviewer.value_flow import extract_value_flow_for_function
from app.services.llm_logic_reviewer.repository_index import RepositoryIndex
from app.services.llm_logic_reviewer.context_retriever import retrieve_context_for_function, RetrievedContextPackage
from app.services.llm_logic_reviewer.candidate_selector import score_function_candidate
from app.services.llm_logic_reviewer.evidence_builder import build_cross_file_evidence, EvidencePacket
from app.services.llm_logic_reviewer.openai_reasoner import reason_about_semantic_candidate
from app.services.llm_logic_reviewer.evidence_validator import validate_semantic_finding

logger = logging.getLogger(__name__)

_provider = create_llm_provider()
_executor = ThreadPoolExecutor(max_workers=1)

# Global LLM call counter for monitoring token usage
_llm_call_count = 0

def get_llm_call_count() -> int:
    """Get total LLM calls made in current session."""
    global _llm_call_count
    return _llm_call_count

def reset_llm_call_count():
    """Reset LLM call counter (useful for testing)."""
    global _llm_call_count
    _llm_call_count = 0


class TemplateString(str):
    """Template string providing default values for optional placeholders."""

    def format(self, *args, **kwargs):
        kwargs.setdefault("value_flow", "")
        kwargs.setdefault("understanding", "")
        return super().format(*args, **kwargs)


PASS1_UNDERSTAND_PROMPT = TemplateString("""Analyze the target function's intent and execution contract.
Target Function: {function_name}
File: {file_path}

EXTRACTED FACTS:
{semantic_facts}
{repository_context}

Source Code:
{function_code}

Respond in JSON:
{{
  "intent": "Brief statement of intended logic and purpose",
  "inputs_contract": "Expected parameter types, non-None guarantees, or unit conventions",
  "return_contract": "Expected return type, exit code semantics, or return value structure",
  "side_effects": "State mutations, DB actions, or external calls"
}}
""")


PASS2_HYPOTHESIS_PROMPT = TemplateString("""You are an expert semantic code investigator auditing code for concrete logic defects.

FUNCTION UNDER INVESTIGATION:
Name: {function_name}
File: {file_path}

FUNCTION CONTRACT & UNDERSTANDING:
{understanding}

EXTRACTED FACTS & VALUE FLOW:
{semantic_facts}
{value_flow}

REPOSITORY CONTEXT:
{repository_context}

Source Code:
{function_code}

INVESTIGATE THESE 15 SEMANTIC BUG DIMENSIONS:
1. INPUT/OUTPUT CONTRACT: Does implementation violate caller expectation or docstring contract?
2. ARGUMENT SEMANTICS & ORDER: Are arguments passed in correct semantic order (e.g., buyer vs merchant, source vs dest)?
3. RETURN VALUE SEMANTICS & POSIX EXIT CODES: Is return value misinterpreted (e.g. exit code 0 checked with 'if result:')?
4. CONDITION SEMANTICS & COMPARISONS: Inverted comparison or incorrect boolean check?
5. STATE TRANSITIONS & LIFECYCLE: Is status mutated (status='SHIPPED') before external carrier dispatch succeeds?
6. DATA FLOW & UNIT CONVERSION: Unit/currency mismatches (cents vs dollars, percentage vs fraction)?
7. VALIDATION vs FORMULA CONSISTENCY: Does calculation formula match validation bounds (0-100% vs 0-1.0)?
8. ERROR HANDLING & EXCEPTION CONTRACT: Uncaught exception types (expecting KeyError, callee raises SecretNotFoundError)?
9. OPTIONAL/NONE SEMANTICS: Subscripting or attribute access on Optional[dict] or Optional[User] without None guard?
10. PERSISTENCE & TRANSACTIONS: In-memory cache updated without calling db.commit()?
11. API CONTRACT & PAYLOAD ENVELOPES: Payload shape/envelope mismatch between producer and consumer?
12. CACHE & STALENESS INVALIDATION: Database record updated without evicting cache?
13. OPERATION ORDER & SECURITY PREREQUISITES: Order fulfillment executed before webhook signature verification?
14. EDGE CASES & BOUNDARY CONDITIONS: Fence-post boundary flaw (while offset <= total_records)?
15. BATCH / SCALING FOOTPRINT: Full table scan into RAM (query.all()) for top-N ranking?

CRITICAL INSTRUCTIONS:
- If code executes intended logic correctly, return status="NO_BUG".
- DO NOT report style, linting, formatting, missing comments, or generic advice.
- Generate at most 3 concrete hypotheses.
- For each hypothesis, list exact `evidence_needed` symbols/functions/models/contracts required from repository.

Respond in JSON:
{{
  "status": "BUG | NO_BUG | NEEDS_CONTEXT",
  "hypothesis": "Clear summary of flaw",
  "bug_type": "wrong_data_flow | wrong_condition | wrong_state_transition | wrong_operation_order | cross_function",
  "additional_context_needed": [],
  "hypotheses": [
    {{
      "hypothesis": "Concrete description of the semantic defect",
      "bug_type": "return_value_mismatch | parameter_mismatch | unit_mismatch | state_transition | inverted_condition | none_assumption | validation_inconsistency | error_handling | resource_lifecycle | ordering_violation | persistence_inconsistency | contract_mismatch | edge_case_failure | scaling_issue",
      "evidence_needed": ["symbol_or_function_name_1", "symbol_or_function_name_2"]
    }}
  ]
}}
""")

STAGE1_PROMPT = PASS2_HYPOTHESIS_PROMPT


def _stage1_sync(
    function_code: str,
    function_name: str,
    file_path: str,
    frameworks: list[str] | None = None,
    repository_context: str = "",
    value_flow: str = "",
) -> dict | None:
    """Backward-compatible wrapper executing investigation for test suites & single-pass callers."""
    try:
        semantic_facts = extract_semantic_facts(
            function_code, function_name, file_path=file_path, frameworks=frameworks
        )
        if not value_flow:
            value_flow = extract_value_flow_for_function(function_code, file_path=file_path)

        prompt = STAGE1_PROMPT.format(
            function_name=function_name,
            file_path=file_path,
            semantic_facts=semantic_facts,
            value_flow=f"\n{value_flow}\n" if value_flow else "",
            repository_context=repository_context,
            function_code=function_code,
        )
        global _llm_call_count
        _llm_call_count += 1
        logger.debug("LLM call #%d", _llm_call_count)
        response = _provider.generate(prompt)
        text = response["response"].strip()
        parsed = _extract_json_block(text)
        if not parsed:
            return None

        status = str(parsed.get("status", "")).strip().upper()
        if status == "NEEDS_CONTEXT":
            needed = parsed.get("additional_context_needed", [])
            if not isinstance(needed, list):
                needed = [str(needed)]
            return {
                "status": "NEEDS_CONTEXT",
                "additional_context_needed": needed,
                "hypothesis": parsed.get("hypothesis", ""),
            }

        if status != "BUG" and not parsed.get("hypotheses"):
            return None

        confidence = float(parsed.get("confidence", 0.95) or 0.95)
        if confidence < 0.8:
            return None

        hypotheses = parsed.get("hypotheses", [])
        hypothesis = parsed.get("hypothesis", "")
        bug_type = parsed.get("bug_type", "wrong_data_flow")

        if hypotheses and isinstance(hypotheses, list):
            h = hypotheses[0]
            hypothesis = h.get("hypothesis", hypothesis)
            bug_type = h.get("bug_type", bug_type)

        if not hypothesis or str(bug_type).lower() in ("none", ""):
            return None

        cat = _map_bug_type_to_category(bug_type)
        return {
            "status": "BUG",
            "category": cat,
            "bug_type": bug_type,
            "title": f"{bug_type}: {hypothesis[:80]}",
            "hypothesis": hypothesis,
            "why": hypothesis,
            "evidence": parsed.get("evidence") or repository_context or hypothesis,
            "confidence": float(parsed.get("confidence", 0.95) or 0.95),
            "severity": parsed.get("severity") or _category_to_severity(cat),
            "execution_scenario": parsed.get("execution_scenario", ""),
            "expected_behavior": parsed.get("expected_behavior", ""),
            "actual_behavior": parsed.get("actual_behavior", ""),
            "contract_violation": parsed.get("contract_violation", ""),
            "additional_context_needed": parsed.get("additional_context_needed", []),
        }
    except Exception as e:
        logger.debug("Stage 1 sync failed: %s", e)
        return None


def _map_bug_type_to_category(bug_type: str) -> str:
    """Map granular semantic bug_type to standard pipeline category."""
    bt = (bug_type or "").lower().strip()
    if any(k in bt for k in ("return", "data_flow", "unit", "persistence", "resource", "value", "scaling")):
        return "wrong_data_flow"
    if any(k in bt for k in ("condition", "inverted", "none_assumption", "validation", "comparison", "boolean", "edge_case")):
        return "wrong_condition"
    if any(k in bt for k in ("state", "transition")):
        return "wrong_state_transition"
    if any(k in bt for k in ("order", "lifecycle", "sequence", "prerequisite", "timing")):
        return "wrong_operation_order"
    return "cross_function"


def _pass1_understand_sync(
    function_code: str,
    function_name: str,
    file_path: str,
    semantic_facts: str,
    repository_context: str,
) -> dict:
    """Pass 1: Understand target function intent and contract."""
    try:
        prompt = PASS1_UNDERSTAND_PROMPT.format(
            function_name=function_name,
            file_path=file_path,
            semantic_facts=semantic_facts,
            repository_context=repository_context,
            function_code=function_code,
        )
        global _llm_call_count
        _llm_call_count += 1
        logger.debug("LLM call #%d", _llm_call_count)
        response = _provider.generate(prompt)
        text = response["response"].strip()
        parsed = _extract_json_block(text)
        return parsed or {}
    except Exception as e:
        logger.debug("Pass 1 understand failed for %s::%s: %s", file_path, function_name, e)
        return {}


def _pass2_generate_hypotheses_sync(
    function_code: str,
    function_name: str,
    file_path: str,
    understanding: dict,
    semantic_facts: str,
    value_flow: str,
    repository_context: str,
) -> dict | None:
    """Pass 2: Generate bug hypotheses evaluating 15 semantic dimensions."""
    try:
        und_str = (
            f"Intent: {understanding.get('intent', 'N/A')}\n"
            f"Input Contract: {understanding.get('inputs_contract', 'N/A')}\n"
            f"Return Contract: {understanding.get('return_contract', 'N/A')}\n"
            f"Side Effects: {understanding.get('side_effects', 'N/A')}"
        )
        prompt = PASS2_HYPOTHESIS_PROMPT.format(
            function_name=function_name,
            file_path=file_path,
            understanding=und_str,
            semantic_facts=semantic_facts,
            value_flow=f"\n{value_flow}\n" if value_flow else "",
            repository_context=repository_context,
            function_code=function_code,
        )
        global _llm_call_count
        _llm_call_count += 1
        logger.debug("LLM call #%d", _llm_call_count)
        response = _provider.generate(prompt)
        text = response["response"].strip()
        parsed = _extract_json_block(text)
        if not parsed:
            return None

        status = str(parsed.get("status", "")).strip().upper()
        if status != "BUG":
            return None

        hypotheses = parsed.get("hypotheses", [])
        if isinstance(hypotheses, dict):
            hypotheses = [hypotheses]
        if not hypotheses or not isinstance(hypotheses, list):
            return None

        return {"status": "BUG", "hypotheses": hypotheses}
    except Exception as e:
        logger.debug("Pass 2 hypotheses failed for %s::%s: %s", file_path, function_name, e)
        return None


def _extract_json_block(text: str) -> dict | None:
    """Helper to extract JSON object from text or markdown fences."""
    try:
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            in_json = False
            for line in lines[1:]:
                if line.strip() == "```":
                    break
                if not in_json and line.strip().startswith("{"):
                    in_json = True
                if in_json:
                    json_lines.append(line)
            text = "\n".join(json_lines) if json_lines else text
        else:
            start_idx = text.find("{")
            end_idx = text.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                text = text[start_idx : end_idx + 1]
        return json.loads(text.strip())
    except Exception:
        return None


# ============================================================================
# STAGE 2: SOURCE GROUNDING (AST-based validation)
# ============================================================================

def _stage2_validate(
    function_code: str,
    candidate: dict,
    function_name: str = "",
    context_code: str = "",
) -> bool:
    """Stage 2: Verify bug claim is grounded in actual source using AST."""
    try:
        is_valid, reason = validate_candidate_against_source(
            function_code,
            function_name,
            candidate,
            context_code=context_code,
        )

        if not is_valid:
            logger.debug("Stage 2 AST validation rejected: %s", reason)
            return False

        logger.debug("Stage 2 AST validation passed: %s", reason)
        return True

    except Exception as e:
        logger.debug("Stage 2 validation error: %s", e)
        return False


# ============================================================================
# STAGE 3: ADVERSARIAL VERIFICATION (Try to DISPROVE the candidate)
# ============================================================================

STAGE3_PROMPT = """You are a code verification auditor. Your task is to verify whether a reported bug is genuine or a false positive.

SOURCE CODE:
{code}

EXTRACTED FACTS (AUTHORITATIVE):
{semantic_facts}
{repository_context}

REPORTED BUG:
- Category: {category}
- Title: {title}
- Cited Evidence: {evidence}
- Explanation: {why}

VERIFICATION CHECKS:

1. CODE EXISTENCE (Reject Hallucinations)
   - Does every referenced variable, function, and condition actually exist in the source code?
   - If the candidate references non-existent code elements -> REJECT.

2. DEFECT CONFIRMATION (Confirm Real Bugs)
   - Does the cited code contain a clear logical defect contradicting the function's purpose?
   - Inverted guard / condition:
     * Calling charge_card or granting access when validation fails (e.g. `if not card.is_valid(): charge_card(...)`) -> CONFIRM.
     * Returning True / valid for an expired token or banned user -> CONFIRM.
     * Comparing with inverted operator (e.g. `role != 'admin'` in is_admin) -> CONFIRM.
   - Wrong operation order / state transition:
     * Setting status to "completed" or "shipped" before prerequisite validation or tracking -> CONFIRM.
     * Executing an irreversible side-effect before validating inputs -> CONFIRM.
   - Wrong data flow / return value:
     * Returning intermediate subtotal instead of final total -> CONFIRM.
     * Adding discount to price instead of subtracting it -> CONFIRM.
     * Comparing plaintext password directly with hash -> CONFIRM.

3. SAFE PATTERNS (Must REJECT)
   - Deny-list: returning False or denied when a role/status IS IN a restricted set is CORRECT business logic -> REJECT.
   - Variable swap: `a, b = b, a` is CORRECT Python syntax -> REJECT.
   - String normalization: `.strip()`, `.lower()` is CORRECT sanitization -> REJECT.
   - Early guard return: returning None/False for empty/None input is CORRECT defensive programming -> REJECT.
   - Path construction: `path / 'subdir'` is CORRECT pathlib usage, NOT division -> REJECT.
   - Audit logging with error handler: logging inside a try/except that also catches failures and logs errors is CORRECT audit trail -> REJECT. But logging BEFORE a side-effect with NO error handler (so the log lies if the operation fails) IS a defect -> CONFIRM.

Answer JSON only:
{{
  "confirmed": true,
  "reason": "Confirmed: [cite the specific defect in the code]"
}}
or
{{
  "confirmed": false,
  "reason": "Rejected: [explain why this is correct code or false claim]"
}}
"""


def _stage3_verify_sync(
    function_code: str,
    candidate: dict,
    semantic_facts: str,
    repository_context: str = "",
) -> bool:
    """Stage 3: Evidence-based verification that confirms if evidence supports the bug claim."""
    try:
        repo_ctx_block = f"\nREPOSITORY CONTEXT & RELATED CODE:\n{repository_context}\n" if repository_context else ""

        prompt = STAGE3_PROMPT.format(
            title=candidate.get("title", ""),
            category=candidate.get("category", ""),
            evidence=candidate.get("evidence", ""),
            why=candidate.get("why", ""),
            semantic_facts=semantic_facts,
            repository_context=repo_ctx_block,
            code=function_code,
        )

        global _llm_call_count
        _llm_call_count += 1
        logger.debug("LLM call #%d", _llm_call_count)
        response = _provider.generate(prompt)
        text = response["response"].strip()

        # Extract JSON from response (handle markdown code fences)
        if text.startswith("```"):
            # Find the start of JSON content (after opening fence)
            lines = text.split('\n')
            # Skip the opening fence line
            json_lines = []
            in_json = False
            for line in lines[1:]:  # Skip first line (opening fence)
                if line.strip() == "```":
                    break  # Found closing fence
                if not in_json and line.strip() == "":
                    continue  # Skip empty lines before JSON
                if not in_json and line.strip().startswith('{'):
                    in_json = True
                if in_json:
                    json_lines.append(line)
            text = '\n'.join(json_lines) if json_lines else text
        else:
            # Try to find JSON object in plain text
            # Look for { ... } pattern
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                text = text[start_idx:end_idx+1]

        # Handle case where response might be just a quoted string like '"confirmed"' or '"rejected"'
        text_stripped = text.strip()
        if text_stripped.startswith('"') and text_stripped.endswith('"') and len(text_stripped) >= 2:
            # Extract the content inside quotes
            inner_content = text_stripped[1:-1]
            if inner_content in ['true', 'false']:
                # Convert to boolean
                confirmed = (inner_content == 'true')
                reason = f"Interpreted from quoted boolean: {inner_content}"
                logger.info(
                    "Stage 3 VERIFICATION %s: %s ΓÇö %s",
                    "CONFIRMED" if confirmed else "REJECTED",
                    candidate.get("title", "unknown"),
                    reason[:100],
                )
                return confirmed
            elif inner_content in ['confirmed', 'rejected']:
                # Handle quoted confirmation/rejection strings
                confirmed = (inner_content == 'confirmed')
                reason = f"Interpreted from quoted string: {inner_content}"
                logger.info(
                    "Stage 3 VERIFICATION %s: %s ΓÇö %s",
                    "CONFIRMED" if confirmed else "REJECTED",
                    candidate.get("title", "unknown"),
                    reason[:100],
                )
                return confirmed

        # Parse JSON
        try:
            parsed = json.loads(text_stripped)
            # Ensure parsed is a dictionary and has the confirmed key
            if isinstance(parsed, dict) and "confirmed" in parsed:
                confirmed = parsed.get("confirmed", False)
                reason = str(parsed.get("reason", ""))

                # Reconcile if model copied boolean from prompt template opposite of explanation
                reason_lower = reason.lower()
                if not confirmed and (reason_lower.startswith("confirmed") or "defect is confirmed" in reason_lower or "bug is confirmed" in reason_lower) and "not confirmed" not in reason_lower:
                    confirmed = True
                elif confirmed and (reason_lower.startswith("rejected") or any(phrase in reason_lower for phrase in ("false positive", "not a bug"))):
                    confirmed = False

                if not confirmed:
                    logger.info(
                        "Stage 3 VERIFICATION REJECTED: %s ΓÇö %s",
                        candidate.get("title", "unknown"),
                        reason[:100],
                    )
                else:
                    logger.info(
                        "Stage 3 VERIFICATION CONFIRMED: %s ΓÇö %s",
                        candidate.get("title", "unknown"),
                        reason[:100],
                    )

                return confirmed
            else:
                # If it's not a dict or doesn't have confirmed key, treat as rejection
                logger.debug(
                    "Stage 3: Parsed JSON is not a valid object: %s",
                    parsed,
                )
                return False
        except json.JSONDecodeError as e:
            logger.debug("Stage 3 JSON parse failed: %s", e)
            return False

    except json.JSONDecodeError as e:
        logger.debug("Stage 3 JSON parse failed: %s", e)
        return False
    except Exception as e:
        logger.debug("Stage 3 adversarial verification failed: %s", e)
        return False


# ============================================================================
# ROUND 3: ADVERSARIAL DISPROVE & EVIDENCE CHAIN PROMPT
# ============================================================================

ROUND3_PROMPT = """You are a senior adversarial code auditor.
Your job is to TRY TO DISPROVE the proposed bug candidate using the source code and repository facts.

ASSUME THE PROPOSED BUG IS WRONG.
Analyze how the code might actually be correct:
- Is this an intentional deny-list or allow-list pattern?
- Is there a guard clause or early return preventing failure?
- Does caller handle or sanitize this value?
- Is this standard framework convention or idiomatic pattern?
- Does it fail in reality or only under hypothetical, impossible inputs?

SOURCE CODE:
{code}

EXTRACTED FACTS:
{semantic_facts}
{repository_context}

PROPOSED BUG CANDIDATE:
- Category: {category}
- Title: {title}
- Hypothesis: {hypothesis}
- Stated Violation: {contract_violation}
- Concrete Scenario: {execution_scenario}
- Cited Elements: {evidence}

DECISION:
1. Can you DISPROVE this bug with evidence from the code/context?
   If YES, mark disproved=true and explain why the code is actually correct or why the bug is hypothetical.
2. If the bug CANNOT be disproved and is a PROVEN concrete semantic defect with a clear execution failure:
   Mark disproved=false and construct an explicit step-by-step EVIDENCE CHAIN.

Respond in JSON:
{{
  "disproved": true | false,
  "disprove_reason": "Explanation if disproved, or empty string",
  "exact_file": "{file_path}",
  "exact_symbol": "symbol_name",
  "exact_line": 1,
  "concrete_execution_scenario": "Concrete inputs and call sequence that trigger failure",
  "evidence_chain": [
    "Step 1: target calls callee()",
    "Step 2: callee contract returns X",
    "Step 3: target assumes Y without conversion",
    "Step 4: consumer fails or misinterprets value"
  ],
  "root_cause": "The fundamental semantic flaw",
  "expected_behavior": "What the contract/intent required",
  "actual_behavior": "What actually executes",
  "confidence": 0.95
}}

If disproved:
{{
  "disproved": true,
  "disprove_reason": "Explain why this code is correct or unproven",
  "evidence_chain": []
}}
"""


def _round3_adversarial_sync(
    function_code: str,
    candidate: dict,
    semantic_facts: str,
    repository_context: str = "",
    file_path: str = "",
) -> dict | None:
    """Round 3: Adversarial disprove analysis and evidence chain generation."""
    try:
        repo_ctx_block = f"\nREPOSITORY CONTEXT & RELATED CODE:\n{repository_context}\n" if repository_context else ""
        prompt = ROUND3_PROMPT.format(
            code=function_code,
            semantic_facts=semantic_facts,
            repository_context=repo_ctx_block,
            category=candidate.get("category", ""),
            title=candidate.get("title", ""),
            hypothesis=candidate.get("hypothesis", ""),
            contract_violation=candidate.get("contract_violation", ""),
            execution_scenario=candidate.get("execution_scenario", ""),
            evidence=candidate.get("evidence", ""),
            file_path=file_path,
        )

        global _llm_call_count
        _llm_call_count += 1
        logger.debug("LLM call #%d", _llm_call_count)
        response = _provider.generate(prompt)
        text = response["response"].strip()

        # Extract JSON
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            in_json = False
            for line in lines[1:]:
                if line.strip() == "```":
                    break
                if not in_json and line.strip() == "":
                    continue
                if not in_json and line.strip().startswith("{"):
                    in_json = True
                if in_json:
                    json_lines.append(line)
            text = "\n".join(json_lines) if json_lines else text
        else:
            start_idx = text.find("{")
            end_idx = text.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                text = text[start_idx : end_idx + 1]

        parsed = json.loads(text.strip())
        disproved = parsed.get("disproved")
        if disproved is True:
            logger.info("Round 3: Candidate disproved ΓÇö %s", parsed.get("disprove_reason", "no reason"))
            return None

        # Evidence chain must be present
        chain = parsed.get("evidence_chain", [])
        if isinstance(chain, str):
            chain = [line.strip() for line in chain.split("\n") if line.strip()]
        elif not isinstance(chain, list):
            chain = []

        if not chain:
            logger.info("Round 3: Candidate rejected ΓÇö missing evidence chain")
            return None

        # Update candidate with Round 3 findings
        candidate["evidence_chain"] = chain
        candidate["root_cause"] = parsed.get("root_cause", candidate.get("hypothesis", ""))
        candidate["exact_file"] = parsed.get("exact_file", file_path)
        candidate["exact_symbol"] = parsed.get("exact_symbol", candidate.get("function_name", ""))
        candidate["concrete_execution_scenario"] = parsed.get(
            "concrete_execution_scenario", candidate.get("execution_scenario", "")
        )
        candidate["expected_behavior"] = parsed.get("expected_behavior", candidate.get("expected_behavior", ""))
        candidate["actual_behavior"] = parsed.get("actual_behavior", candidate.get("actual_behavior", ""))
        if parsed.get("confidence") is not None:
            candidate["confidence"] = float(parsed["confidence"])
        exact_line = parsed.get("exact_line")
        if isinstance(exact_line, int) and exact_line > 0:
            candidate["line"] = exact_line

        return candidate
    except Exception as e:
        logger.debug("Round 3 adversarial analysis failed: %s", e)
        # Fallback to candidate with synthesized chain if parse failed
        candidate["evidence_chain"] = [
            f"Observed behavior: {candidate.get('actual_behavior', candidate.get('why', ''))}",
            f"Expected contract: {candidate.get('expected_behavior', 'Correct execution')}",
            f"Violation: {candidate.get('contract_violation', 'Logic flaw')}",
        ]
        return candidate


# ============================================================================
# CONTROLLED INVESTIGATION BUDGET
# ============================================================================

@dataclass
class InvestigationBudget:
    """Enforces strict, bounded limits on semantic investigation rounds."""
    max_rounds: int = 3
    max_chars_per_round: int = 4000
    max_total_chars: int = 10000
    max_symbols: int = 10
    max_files: int = 5

    current_round: int = 0
    total_chars_used: int = 0
    retrieved_symbols: set = field(default_factory=set)
    files_touched: set = field(default_factory=set)

    def can_proceed(self) -> bool:
        return (
            self.current_round < self.max_rounds
            and self.total_chars_used < self.max_total_chars
            and len(self.retrieved_symbols) < self.max_symbols
            and len(self.files_touched) < self.max_files
        )

    def record_usage(
        self,
        chars: int,
        symbols: list[str] | None = None,
        file_paths: list[str] | None = None,
    ) -> None:
        self.total_chars_used += chars
        if symbols:
            for s in symbols:
                if len(self.retrieved_symbols) < self.max_symbols:
                    self.retrieved_symbols.add(s)
        if file_paths:
            for f in file_paths:
                if len(self.files_touched) < self.max_files:
                    self.files_touched.add(f)


# ============================================================================
# MAIN ENTRY POINT: 3-ROUND CONTROLLED INVESTIGATION LOOP
# ============================================================================

async def detect_semantic_bug(
    function_code: str,
    function_name: str,
    file_path: str,
    frameworks: list[str] | None = None,
    repo_index: RepositoryIndex | None = None,
) -> dict | None:
    """
    Controlled 5-pass semantic investigation loop with PRE-FILTERING:
    Pass 0: Deterministic Candidate Selection (0 LLM cost, filters trivial functions)
    Pass 1: Function Understanding (intent, input/return contract, side effects)
    Pass 2: 15-Dimension Bug Hypothesis Generation (early exit if NO_BUG)
    Pass 3: Evidence-Driven Targeted Context Retrieval (resolve evidence_needed)
    Pass 4: Evidence Grounding & Verification
    Pass 5: Deterministic AST Grounding & Rule Deduplication
    """
    # -------------------------------------------------------------------------
    # PASS 0: Deterministic Candidate Pre-Filter (ZERO LLM COST)
    # -------------------------------------------------------------------------
    norm_fp = file_path.replace("\\", "/")
    candidate_score = score_function_candidate(
        code=function_code,
        function_name=function_name,
        file_path=norm_fp,
        repo_index=repo_index,
    )
    if not candidate_score.is_candidate:
        logger.debug(
            "Semantic v1: PRE-FILTER SKIP %s::%s (score %d < threshold %d)",
            norm_fp, function_name, candidate_score.score, config.SEMANTIC_CANDIDATE_SCORE_THRESHOLD
        )
        return None
    
    logger.debug(
        "Semantic v1: PRE-FILTER PASS %s::%s (score %d, reasons: %s)",
        norm_fp, function_name, candidate_score.score, "; ".join(candidate_score.reasons[:2])
    )
    
    loop = asyncio.get_event_loop()
    budget = InvestigationBudget()

    semantic_facts = extract_semantic_facts(
        function_code, function_name, file_path=file_path, frameworks=frameworks, repo_index=repo_index
    )
    value_flow = extract_value_flow_for_function(
        function_code, file_path=file_path, repo_index=repo_index
    )

    context_pkg = retrieve_context_for_function(
        target_func_name=function_name,
        target_code=function_code,
        file_path=file_path,
        repo_index=repo_index,
    )
    repo_ctx_formatted = context_pkg.formatted_context_block

    if repo_index and repo_index.summary:
        summary_text = (
            f"### REPOSITORY SUMMARY\n"
            f"- Architecture: {repo_index.summary.architecture_summary}\n"
            f"- Domains: {', '.join(repo_index.summary.primary_domains)}\n"
            f"- Frameworks: {', '.join(repo_index.summary.frameworks)}\n\n"
        )
        repo_ctx_formatted = summary_text + repo_ctx_formatted

    if len(repo_ctx_formatted) > budget.max_chars_per_round:
        repo_ctx_formatted = repo_ctx_formatted[:budget.max_chars_per_round] + "\n...[truncated to round budget]"

    # -------------------------------------------------------------------------
    # PASS 1: Function Understanding
    # -------------------------------------------------------------------------
    understanding = await loop.run_in_executor(
        _executor,
        _pass1_understand_sync,
        function_code,
        function_name,
        file_path,
        semantic_facts,
        repo_ctx_formatted,
    )

    # -------------------------------------------------------------------------
    # PASS 2: 15-Dimension Hypothesis Generation
    # -------------------------------------------------------------------------
    p2_result = await loop.run_in_executor(
        _executor,
        _pass2_generate_hypotheses_sync,
        function_code,
        function_name,
        file_path,
        understanding,
        semantic_facts,
        value_flow,
        repo_ctx_formatted,
    )

    if not p2_result or p2_result.get("status") != "BUG":
        # NO_BUG reported in Pass 2 -> STOP immediately (saves LLM calls)
        return None

    hypotheses = p2_result.get("hypotheses", [])
    if not hypotheses:
        return None

    primary_hypothesis = hypotheses[0]
    needed_symbols = primary_hypothesis.get("evidence_needed", [])

    # -------------------------------------------------------------------------
    # PASS 3: Evidence-Driven Targeted Context Retrieval
    # -------------------------------------------------------------------------
    additional_blocks = []
    retrieved_syms = []
    retrieved_files = []

    if repo_index and needed_symbols:
        for sym in needed_symbols:
            if not sym or not isinstance(sym, str):
                continue
            sym_clean = sym.strip()
            fn_entry = repo_index.find_function(sym_clean, current_file=file_path)
            if fn_entry:
                code_str = fn_entry.code_snippet or getattr(fn_entry, "code", "")
                if len(code_str) > 1000:
                    code_str = code_str[:1000] + "\n..."
                additional_blocks.append(
                    f"### Resolved Callee/Caller ({fn_entry.name}):\n"
                    f"File: {fn_entry.file_path}\n"
                    f"Docstring: {fn_entry.docstring}\n"
                    f"Returns: {', '.join(fn_entry.returns) if fn_entry.returns else 'N/A'}\n"
                    f"Exceptions: {', '.join(fn_entry.exceptions) if fn_entry.exceptions else 'N/A'}\n"
                    f"```python\n{code_str}\n```"
                )
                retrieved_syms.append(fn_entry.name)
                retrieved_files.append(fn_entry.file_path)
                continue

            cls_entry = repo_index.find_class(sym_clean)
            if cls_entry:
                additional_blocks.append(
                    f"### Resolved Class ({cls_entry.name}):\n"
                    f"File: {cls_entry.file_path}\n"
                    f"Methods: {', '.join(cls_entry.methods)}\n"
                    f"Attributes: {', '.join(cls_entry.attributes)}\n"
                )
                retrieved_syms.append(cls_entry.name)
                retrieved_files.append(cls_entry.file_path)

    targeted_evidence = "\n\n".join(additional_blocks) if additional_blocks else repo_ctx_formatted

    # Synthesize candidate dictionary for Pass 4 verification
    bug_type = primary_hypothesis.get("bug_type", "wrong_data_flow")
    hyp_text = primary_hypothesis.get("hypothesis", "")
    category = _map_bug_type_to_category(bug_type)

    candidate = {
        "status": "BUG",
        "category": category,
        "bug_type": bug_type,
        "title": f"{bug_type}: {hyp_text[:80]}",
        "hypothesis": hyp_text,
        "why": hyp_text,
        "evidence": targeted_evidence,
        "contract_violation": hyp_text,
        "execution_scenario": f"Execution of {function_name} with target repository context",
        "expected_behavior": "Execution according to intent and caller contract",
        "actual_behavior": hyp_text,
    }

    # -------------------------------------------------------------------------
    # PASS 4: Evidence Grounding & Adversarial Verification
    # -------------------------------------------------------------------------
    verified_candidate = await loop.run_in_executor(
        _executor,
        _round3_adversarial_sync,
        function_code,
        candidate,
        semantic_facts,
        targeted_evidence,
        file_path,
    )

    if not verified_candidate:
        logger.info("Pass 4: Candidate rejected by adversarial check in %s::%s", file_path, function_name)
        return None

    # -------------------------------------------------------------------------
    # PASS 5: Deterministic AST Grounding & Stage 3 Verification
    # -------------------------------------------------------------------------
    if not _stage2_validate(
        function_code,
        verified_candidate,
        function_name=function_name,
        context_code=targeted_evidence,
    ):
        logger.info("Pass 5: AST validation rejected candidate in %s::%s", file_path, function_name)
        return None

    is_stage3_confirmed = await loop.run_in_executor(
        _executor,
        _stage3_verify_sync,
        function_code,
        verified_candidate,
        semantic_facts,
        targeted_evidence,
    )
    if not is_stage3_confirmed:
        logger.info("Pass 5: Verification rejected candidate in %s::%s", file_path, function_name)
        return None

    category = verified_candidate.get("category", "wrong_data_flow")
    confidence = verified_candidate.get("confidence", 0.95)
    severity = verified_candidate.get("severity") or _category_to_severity(category)

    logger.info(
        "ACCEPTED: Semantic bug confirmed in %s::%s after %d rounds (category: %s)",
        file_path, function_name, budget.current_round, category
    )

    return {
        "function_name": function_name,
        "file_path": file_path,
        "title": verified_candidate.get("title", ""),
        "description": verified_candidate.get("why", ""),
        "confidence": confidence,
        "severity": severity,
        "category": category,
        "evidence": {
            "source": "local_llm",
            "category": category,
            "bug_type": verified_candidate.get("bug_type", category),
            "code_evidence": verified_candidate.get("evidence", ""),
            "raw_evidence": verified_candidate.get("raw_evidence", []),
            "evidence_chain": verified_candidate.get("evidence_chain", []),
            "root_cause": verified_candidate.get("root_cause", ""),
            "line": verified_candidate.get("line"),
            "exact_symbol": verified_candidate.get("exact_symbol", function_name),
            "exact_file": verified_candidate.get("exact_file", file_path),
            "hypothesis": verified_candidate.get("hypothesis", ""),
            "execution_scenario": verified_candidate.get(
                "concrete_execution_scenario", verified_candidate.get("execution_scenario", "")
            ),
            "expected_behavior": verified_candidate.get("expected_behavior", ""),
            "actual_behavior": verified_candidate.get("actual_behavior", ""),
            "contract_violation": verified_candidate.get("contract_violation", ""),
            "investigation_rounds": budget.current_round,
            "verification_passed": True,
        },
    }


def _category_to_severity(category: str) -> str:
    """Map bug category to severity level."""
    category_map = {
        "wrong_data_flow": "high",
        "wrong_condition": "high",
        "wrong_state_transition": "high",
        "wrong_operation_order": "high",
        "cross_function": "medium",
    }
    return category_map.get(category, "medium")


async def detect_semantic_bug_v2(
    function_code: str,
    function_name: str,
    file_path: str,
    frameworks: list[str] | None = None,
    repo_index: RepositoryIndex | None = None,
) -> dict | None:
    """
    Enhanced Semantic Bug Detection Pipeline (v2):
    1. Deterministic Candidate Selection (skips functions scoring < 3, 0 LLM cost)
    2. Cross-File Evidence Assembly (callers, callees, shared module-level state)
    3. OpenAI Strong Reasoner (if OPENAI_API_KEY configured)
    4. Deterministic Evidence Validation (verifies symbols, AST order, facts)
    5. Graceful fallback to local Qwen with fixed Stage 3 if OpenAI unavailable
    """
    # Step 1: Deterministic candidate pre-filter
    norm_fp = file_path.replace("\\", "/")
    candidate_score = score_function_candidate(
        code=function_code,
        function_name=function_name,
        file_path=norm_fp,
        repo_index=repo_index,
    )
    if not candidate_score.is_candidate:
        if config.SEMANTIC_DEBUG:
            logger.info(
                "Semantic v2: Skipping %s::%s (score %d < %d)",
                norm_fp, function_name, candidate_score.score, config.SEMANTIC_CANDIDATE_SCORE_THRESHOLD
            )
        return None

    # Step 2: Assemble cross-file evidence packet
    qualname = f"{norm_fp}::{function_name}"
    if repo_index:
        packet = build_cross_file_evidence(qualname, repo_index)
    else:
        packet = EvidencePacket(
            target_qualname=qualname,
            target_file=norm_fp,
            target_lines=(1, len(function_code.splitlines())),
            target_source=function_code,
            is_complete=True,
        )

    # Step 3: OpenAI Strong Reasoner (if configured)
    if config.OPENAI_API_KEY:
        try:
            openai_res = await reason_about_semantic_candidate(packet)
            if openai_res and openai_res.status == "BUG":
                # Step 4: Deterministic Post-LLM Fact Validation
                target_fn = None
                if repo_index:
                    target_fn = repo_index.functions_by_qualname.get(qualname) or repo_index.find_function(function_name, current_file=norm_fp)
                
                confidence = openai_res.confidence
                validated_claims = []
                if target_fn and repo_index:
                    val_res = validate_semantic_finding(openai_res, repo_index, target_fn)
                    if not val_res.is_valid:
                        logger.info(
                            "Semantic v2: OpenAI finding rejected by deterministic validator for %s::%s: %s",
                            norm_fp, function_name, val_res.rejected_claims
                        )
                        return None
                    confidence += val_res.confidence_adjustment
                    validated_claims = val_res.validated_claims

                if confidence >= config.SEMANTIC_MIN_CONFIDENCE:
                    logger.info(
                        "ACCEPTED (Semantic v2 OpenAI): %s::%s (%s, conf=%.2f)",
                        norm_fp, function_name, openai_res.bug_type, confidence
                    )
                    return {
                        "function_name": function_name,
                        "file_path": norm_fp,
                        "title": openai_res.title or f"Semantic Defect in {function_name}()",
                        "description": openai_res.explanation,
                        "confidence": confidence,
                        "severity": "high",
                        "category": openai_res.bug_type.lower(),
                        "evidence": {
                            "source": "openai_reasoner",
                            "category": openai_res.bug_type.lower(),
                            "bug_type": openai_res.bug_type,
                            "code_evidence": openai_res.evidence,
                            "execution_path": openai_res.execution_path,
                            "expected_behavior": openai_res.expected_behavior,
                            "actual_behavior": openai_res.actual_behavior,
                            "affected_files": openai_res.affected_files,
                            "validated_claims": validated_claims,
                            "verification_passed": True,
                        },
                    }
                else:
                    logger.info(
                        "Semantic v2: Confidence %.2f below threshold %.2f for %s::%s",
                        confidence, config.SEMANTIC_MIN_CONFIDENCE, norm_fp, function_name
                    )
                    return None
            elif openai_res and openai_res.status == "NO_BUG":
                logger.info("Semantic v2: OpenAI confirmed NO_BUG for %s::%s", norm_fp, function_name)
                return None
        except Exception as e:
            logger.warning("Semantic v2: OpenAI stage encountered error: %s (falling back to local pipeline)", e)

    # Step 5: Fallback to local Qwen pipeline (with fixed Stage 3)
    return await detect_semantic_bug(
        function_code=function_code,
        function_name=function_name,
        file_path=file_path,
        frameworks=frameworks,
        repo_index=repo_index,
    )

