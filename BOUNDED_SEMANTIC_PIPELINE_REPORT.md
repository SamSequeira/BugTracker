# Bounded Semantic Pipeline Implementation Report

## Executive Summary

Successfully restored the LLM reviewer from commit 6d0099d and implemented the bounded semantic pipeline on top of the existing implementation. The system now uses a deterministic, evidence-based approach to semantic bug detection.

## What Was Restored

### Core LLM Reviewer Files (from commit 6d0099d):
1. **function_extractor.py** - Extracts individual functions from Python files
2. **high_precision_detector.py** - High-precision semantic bug detector with multi-stage validation
3. **deduplication.py** - Prevents rule/LLM finding overlap  
4. **repository_index.py** - Builds repository intelligence index
5. **context_retriever.py** - Retrieves relevant context for functions
6. **evidence_validator.py** - Validates semantic findings against actual source
7. **evidence_builder.py** - Builds cross-file evidence chains
8. **semantic_facts.py** - Extracts semantic facts from code
9. **value_flow.py** - Tracks value flow through functions
10. **candidate_selector.py** - Scores and selects candidate functions
11. **metrics.py** - Tracks pipeline metrics

### Integration Point:
- **repositories.py** - Already integrated to call run_llm_logic_review in Phase 3 of analysis

## What Was Implemented

### New Bounded Semantic Pipeline (semantic_pipeline.py):
Already existed and provides:

1. **File Selection** (discover_source_files):
   - Uses generic directory/file signals (service, services, logic, core, domain, controller, handler, repository, api, views, usecase, etc.)
   - Deterministic and explainable selection
   - Excludes tests, vendor, build artifacts
   - Bounded by max_files and max_source_chars

2. **Function Extraction** (extract_functions):
   - Extracts all meaningful functions/methods from selected files
   - Preserves file path, function name, line range, source code, class/module info
   - No pre-filtering at this stage

3. **Context Extraction** (build_context):
   - Builds bounded context around each function
   - Includes: imports, direct local callees, containing class
   - Respects max_context_chars limit
   - Does not send entire repository to LLM

4. **Evidence Validation** (validate_finding):
   - Validates every LLM finding against actual repository/function/context
   - Verifies referenced variables, functions, calls, conditions, lines exist
   - Rejects findings based on nonexistent code or invented dependencies
   - Does NOT reject semantic bugs simply because rules didn't detect them

### Updated Bounded Reviewer (reviewer.py):
Completely rewritten to use semantic_pipeline:

**Phase 1: File Selection**
- Calls discover_source_files() to select application code
- Logs selected files and reasons

**Phase 2: Function Extraction**
- Extracts functions from all selected files
- Handles extraction errors gracefully

**Phase 3: Context Extraction**
- Builds bounded context for each function using build_context()

**Phase 4: Pre-filter**
- Currently conservative (no aggressive filtering)
- Ensures we don't miss real bugs

**Phase 5: LLM Detector**
- Builds detection prompt using build_detection_prompt()
- Calls LLM provider
- Tracks LLM call count

**Phase 6: Parse LLM Response**
- Uses parse_llm_finding() to extract JSON
- Handles malformed responses

**Phase 7: Evidence Validation**
- Uses validate_finding() to check against source
- Rejects UNSUPPORTED findings
- Allows UNCERTAIN findings (semantic bugs may be ambiguous)

**Phase 8: Deduplication**
- Checks against existing rule-based findings
- Uses existing dedup_engine
- Preserves unique semantic insights

**Phase 9: Final Findings**
- Saves only supported findings to database
- Returns detailed metrics

## Pipeline Flow

```
Repository Path
  ↓
Phase 1: File Selection (discover_source_files)
  → Selects application/business-logic files
  → Uses directory hints (services, core, logic, etc.)
  → Bounded by max_files/max_source_chars
  ↓
Phase 2: Function Extraction (extract_functions)
  → Extracts all functions from selected files
  → Preserves full context (class, decorators, params, etc.)
  ↓
Phase 3: Context Extraction (build_context)
  → Builds bounded context for each function
  → Includes imports, local callees, containing class
  → Bounded by max_context_chars
  ↓
Phase 4: Pre-filter
  → Conservative filtering (currently minimal)
  → Only removes clearly unsuitable content
  ↓
Phase 5: LLM Detector (build_detection_prompt + LLM call)
  → Sends bounded prompt to LLM
  → Asks for structured JSON response
  → Tracks LLM calls
  ↓
Phase 6: Parse LLM Response (parse_llm_finding)
  → Extracts JSON from LLM response
  → Handles malformed output
  ↓
Phase 7: Evidence Validation (validate_finding)
  → Verifies finding against actual source
  → Checks location, code excerpts, symbols
  → Rejects hallucinations
  ↓
Phase 8: Deduplication (dedup_engine)
  → Checks against rule-based findings
  → Prevents overlap
  ↓
Phase 9: Final Findings
  → Saves to database as CandidateIssue
  → Returns metrics
```

## Metrics Tracked

1. **files_selected** - Number of files selected for review
2. **functions_extracted** - Total functions extracted
3. **functions_checked** - Functions sent to LLM
4. **llm_calls_made** - Total LLM API calls
5. **findings_candidate** - LLM flagged these as bugs
6. **findings_validated** - Passed evidence validation
7. **rejected_as_duplicates** - Duplicates of rule findings
8. **accepted_as_unique** - Final unique findings saved
9. **rule_findings** - Existing rule-based findings

## Configuration

Environment variables (with defaults):
- SEMANTIC_MAX_FILES=40
- SEMANTIC_MAX_SOURCE_CHARS=300000
- SEMANTIC_MAX_FUNCTIONS=120
- SEMANTIC_MAX_CONTEXT_CHARS=12000
- SEMANTIC_MAX_CONTEXT_DEPTH=1
- SEMANTIC_MIN_CONFIDENCE=0.75

## Verification

### Test Repository Created:
- Location: backend/test_semantic_repo/services/payment.py
- Contains 2 functions with semantic bugs
- File selection: ✓ PASSED (1 file selected)
- Function extraction: ✓ PASSED (2 functions extracted)
- Context building: ✓ PASSED (184 chars context)

### Pipeline Status:
✓ File selection works correctly
✓ Function extraction works correctly
✓ Context building works correctly
✓ Evidence validation logic implemented
✓ Deduplication integration preserved
✓ API integration preserved (repositories.py Phase 3)

## Important Design Decisions

1. **Conservative Pre-filtering**: We do NOT aggressively discard functions to avoid missing real bugs
2. **Evidence-First Validation**: Every finding must be validated against actual source code
3. **Semantic Focus**: The LLM's job is specifically to find semantic bugs that deterministic rules miss
4. **No Rule Replacement**: The existing rule-based analyzer continues finding deterministic bugs
5. **Bounded Context**: Context is limited to avoid token overflow on local models
6. **Deterministic Selection**: File/function selection is deterministic and explainable

## Next Steps

1. Test with a real repository scan
2. Monitor LLM call counts and token usage
3. Adjust max_functions based on performance
4. Fine-tune evidence validation thresholds
5. Add more sophisticated pre-filtering if needed (after measuring false negatives)

## Files Modified

1. backend/app/services/llm_logic_reviewer/reviewer.py - COMPLETELY REWRITTEN
2. backend/app/services/llm_logic_reviewer/semantic_pipeline.py - Already existed
3. backend/app/services/llm_logic_reviewer/*.py - Restored from 6d0099d

## Files Unchanged

1. backend/app/api/v1/repositories.py - Integration already present
2. backend/app/services/llm_logic_reviewer/llm_provider.py - Token fixes preserved
3. backend/app/services/llm_logic_reviewer/config.py - Configuration preserved
