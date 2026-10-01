"""
Bounded semantic LLM review pipeline.

Pipeline:
    Component 1  - Discover source files
    Component 2  - Extract functions
    Component 3  - Build function context
    Component 4  - Conservative pre-filter
    Component 5  - LLM semantic detection
    Component 6  - Parse LLM response
    Component 7  - Validate finding against source
    Component 8  - Deduplication [SKIPPED FOR NOW]
    Component 9  - Persist accepted finding

The pipeline is intentionally sequential:

    file -> function -> context -> LLM -> parse -> validate -> persist

No component runs concurrently.
No rule-based findings are modified.
No deduplication is performed at this stage.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from data.dbconnection.session import AsyncSessionLocal
from app.models.candidate_issues import CandidateIssue
from app.models.issue_recommendation import IssueRecommendation

from app.services.llm_logic_reviewer.llm_provider import (
    create_llm_provider,
)

from app.services.llm_logic_reviewer.semantic_pipeline import (
    SemanticReviewConfig,
    build_context,
    build_detection_prompt,
    discover_source_files,
    extract_functions,
    parse_llm_finding,
    validate_finding,
)


logger = logging.getLogger(__name__)


async def run_llm_logic_review(
    analysis_run_id: str,
    repository_path: str,
    max_functions: int | None = None,
) -> dict[str, Any]:
    """
    Run the complete bounded semantic LLM review pipeline.

    Execution order:

        1. Discover files
        2. Extract functions
        3. Build context
        4. Pre-filter
        5. LLM detection
        6. Parse response
        7. Validate finding
        8. Deduplication -- SKIPPED
        9. Persist finding

    Each function is processed completely before the next function starts.

    Returns:
        Dictionary containing pipeline metrics.
    """

    print()
    print("=" * 80)
    print("LLM SEMANTIC REVIEW PIPELINE")
    print("=" * 80)
    print(f"Repository : {repository_path}")
    print(f"Analysis ID: {analysis_run_id}")
    print("=" * 80)

    # ==================================================================
    # CONFIGURATION
    # ==================================================================

    config = SemanticReviewConfig()

    if max_functions is not None:
        config = SemanticReviewConfig(
            max_files=config.max_files,
            max_source_chars=config.max_source_chars,
            max_functions=max_functions,
            max_context_chars=config.max_context_chars,
            max_context_depth=config.max_context_depth,
            min_confidence=config.min_confidence,
        )

    repo_root = Path(repository_path).resolve()

    if not repo_root.exists():
        raise FileNotFoundError(
            f"Repository path does not exist: {repo_root}"
        )

    if not repo_root.is_dir():
        raise NotADirectoryError(
            f"Repository path is not a directory: {repo_root}"
        )

    # ==================================================================
    # METRICS
    # ==================================================================

    metrics: dict[str, Any] = {
        # Component 1
        "files_discovered": 0,
        "files_selected": 0,

        # Component 2
        "functions_extracted": 0,
        "functions_checked": 0,

        # Component 3
        "contexts_built": 0,

        # Component 4
        "functions_prefiltered": 0,

        # Component 5
        "llm_calls_made": 0,
        "llm_failures": 0,

        # Component 6
        "responses_parsed": 0,
        "parse_failures": 0,

        # Component 7
        "findings_candidate": 0,
        "findings_validated": 0,
        "findings_rejected": 0,
        "validation_uncertain": 0,

        # Component 8
        "deduplication_skipped": True,

        # Component 9
        "findings_persisted": 0,
        "persistence_failures": 0,
    }

    # ==================================================================
    # CREATE LLM PROVIDER ONCE
    # ==================================================================

    try:
        provider = create_llm_provider()

    except Exception as exc:
        logger.exception(
            "Failed to initialize LLM provider"
        )

        raise RuntimeError(
            f"Could not initialize LLM provider: {exc}"
        ) from exc

    provider_type = type(provider).__name__

    print()
    print("[PIPELINE] LLM provider initialized")
    print(f"           Provider: {provider_type}")

    # ==================================================================
    # COMPONENT 1
    # DISCOVER SOURCE FILES
    # ==================================================================

    print()
    print("=" * 80)
    print("COMPONENT 1 — SOURCE FILE DISCOVERY")
    print("=" * 80)

    try:
        selected_files = discover_source_files(
            repo_root,
            config,
        )

    except Exception as exc:
        logger.exception(
            "Source file discovery failed"
        )

        raise RuntimeError(
            f"Component 1 failed during source discovery: {exc}"
        ) from exc

    metrics["files_discovered"] = len(selected_files)
    metrics["files_selected"] = len(selected_files)

    print(
        f"Files selected: {len(selected_files)}"
    )

    for index, selected_file in enumerate(
        selected_files,
        start=1,
    ):
        print(
            f"  [{index}] "
            f"{selected_file.relative_path} "
            f"({selected_file.source_chars} chars)"
        )

    if not selected_files:

        print()
        print(
            "No eligible application source files were found."
        )
        print(
            "Stopping semantic pipeline."
        )

        return metrics

    # ==================================================================
    # COMPONENT 2
    # EXTRACT FUNCTIONS
    # ==================================================================

    print()
    print("=" * 80)
    print("COMPONENT 2 — FUNCTION EXTRACTION")
    print("=" * 80)

    all_functions = []

    for selected_file in selected_files:

        try:
            functions = extract_functions(
                selected_file
            )

        except Exception as exc:

            logger.warning(
                "Function extraction failed for %s: %s",
                selected_file.relative_path,
                exc,
            )

            print(
                f"  ERROR: Could not extract functions from "
                f"{selected_file.relative_path}"
            )

            continue

        all_functions.extend(functions)

        print(
            f"  {selected_file.relative_path}: "
            f"{len(functions)} functions"
        )

    metrics["functions_extracted"] = len(
        all_functions
    )

    print()
    print(
        f"Total functions extracted: "
        f"{len(all_functions)}"
    )

    if not all_functions:

        print(
            "No functions were extracted."
        )
        print(
            "Stopping semantic pipeline."
        )

        return metrics

    # ==================================================================
    # APPLY GLOBAL FUNCTION LIMIT ONCE
    # ==================================================================

    if config.max_functions > 0:

        functions_to_check = all_functions[
            : config.max_functions
        ]

    else:

        functions_to_check = all_functions

    print(
        f"Functions selected for LLM review: "
        f"{len(functions_to_check)}"
    )

    # ==================================================================
    # COMPONENTS 3-9
    #
    # Each function passes through the complete pipeline before the
    # next function starts.
    # ==================================================================

    for function_index, function in enumerate(
        functions_to_check,
        start=1,
    ):

        metrics["functions_checked"] += 1

        print()
        print("-" * 80)
        print(
            f"FUNCTION {function_index}/"
            f"{len(functions_to_check)}"
        )
        print("-" * 80)

        print(
            f"File      : {function.file_path}"
        )

        print(
            f"Function  : {function.qualified_name}"
        )

        print(
            f"Lines     : "
            f"{function.start_line}-"
            f"{function.end_line}"
        )

        # ==============================================================
        # COMPONENT 3
        # BUILD CONTEXT
        # ==============================================================

        print()
        print(
            "[COMPONENT 3] Building context..."
        )

        try:

            context = build_context(
                function,
                all_functions,
                config,
                repo_root=str(repo_root),
            )

        except Exception as exc:

            logger.warning(
                "Context building failed for %s: %s",
                function.qualified_name,
                exc,
            )

            print(
                f"  FAILED: {exc}"
            )

            continue

        metrics["contexts_built"] += 1

        print(
            f"  Context sections: "
            f"{', '.join(context.included)}"
        )

        print(
            f"  Context chars: "
            f"{len(context.text)}"
        )

        print(
            f"  Context truncated: "
            f"{context.truncated}"
        )

        # ==============================================================
        # COMPONENT 4
        # CONSERVATIVE PRE-FILTER
        # ==============================================================

        print()
        print(
            "[COMPONENT 4] Pre-filter..."
        )

        """
        The pre-filter intentionally remains conservative.

        The LLM is responsible for detecting semantic bugs that
        deterministic rules may miss.

        Therefore functions are NOT rejected merely because they:

            - are short
            - contain no obvious bug
            - lack specific keywords
            - lack a specific AST pattern

        Every extracted function currently passes through.
        """

        metrics["functions_prefiltered"] += 1

        print(
            "  Decision: PASS"
        )

        print(
            "  Reason  : Conservative semantic review"
        )

        # ==============================================================
        # COMPONENT 5
        # LLM SEMANTIC DETECTION
        # ==============================================================

        print()
        print(
            "[COMPONENT 5] Sending function to LLM..."
        )

        try:

            prompt = build_detection_prompt(
                function,
                context,
            )

        except Exception as exc:

            logger.warning(
                "Prompt construction failed for %s: %s",
                function.qualified_name,
                exc,
            )

            print(
                f"  Prompt construction FAILED: {exc}"
            )

            continue

        metrics["llm_calls_made"] += 1

        print(
            f"  Prompt chars: {len(prompt)}"
        )

        try:

            # ----------------------------------------------------------
            # Synchronous provider call.
            #
            # Function N must finish its LLM call before function N+1
            # starts.
            # ----------------------------------------------------------

            response_dict = provider.generate(
                prompt
            )

        except Exception as exc:

            metrics["llm_failures"] += 1

            logger.warning(
                "LLM provider raised an exception for %s: %s",
                function.qualified_name,
                exc,
            )

            print(
                f"  LLM FAILED: {exc}"
            )

            continue

        # --------------------------------------------------------------
        # Validate provider result
        # --------------------------------------------------------------

        if not isinstance(
            response_dict,
            dict,
        ):

            metrics["llm_failures"] += 1

            print(
                "  LLM FAILED: provider returned "
                "non-dictionary result"
            )

            continue

        response = response_dict.get(
            "response",
            "",
        )

        provider_error = response_dict.get(
            "error"
        )

        if provider_error and not response:

            metrics["llm_failures"] += 1

            logger.warning(
                "LLM provider returned an error for %s: %s",
                function.qualified_name,
                provider_error,
            )

            print(
                f"  LLM FAILED: {provider_error}"
            )

            continue

        if not isinstance(
            response,
            str,
        ):

            metrics["llm_failures"] += 1

            print(
                "  LLM FAILED: provider response "
                "was not a string"
            )

            continue

        if not response.strip():

            metrics["llm_failures"] += 1

            print(
                "  LLM FAILED: empty response"
            )

            continue

        print(
            f"  Response received: "
            f"{len(response)} chars"
        )

        response_preview = response.strip()

        if len(response_preview) > 1000:

            response_preview = (
                response_preview[:1000]
                + "\n..."
            )

        print()
        print(
            "  LLM response:"
        )

        print(
            "  " + "-" * 70
        )

        for line in response_preview.splitlines():

            print(
                f"  {line}"
            )

        print(
            "  " + "-" * 70
        )

        # ==============================================================
        # COMPONENT 6
        # PARSE LLM RESPONSE
        # ==============================================================

        print()
        print(
            "[COMPONENT 6] Parsing LLM response..."
        )

        try:

            candidate = parse_llm_finding(
                response
            )

        except Exception as exc:

            logger.warning(
                "LLM response parser crashed for %s: %s",
                function.qualified_name,
                exc,
            )

            metrics["parse_failures"] += 1

            print(
                f"  Parser FAILED: {exc}"
            )

            continue

        if candidate is None:

            metrics["parse_failures"] += 1

            print(
                "  Parse result: FAILED"
            )

            print(
                "  Reason: response was not a valid "
                "single JSON object"
            )

            continue

        metrics["responses_parsed"] += 1

        print(
            "  Parse result: SUCCESS"
        )

        print(
            f"  bug_found: "
            f"{candidate.get('bug_found')}"
        )

        print(
            f"  bug_type: "
            f"{candidate.get('bug_type', '')}"
        )

        print(
            f"  title: "
            f"{candidate.get('title', '')}"
        )

        print(
            f"  confidence: "
            f"{candidate.get('confidence', '')}"
        )

        # ==============================================================
        # NO BUG
        # ==============================================================

        if candidate.get("bug_found") is False:

            print()
            print(
                "  RESULT: LLM found no concrete semantic bug."
            )

            print()
            print(
                f"FUNCTION {function_index}/"
                f"{len(functions_to_check)} COMPLETE"
            )

            continue

        # ==============================================================
        # CANDIDATE FINDING
        # ==============================================================

        metrics["findings_candidate"] += 1

        # ==============================================================
        # COMPONENT 7
        # VALIDATE FINDING AGAINST SOURCE
        # ==============================================================

        print()
        print(
            "[COMPONENT 7] Validating finding..."
        )

        try:

            validation_status, validation_reason = (
                validate_finding(
                    candidate,
                    function,
                )
            )

        except Exception as exc:

            logger.warning(
                "Finding validation crashed for %s: %s",
                function.qualified_name,
                exc,
            )

            metrics["findings_rejected"] += 1

            print(
                f"  Validation FAILED with exception: "
                f"{exc}"
            )

            continue

        print(
            f"  Validation status: "
            f"{validation_status}"
        )

        if validation_reason:

            print(
                f"  Reason: "
                f"{validation_reason}"
            )

        # --------------------------------------------------------------
        # NO_BUG
        # --------------------------------------------------------------

        if validation_status == "NO_BUG":

            print(
                "  RESULT: No bug."
            )

            print()
            print(
                f"FUNCTION {function_index}/"
                f"{len(functions_to_check)} COMPLETE"
            )

            continue

        # --------------------------------------------------------------
        # UNSUPPORTED
        # --------------------------------------------------------------

        if validation_status == "UNSUPPORTED":

            metrics["findings_rejected"] += 1

            print(
                "  RESULT: REJECTED."
            )

            print()
            print(
                f"FUNCTION {function_index}/"
                f"{len(functions_to_check)} COMPLETE"
            )

            continue

        # --------------------------------------------------------------
        # UNCERTAIN
        # --------------------------------------------------------------

        if validation_status == "UNCERTAIN":

            metrics["validation_uncertain"] += 1
            metrics["findings_rejected"] += 1

            print(
                "  RESULT: REJECTED as UNCERTAIN."
            )

            print()
            print(
                f"FUNCTION {function_index}/"
                f"{len(functions_to_check)} COMPLETE"
            )

            continue

        # --------------------------------------------------------------
        # UNKNOWN VALIDATION STATUS
        # --------------------------------------------------------------

        if validation_status != "SUPPORTED":

            metrics["findings_rejected"] += 1

            print(
                "  RESULT: REJECTED because validation "
                "returned an unknown status."
            )

            print()
            print(
                f"FUNCTION {function_index}/"
                f"{len(functions_to_check)} COMPLETE"
            )

            continue

        # --------------------------------------------------------------
        # SUPPORTED
        # --------------------------------------------------------------

        metrics["findings_validated"] += 1

        print(
            "  RESULT: SUPPORTED"
        )

        # ==============================================================
        # COMPONENT 8
        # DEDUPLICATION
        # ==============================================================

        print()
        print(
            "[COMPONENT 8] Deduplication: SKIPPED"
        )

        """
        Deduplication is intentionally disabled.

        Every finding that passes Component 7 proceeds directly to
        Component 9.
        """

        # ==============================================================
        # BUILD FINAL FINDING
        # ==============================================================

        issue_title = candidate.get(
            "title",
            f"Semantic bug in {function.name}()",
        )

        issue_description = candidate.get(
            "description",
            "",
        )

        confidence = candidate.get(
            "confidence",
            0.0,
        )

        try:

            confidence = float(
                confidence
            )

        except (
            TypeError,
            ValueError,
        ):

            confidence = 0.0

        # Keep confidence bounded between 0 and 1.

        confidence = max(
            0.0,
            min(
                1.0,
                confidence,
            ),
        )

        # ==============================================================
        # COMPONENT 9
        # PERSIST ACCEPTED FINDING
        # ==============================================================

        print()
        print(
            "[COMPONENT 9] Persisting finding..."
        )

        exact_line = (
            candidate.get("buggy_line")
            or candidate.get("start_line")
            or function.start_line
        )

        issue = CandidateIssue(
            id=str(uuid.uuid4()),
            analysis_run_id=analysis_run_id,
            title=issue_title,
            description=issue_description,
            file_path=function.file_path,
            line_number=exact_line,
            severity=(
                "high"
                if confidence >= 0.85
                else "medium"
            ),
            urgency="needs_review",
            issue_type="semantic_bug",
            message=issue_description,
            code_snippet=function.source,
            evidence={
                "source": "semantic_llm",

                "confidence": confidence,

                "category": candidate.get(
                    "bug_type",
                    "semantic_bug",
                ),

                "bug_type": candidate.get(
                    "bug_type",
                    "semantic_bug",
                ),

                "function_name": function.name,

                "qualified_name": (
                    function.qualified_name
                ),

                "file": function.file_path,

                "function_start_line": function.start_line,

                "function_end_line": function.end_line,

                "buggy_line": candidate.get("buggy_line"),

                "start_line": candidate.get(
                    "start_line",
                    function.start_line,
                ),

                "end_line": candidate.get(
                    "end_line",
                    function.end_line,
                ),

                "evidence": candidate.get(
                    "evidence",
                    "",
                ),

                "reasoning": candidate.get(
                    "reasoning",
                    "",
                ),

                "expected_behavior": candidate.get(
                    "expected_behavior",
                    "",
                ),

                "actual_behavior": candidate.get(
                    "actual_behavior",
                    "",
                ),

                "relevant_code": candidate.get(
                    "relevant_code",
                    "",
                ),

                "suggested_fix": candidate.get(
                    "suggested_fix",
                    "",
                ),
            },
        )

        try:

            async with AsyncSessionLocal() as db:

                db.add(issue)

                suggested_fix_text = candidate.get("suggested_fix")
                if suggested_fix_text and str(suggested_fix_text).strip():
                    rec = IssueRecommendation(
                        id=str(uuid.uuid4()),
                        candidate_issue_id=issue.id,
                        recommendation=str(suggested_fix_text).strip(),
                        diff_remove=candidate.get("relevant_code") or candidate.get("evidence") or None,
                        diff_add=str(suggested_fix_text).strip(),
                        fix_type="ai_patch",
                        priority_order=1,
                    )
                    db.add(rec)

                await db.commit()

        except Exception as exc:

            metrics["persistence_failures"] += 1

            logger.exception(
                "Failed to persist semantic finding for %s",
                function.qualified_name,
            )

            print(
                f"  Persistence FAILED: {exc}"
            )

            continue

        metrics["findings_persisted"] += 1

        print()
        print(
            "  RESULT: ACCEPTED AND PERSISTED"
        )

        print(
            f"  Issue ID : {issue.id}"
        )

        print(
            f"  Title    : {issue.title}"
        )

        print(
            f"  Severity : {issue.severity}"
        )

        print(
            f"  Location : "
            f"{function.file_path}:"
            f"{candidate.get('start_line', function.start_line)}"
        )

        # ==============================================================
        # FUNCTION COMPLETE
        # ==============================================================

        print()
        print(
            f"FUNCTION {function_index}/"
            f"{len(functions_to_check)} COMPLETE"
        )

    # ==================================================================
    # FINAL PIPELINE METRICS
    # ==================================================================

    print()
    print("=" * 80)
    print("SEMANTIC PIPELINE COMPLETE")
    print("=" * 80)

    print()
    print("COMPONENT 1 — FILE DISCOVERY")
    print(
        f"  Files discovered     : "
        f"{metrics['files_discovered']}"
    )
    print(
        f"  Files selected       : "
        f"{metrics['files_selected']}"
    )

    print()
    print("COMPONENT 2 — FUNCTION EXTRACTION")
    print(
        f"  Functions extracted  : "
        f"{metrics['functions_extracted']}"
    )
    print(
        f"  Functions checked    : "
        f"{metrics['functions_checked']}"
    )

    print()
    print("COMPONENT 3 — CONTEXT")
    print(
        f"  Contexts built       : "
        f"{metrics['contexts_built']}"
    )

    print()
    print("COMPONENT 4 — PRE-FILTER")
    print(
        f"  Functions passed     : "
        f"{metrics['functions_prefiltered']}"
    )

    print()
    print("COMPONENT 5 — LLM DETECTION")
    print(
        f"  LLM calls            : "
        f"{metrics['llm_calls_made']}"
    )
    print(
        f"  LLM failures         : "
        f"{metrics['llm_failures']}"
    )

    print()
    print("COMPONENT 6 — PARSING")
    print(
        f"  Responses parsed     : "
        f"{metrics['responses_parsed']}"
    )
    print(
        f"  Parse failures       : "
        f"{metrics['parse_failures']}"
    )

    print()
    print("COMPONENT 7 — VALIDATION")
    print(
        f"  Candidate findings   : "
        f"{metrics['findings_candidate']}"
    )
    print(
        f"  Validated findings   : "
        f"{metrics['findings_validated']}"
    )
    print(
        f"  Rejected findings    : "
        f"{metrics['findings_rejected']}"
    )
    print(
        f"  Uncertain findings   : "
        f"{metrics['validation_uncertain']}"
    )

    print()
    print("COMPONENT 8 — DEDUPLICATION")
    print(
        "  Status               : SKIPPED"
    )

    print()
    print("COMPONENT 9 — PERSISTENCE")
    print(
        f"  Findings persisted   : "
        f"{metrics['findings_persisted']}"
    )
    print(
        f"  Persistence failures : "
        f"{metrics['persistence_failures']}"
    )

    print()
    print("=" * 80)

    return metrics