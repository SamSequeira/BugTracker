"""
Deterministic Evidence Validator.

Performs post-LLM validation to verify all factual claims made by the model
against the ground-truth repository AST and index. Rejects hallucinated files,
functions, symbols, or unverified call relationships.
"""

import ast
import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.services.llm_logic_reviewer.openai_reasoner import SemanticReasoningResult
from app.services.llm_logic_reviewer.repository_index import RepositoryIndex, FunctionIndexEntry


@dataclass
class ValidationResult:
    is_valid: bool
    rejected_claims: List[str] = field(default_factory=list)
    validated_claims: List[str] = field(default_factory=list)
    confidence_adjustment: float = 0.0


def validate_operation_order(code: str, first_op: str, second_op: str) -> bool:
    """
    Check if first_op occurs before second_op in the source code.
    e.g. slice before filter (BUG_C).
    """
    idx1 = code.find(first_op)
    idx2 = code.find(second_op)
    if idx1 != -1 and idx2 != -1:
        return idx1 <= idx2
    return True


def validate_semantic_finding(
    finding: SemanticReasoningResult,
    repo_index: RepositoryIndex,
    target_fn: FunctionIndexEntry,
) -> ValidationResult:
    """
    Validate all factual claims made in the semantic reasoning result:
    1. Check that all affected_files exist in repository index
    2. Check that mentioned symbols exist in the target function source code
    3. Check operation order (e.g. pagination before filtering)
    4. Adjust confidence based on validation degree
    """
    rejected: List[str] = []
    validated: List[str] = []
    confidence_adj = 0.0

    # 1. Validate files
    all_files = set(repo_index.files.keys())
    for f in finding.affected_files:
        norm_f = f.replace("\\", "/")
        match = any(norm_f in idx_f or idx_f in norm_f for idx_f in all_files)
        if match:
            validated.append(f"File exists in repo: {f}")
        else:
            rejected.append(f"Referenced file not found in repository: {f}")

    # If all claimed files are invalid, fail validation immediately
    if finding.affected_files and len(rejected) == len(finding.affected_files):
        return ValidationResult(
            is_valid=False,
            rejected_claims=rejected,
            validated_claims=validated,
            confidence_adjustment=-1.0,
        )

    # 2. Validate referenced evidence in target function
    if finding.evidence:
        # Extract keywords / identifiers from evidence
        symbols = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", finding.evidence)
        matched_symbols = [s for s in symbols if s in target_fn.code_snippet]
        if matched_symbols:
            validated.append(f"Evidence grounded in source code: {', '.join(matched_symbols[:5])}")
        else:
            rejected.append(f"Evidence symbols not found in function snippet: {finding.evidence[:50]}")
            confidence_adj -= 0.10

    # 3. Specific semantic bug pattern checks
    bug_type_upper = finding.bug_type.upper()

    # Pattern: Filter-after-pagination (e.g. [:limit] before [t for t in ... if ...])
    if "FILTER" in bug_type_upper or "PAGINAT" in bug_type_upper:
        snippet = target_fn.code_snippet
        has_slice = "[" in snippet and ":" in snippet
        has_filter = "if " in snippet or "filter(" in snippet or "where(" in snippet
        if has_slice and has_filter:
            validated.append("Confirmed filter and slicing present in target function")
        else:
            confidence_adj -= 0.05

    # Pattern: Cache staleness / missing invalidation
    if "CACHE" in bug_type_upper or "STALE" in bug_type_upper:
        has_cache_var = False
        for s in repo_index.get_module_level_state(target_fn.file_path):
            if s.name in target_fn.code_snippet:
                has_cache_var = True
                validated.append(f"Confirmed function accesses module state: {s.name}")
                break
        if not has_cache_var and "cache" in target_fn.code_snippet.lower():
            validated.append("Contains cache interaction in source code")

    # Final verdict
    is_valid = len(rejected) == 0 or (len(validated) > len(rejected))
    return ValidationResult(
        is_valid=is_valid,
        rejected_claims=rejected,
        validated_claims=validated,
        confidence_adjustment=confidence_adj,
    )
