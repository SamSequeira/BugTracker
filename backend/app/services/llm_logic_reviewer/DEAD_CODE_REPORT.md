# DEAD CODE REPORT - llm_logic_reviewer/

**Date:** 2026-09-28  
**Scope:** backend/app/services/llm_logic_reviewer/ only  
**Analysis Method:** Import tracing, missing module detection, reference counting

---

## SUMMARY

**Total Files in Directory:** 18 (including backups)  
**Files Currently Used (Classic Pipeline):** 4  
**Dead/Orphaned Files:** 12  
**Backup Files:** 2  

---

## CATEGORY 1: MISSING DEPENDENCIES (BROKEN IMPORTS)

### 1.1 high_precision_detector.py (48 KB)
**Status:** DEAD - Cannot be imported  
**Evidence:**
```python
# Line 36:
from app.services.llm_logic_reviewer.source_validator import validate_candidate_against_source

# Line 43:
from app.services.llm_logic_reviewer.openai_reasoner import reason_about_semantic_candidate
```

**Proof of Missing Modules:**
```bash
`$ file_search openai_reasoner.py
# Result: No files found

`$ file_search source_validator.py  
# Result: No files found
```

**Import Attempts:**
```bash
`$ python -c "from app.services.llm_logic_reviewer import high_precision_detector"
# Error: ModuleNotFoundError: No module named 'app.services.llm_logic_reviewer.source_validator'
```

**Grep Results (No External Imports):**
```bash
`$ grep -r "high_precision_detector" **/*.py
# Result: No matches found (except self-references)
```

**Conclusion:** This file has never successfully run in the current codebase.

---

### 1.2 evidence_validator.py (4.5 KB)
**Status:** DEAD - Depends on missing openai_reasoner  
**Evidence:**
```python
# Line 14:
from app.services.llm_logic_reviewer.openai_reasoner import SemanticReasoningResult
```

**Import Chain:**
- evidence_validator.py → openai_reasoner.py (MISSING)
- high_precision_detector.py → evidence_validator.py (but high_precision_detector is also dead)

**Grep Results:**
```bash
`$ grep -r "evidence_validator" **/*.py --exclude-dir=__pycache__
# Result: Only imported by high_precision_detector.py (which is itself dead)
```

**Conclusion:** Dead dependency chain.

---

## CATEGORY 2: ORPHANED MODULES (NO IMPORTS FROM PRODUCTION CODE)

### 2.1 candidate_selector.py (6.3 KB)
**Status:** ORPHANED  
**Evidence:**
```bash
`$ grep -r "candidate_selector" **/*.py --exclude-dir=__pycache__
# Only match: high_precision_detector.py line 41
```

**Imports Only From:** high_precision_detector.py (which is dead)  
**Never Imported By:** reviewer.py, semantic_pipeline.py, repositories.py, or any test

**Conclusion:** Orphaned, only referenced by dead code.

---

### 2.2 context_retriever.py (39 KB)
**Status:** ORPHANED  
**Evidence:**
```bash
`$ grep -r "context_retriever" **/*.py --exclude-dir=__pycache__
# Only match: high_precision_detector.py line 40
```

**Note:** semantic_pipeline.py has its own `build_context()` function (currently used).

**Conclusion:** Duplicate/abandoned context building implementation.

---

### 2.3 evidence_builder.py (8.8 KB)
**Status:** ORPHANED  
**Evidence:**
```bash
`$ grep -r "evidence_builder" **/*.py --exclude-dir=__pycache__
# Only match: high_precision_detector.py line 42
```

**Conclusion:** Orphaned, only referenced by dead code.

---

### 2.4 function_extractor.py (7 KB)
**Status:** ORPHANED  
**Evidence:**
```bash
`$ grep -r "function_extractor" **/*.py --exclude-dir=__pycache__
# Result: No matches found
```

**Note:** semantic_pipeline.py has its own `extract_functions()` function (currently used).

**Conclusion:** Duplicate/abandoned function extraction implementation.

---

### 2.5 metrics.py (6.1 KB)
**Status:** ORPHANED  
**Evidence:**
```bash
`$ grep -r "from.*llm_logic_reviewer.*metrics" **/*.py
# Result: No matches found

`$ grep -r "MetricsCollector|DetectionMetrics" backend/app/services/llm_logic_reviewer/*.py
# Only found: self-definitions in metrics.py
```

**Conclusion:** Metrics tracking never integrated into any pipeline.

---

### 2.6 repository_index.py (33 KB)
**Status:** ORPHANED (but referenced by dead code)  
**Evidence:**
```bash
`$ grep -r "repository_index" **/*.py --exclude-dir=__pycache__
# Matches: candidate_selector.py, context_retriever.py, evidence_builder.py, 
#          evidence_validator.py, high_precision_detector.py, semantic_facts.py
```

**All References From Dead/Orphaned Files Only:**
- candidate_selector.py (orphaned)
- context_retriever.py (orphaned)
- evidence_builder.py (orphaned)
- evidence_validator.py (dead)
- high_precision_detector.py (dead)
- semantic_facts.py (orphaned - see below)

**Never Imported By:** reviewer.py, semantic_pipeline.py, or any active code

**Conclusion:** Complex repository indexing system that was never integrated.

---

### 2.7 semantic_facts.py (19 KB)
**Status:** ORPHANED  
**Evidence:**
```bash
`$ grep -r "semantic_facts" **/*.py --exclude-dir=__pycache__
# Matches: repository_index.py line 35, high_precision_detector.py line 37
```

**Import Chain:**
- repository_index.py → semantic_facts.py (repository_index is itself orphaned)
- high_precision_detector.py → semantic_facts.py (dead)

**Conclusion:** Fact extraction system never integrated.

---

### 2.8 value_flow.py (45 KB)
**Status:** ORPHANED  
**Evidence:**
```bash
`$ grep -r "value_flow" **/*.py --exclude-dir=__pycache__
# Matches: semantic_facts.py line 28, high_precision_detector.py line 38
```

**Import Chain:**
- semantic_facts.py → value_flow.py (semantic_facts is itself orphaned)
- high_precision_detector.py → value_flow.py (dead)

**Conclusion:** Value flow analysis never integrated.

---

### 2.9 config.py (2.7 KB)
**Status:** PARTIALLY ORPHANED - Some env vars might be read elsewhere  
**Evidence:**
```bash
`$ grep -r "from.*llm_logic_reviewer.*config" **/*.py --exclude-dir=__pycache__
# Matches: candidate_selector.py line 13, function_extractor.py line 11, 
#          high_precision_detector.py line 34
```

**All References From Dead/Orphaned Files.**

**Environment Variables Defined:**
- `OLLAMA_HOST`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS` (ALSO defined in llm_provider.py)
- `LLM_MIN_FUNCTION_LINES`, `LLM_MAX_FUNCTION_CHARS`, `LLM_MAX_RETRIES_PER_FUNCTION` (unused)
- `OPENAI_API_KEY`, `SEMANTIC_STRONG_MODEL`, `SEMANTIC_MIN_CONFIDENCE` (unused)
- `SEMANTIC_CANDIDATE_SCORE_THRESHOLD` (unused)

**Duplicate Config:**
- llm_provider.py reads OLLAMA_* vars directly via `os.getenv()` (lines ~665-680)
- config.py reads the same vars

**Conclusion:** Duplicate configuration, unreferenced by active code.

---

## CATEGORY 3: BACKUP FILES

### 3.1 reviewer.py.backup (11 KB)
**Last Modified:** 2026-09-26 4:43 PM  
**Evidence:** File extension `.backup`  
**Conclusion:** Old backup, safe to delete.

---

### 3.2 semantic_pipeline.py.bak (64 KB)
**Last Modified:** 2026-09-28 10:53 AM (same date as current semantic_pipeline.py)  
**Evidence:** File extension `.bak`, size very similar to current file (64863 vs 63621 bytes)  
**Conclusion:** Recent backup during editing, safe to delete.

---

## CATEGORY 4: CURRENTLY ACTIVE FILES (DO NOT DELETE)

### 4.1 reviewer.py (25 KB) ✓ ACTIVE
**Exports:** `async def run_llm_logic_review()`  
**Imported By:** 
- backend/app/api/v1/repositories.py (line 114, 339)
- backend/run_pipeline_logged.py (line 102)
- test_complete_e2e.py (line 109)
- test_final_e2e.py (line 106)
- backend/test_e2e.py (line 38)
- backend/test_components_1_4.py (line 5)

---

### 4.2 semantic_pipeline.py (65 KB) ✓ ACTIVE
**Exports:**
- `SemanticReviewConfig`
- `discover_source_files()`
- `extract_functions()`
- `build_context()`
- `build_detection_prompt()`
- `parse_llm_finding()`
- `validate_finding()`

**Imported By:**
- reviewer.py (line 36)
- backend/tests/test_bounded_semantic_pipeline.py (line 3)

---

### 4.3 llm_provider.py (31 KB) ✓ ACTIVE
**Exports:**
- `LLMProvider` (base class)
- `OllamaProvider`
- `GeminiProvider`
- `GroqProvider`
- `OpenAIProvider`
- `FailoverProvider`
- `create_llm_provider()`

**Imported By:**
- reviewer.py (line 34)
- backend/run_pipeline_logged.py (line 103)
- test_provider.py (line 5)
- backend/test_e2e.py (line 24)
- high_precision_detector.py (line 35 - but this file is dead)

---

### 4.4 deduplication.py (21 KB) ✓ ACTIVE (but currently SKIPPED in pipeline)
**Exports:**
- `DeduplicationEngine`
- `get_dedup_engine()`
- `normalize_category()`

**Note:** Component 8 (deduplication) is intentionally SKIPPED in reviewer.py line ~478-487.  
This file is structurally sound but functionally dormant. It exists for future use.

**Imported By:** None currently (reserved for future Component 8 activation)

---

### 4.5 __init__.py (41 bytes) ✓ ACTIVE
**Purpose:** Package marker  
**Contents:** Minimal or empty

---

## DELETION SUMMARY

**Safe to Delete Immediately (12 files, ~240 KB):**

1. `high_precision_detector.py` - Broken imports, never runnable
2. `candidate_selector.py` - Orphaned
3. `context_retriever.py` - Orphaned, duplicate of semantic_pipeline functionality
4. `evidence_builder.py` - Orphaned
5. `evidence_validator.py` - Broken dependency chain
6. `function_extractor.py` - Orphaned, duplicate of semantic_pipeline functionality
7. `metrics.py` - Never integrated
8. `repository_index.py` - Orphaned, complex unused indexing
9. `semantic_facts.py` - Orphaned
10. `value_flow.py` - Orphaned
11. `config.py` - Duplicate configuration, unreferenced
12. `reviewer.py.backup` - Backup file

**Safe to Delete After Verification (1 file):**

13. `semantic_pipeline.py.bak` - Recent backup, delete after confirming current semantic_pipeline.py works

---

## VERIFICATION COMMAND

Before deletion, run the existing pipeline to establish baseline:

```powershell
cd backend
python run_pipeline_logged.py C:\mw\miniwallet-buggy --label before_cleanup --max-functions 5
```

**Expected Output:** Pipeline completes, generates findings.json with 0-N findings.

After deletion, run again:

```powershell
python run_pipeline_logged.py C:\mw\miniwallet-buggy --label after_cleanup --max-functions 5
```

**Success Criteria:** Identical pipeline behavior, same number of findings (±0 tolerance).

---

## UNUSED ENVIRONMENT VARIABLES (from config.py)

These env vars are defined but never read by active code:

```
LLM_MIN_FUNCTION_LINES
LLM_MAX_FUNCTION_CHARS
LLM_MAX_RETRIES_PER_FUNCTION
SEMANTIC_STRONG_MODEL
SEMANTIC_CANDIDATE_SCORE_THRESHOLD
```

**Action:** These can remain in `.env` files (harmless) or be removed during config cleanup.

---

## DEPENDENCY GRAPH (Dead Code Only)

```
high_precision_detector.py (DEAD - broken imports)
├── source_validator.py (MISSING FILE)
├── openai_reasoner.py (MISSING FILE)
├── candidate_selector.py (ORPHANED)
├── context_retriever.py (ORPHANED)
├── evidence_builder.py (ORPHANED)
├── evidence_validator.py (DEAD)
├── semantic_facts.py (ORPHANED)
├── value_flow.py (ORPHANED)
├── repository_index.py (ORPHANED)
└── config.py (ORPHANED)
```

**None of these files are reachable from the active entry point** (`run_llm_logic_review()` in reviewer.py).

---

## RECOMMENDATION

**APPROVE deletion of all 13 files listed above.**

The "classic" pipeline (Components 1-9) relies ONLY on:
- reviewer.py
- semantic_pipeline.py
- llm_provider.py
- deduplication.py (reserved for future use)

All other files represent an abandoned "high precision" rewrite attempt that was never completed and has missing dependencies.

---

**END OF REPORT**
