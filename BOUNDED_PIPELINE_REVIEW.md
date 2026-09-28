# BOUNDED SEMANTIC PIPELINE - END-TO-END REVIEW

## Configuration Limits

### From semantic_pipeline.py (SemanticReviewConfig):

```python
@dataclass(frozen=True)
class SemanticReviewConfig:
    max_files: int = int(os.getenv("SEMANTIC_MAX_FILES", "40"))
    max_source_chars: int = int(os.getenv("SEMANTIC_MAX_SOURCE_CHARS", "300000"))
    max_functions: int = int(os.getenv("SEMANTIC_MAX_FUNCTIONS", "120"))
    max_context_chars: int = int(os.getenv("SEMANTIC_MAX_CONTEXT_CHARS", "12000"))
    max_context_depth: int = int(os.getenv("SEMANTIC_MAX_CONTEXT_DEPTH", "1"))
    min_confidence: float = float(os.getenv("SEMANTIC_MIN_CONFIDENCE", "0.75"))
```

**Current Defaults:**
- max_files = 40 files
- max_source_chars = 300,000 chars total across all files
- max_functions = 120 functions
- max_context_chars = 12,000 chars per function context
- max_context_depth = 1 (only direct local callees)
- min_confidence = 0.75

**Environment Variables:** None set in .env, so defaults are active

---

## 1. FILE SELECTION (discover_source_files)

### Application Hints (what gets selected):
```python
APPLICATION_HINTS = frozenset({
    "service", "services", "core", "logic", "domain", "business", "usecase",
    "usecases", "use_case", "use_cases", "controller", "controllers", "handler",
    "handlers", "api", "routes", "views", "repository", "repositories", "manager",
    "managers", "processor", "processors", "worker", "workers", "module", "modules",
})
```

### Exclusion Rules (what gets skipped):
```python
EXCLUDED_PARTS = frozenset({
    ".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist", "build",
    "coverage", "vendor", "migrations", "alembic", "docs", "site-packages", ".pytest_cache",
})
```

### Selection Logic:
1. **Find all .py files** recursively in repository
2. **Skip if:**
   - Path contains any EXCLUDED_PARTS
   - Filename starts with "test_" or ends with "_test.py"
   - File size is 0 or > max_source_chars (300KB default)
   - File has syntax errors or invalid UTF-8
3. **Include if:**
   - Path contains APPLICATION_HINTS (e.g., "services", "core", "logic") → "application-directory hint"
   - Filename is main.py, app.py, server.py, manage.py, wsgi.py, asgi.py → "application-entry hint"
   - File contains executable definitions (functions/classes) → "executable definitions"
4. **Sort priority:**
   - Files with "application-directory hint" come first
   - Then alphabetically by relative path
5. **Bounded selection:**
   - Stop when reaching max_files (40) OR total_chars > max_source_chars (300KB)

### Result:
```python
@dataclass(frozen=True)
class SelectedFile:
    path: Path                          # Absolute path
    relative_path: str                  # Relative to repo root
    language: str                       # "python"
    source_chars: int                   # File size in characters
    selection_reasons: tuple[str, ...]  # Why this file was selected
```

---

## 2. FUNCTION EXTRACTION (extract_functions)

### What Gets Extracted:
- All FunctionDef and AsyncFunctionDef nodes from AST
- Methods inside classes (with class context)
- Nested functions (they are functions too)

### Information Captured:
```python
@dataclass(frozen=True)
class ExtractedFunction:
    file_path: str              # Relative path
    language: str               # "python"
    name: str                   # Function name
    class_name: str | None      # Containing class if method
    qualified_name: str         # "ClassName.method_name" or "function_name"
    start_line: int             # 1-indexed
    end_line: int               # 1-indexed, inclusive
    source: str                 # Complete function source code
    parameters: tuple[str, ...] # ("arg1", "arg2", "*args", "**kwargs")
    is_async: bool              # True for async def
    decorators: tuple[str, ...] # Unparsed decorator source
    called_names: tuple[str, ...] # Names called inside function
    imports: tuple[str, ...]    # File-level imports
    class_source: str | None    # Complete class source if method
```

### No Pre-filtering:
- ALL functions are extracted
- No judgment about which might be buggy
- No skipping of getters, setters, simple functions

---

## 3. CONTEXT BUILDING (build_context)

### Context Included (in order, within budget):
1. **Target function** (ALWAYS included, full source)
2. **Imports** (if space available)
3. **Containing class** (if method and space available)
4. **Direct local callees** (functions called by target, same file only, depth=1)

### Context Budget:
- max_context_chars = 12,000 chars default
- Context is built sequentially; stops when budget exhausted
- Returns truncated=True if ran out of space

### Result:
```python
@dataclass(frozen=True)
class ContextPackage:
    text: str                      # Complete context text
    included: tuple[str, ...]      # ["target_function", "imports", "direct_callee:func_name"]
    truncated: bool                # True if hit budget limit
```

### Example Context Format:
```
TARGET FUNCTION calculate_total (services/payment.py:15-20)
def calculate_total(items):
    total = 0
    for item in items:
        total += item["price"] * item["quantity"]
    return total

RELEVANT IMPORTS
import decimal
from typing import List

DIRECT LOCAL CALLEE validate_items (22-25)
def validate_items(items):
    return all(item.get("price") and item.get("quantity") for item in items)
```

---

## 4. LLM PROMPT (build_detection_prompt)

### Prompt Structure:
```python
def build_detection_prompt(target: ExtractedFunction, context: ContextPackage) -> str:
    return f'''You are reviewing bounded repository code for concrete semantic or behavioral defects that deterministic rules may miss.
Repository language: {target.language}
Target file: {target.file_path}
Target function: {target.qualified_name}

Use only the supplied code and context. Do not report style, preferences, hypothetical problems, missing features, or unrelated bugs. If concrete evidence is insufficient, return bug_found=false.

Return exactly one JSON object:
{{"bug_found":false,"bug_type":"","title":"","description":"","file":"{target.file_path}","start_line":{target.start_line},"end_line":{target.end_line},"evidence":"","reasoning":"","expected_behavior":"","actual_behavior":"","confidence":0.0,"relevant_code":""}}

For a true finding, location must be inside the target function and relevant_code must be an exact source excerpt. Do not invent symbols or dependencies.

CONTEXT INCLUDED: {", ".join(context.included)}
{context.text}'''
```

### Prompt Size:
- Base template: ~800 chars
- Context: up to 12,000 chars
- **Total: ~12,800 chars maximum per prompt**

### Expected LLM Response Format:
```json
{
  "bug_found": true,
  "bug_type": "wrong_variable_used",
  "title": "Wrong dictionary key accessed",
  "description": "Function accesses item['qty'] but standard key is 'quantity'",
  "file": "services/payment.py",
  "start_line": 17,
  "end_line": 17,
  "evidence": "Line uses item['qty'] which will raise KeyError",
  "reasoning": "All other functions use 'quantity' key",
  "expected_behavior": "Should access item['quantity']",
  "actual_behavior": "Accesses item['qty']",
  "confidence": 0.9,
  "relevant_code": "total += item[\"price\"] * item[\"qty\"]"
}
```

---

## 5. EVIDENCE VALIDATION (validate_finding)

### Validation Steps:

#### Step 1: Structural Validation
```python
# Check basic structure
if not candidate or not isinstance(candidate.get("bug_found"), bool):
    return "UNSUPPORTED", "Malformed or missing bug_found field."

if not candidate["bug_found"]:
    return "NO_BUG", None
```

#### Step 2: Required Fields
```python
required = ("bug_type", "title", "description", "evidence", "reasoning", "relevant_code")
if any(not isinstance(candidate.get(field), str) or not candidate[field].strip() for field in required):
    return "UNSUPPORTED", "Missing required finding evidence."
```

#### Step 3: File Match
```python
if candidate.get("file") != target.file_path:
    return "UNSUPPORTED", "Finding references a different file."
```

#### Step 4: Location Validation
```python
try:
    start, end = int(candidate["start_line"]), int(candidate["end_line"])
except (KeyError, TypeError, ValueError):
    return "UNSUPPORTED", "Invalid location."

if start < target.start_line or end < start or end > target.end_line:
    return "UNSUPPORTED", "Finding location is outside the analyzed function."
```

#### Step 5: Code Excerpt Validation
```python
if candidate["relevant_code"] not in target.source:
    return "UNSUPPORTED", "Cited code does not occur in the target function."
```

#### Step 6: Symbol Validation
```python
source_names = {node.id for node in ast.walk(ast.parse(textwrap.dedent(target.source))) 
                if isinstance(node, ast.Name)}
mentioned = {word for word in candidate["evidence"].replace("_", " ").split() if word.isidentifier()}

if mentioned and not (mentioned & source_names):
    return "UNCERTAIN", "Evidence has no statically resolvable target symbol."
```

### Validation Results:
- **"SUPPORTED"** → Finding is valid, proceed to save
- **"UNSUPPORTED"** → Finding is hallucinated/malformed, reject
- **"UNCERTAIN"** → Evidence mentions symbols not in target (currently still accepted)
- **"NO_BUG"** → LLM says no bug found

---

## 6. DEDUPLICATION

### Logic:
```python
# Query rule-based findings in the SAME FILE
rule_candidates = await db_session.execute(
    select(CandidateIssue).where(
        (CandidateIssue.analysis_run_id == analysis_run_id) &
        (CandidateIssue.file_path == file_path) &
        ((CandidateIssue.rule_id.isnot(None)) |
         (cast(CandidateIssue.evidence["source"], String) == '"rule"'))
    )
)

# Use existing dedup_engine to check similarity
return dedup_engine.find_duplicate(llm_finding, rule_findings)
```

### Scope:
- Only checks within the same file
- Compares LLM findings against rule-based findings
- Uses existing deduplication engine logic

---

## 7. COMPLETE PIPELINE FLOW

```
START: Repository Path
  ↓
[CONFIG] Load limits (max_files=40, max_functions=120, max_context_chars=12000)
  ↓
[PHASE 1] File Selection (discover_source_files)
  → Scan repository recursively for *.py
  → Apply exclusion rules (tests, vendor, migrations, etc.)
  → Apply inclusion rules (APPLICATION_HINTS: services, core, logic, etc.)
  → Sort by priority (app hints first, then alphabetical)
  → Bound selection (stop at 40 files OR 300KB total)
  → Result: List[SelectedFile] (typically 10-40 files)
  ↓
[PHASE 2] Function Extraction (extract_functions)
  → For each selected file:
    → Parse AST
    → Extract ALL functions/methods (no filtering)
    → Capture metadata (name, lines, params, decorators, calls, class)
  → Result: List[ExtractedFunction] (typically 100-500 functions)
  ↓
[BOUND] Limit to max_functions (120)
  → Take first 120 functions if more were extracted
  ↓
[PHASE 3-9] For each function (up to 120):
  ↓
  [PHASE 3] Context Building (build_context)
    → Include target function (always)
    → Add imports (if budget allows)
    → Add containing class (if method and budget allows)
    → Add direct local callees (depth=1, same file, budget permitting)
    → Bound by max_context_chars (12,000)
    → Result: ContextPackage (~500-12000 chars)
  ↓
  [PHASE 4] Pre-filter
    → Currently: NO filtering
    → Conservative approach to avoid false negatives
  ↓
  [PHASE 5] LLM Detection (build_detection_prompt + LLM call)
    → Build prompt (~800 chars template + context)
    → Call LLM provider (Groq qwen/qwen3.8-27b)
    → Track LLM call count
    → Result: JSON string response
  ↓
  [PHASE 6] Parse Response (parse_llm_finding)
    → Strip markdown fences if present
    → Parse JSON
    → Check bug_found field
    → Result: dict or None
  ↓
  [PHASE 7] Evidence Validation (validate_finding)
    → Validate structure (bug_found, required fields)
    → Validate file match
    → Validate location bounds (start/end within function)
    → Validate code excerpt exists in source
    → Validate mentioned symbols exist
    → Result: "SUPPORTED", "UNSUPPORTED", "UNCERTAIN", or "NO_BUG"
  ↓
  [FILTER] If validation != "SUPPORTED" → REJECT, continue to next function
  ↓
  [PHASE 8] Deduplication (_check_duplicate)
    → Query rule-based findings in same file
    → Use dedup_engine.find_duplicate()
    → Result: duplicate dict or None
  ↓
  [FILTER] If duplicate found → REJECT, log, continue to next function
  ↓
  [PHASE 9] Save Finding
    → Create CandidateIssue with source="semantic_llm"
    → Save to database
    → Increment accepted_as_unique counter
  ↓
[LOOP BACK] Process next function (up to 120 total)
  ↓
[END] Return metrics dict:
  - files_selected
  - functions_extracted
  - functions_checked (≤ 120)
  - llm_calls_made (= functions_checked)
  - findings_candidate (LLM said bug_found=true)
  - findings_validated (passed evidence validation)
  - rejected_as_duplicates (matched rule findings)
  - accepted_as_unique (final saved findings)
  - rule_findings (existing rule-based findings)
```

---

## 8. RESOURCE LIMITS SUMMARY

| Limit | Default | Impact |
|-------|---------|--------|
| **max_files** | 40 | Maximum source files selected |
| **max_source_chars** | 300,000 | Total chars across all files |
| **max_functions** | 120 | Maximum functions checked |
| **max_context_chars** | 12,000 | Context size per function |
| **max_context_depth** | 1 | Only direct local callees |

### LLM Call Estimation:
- **1 LLM call per function checked**
- **Default: up to 120 LLM calls per repository scan**
- **Prompt size: ~800-12,800 chars each**

### Token Estimation (Groq qwen/qwen3.8-27b):
- Input: ~200-3,200 tokens per call (assume 4 chars/token)
- 120 calls × 3,000 avg tokens = ~360,000 input tokens
- With Groq OTPM limit = 1,000 tokens, this will need pacing

---

## 9. CURRENT ISSUES/OBSERVATIONS

### ✓ Strengths:
1. Bounded selection is deterministic and explainable
2. Context building respects limits
3. Evidence validation is thorough
4. File selection uses sensible application hints
5. Deduplication prevents rule/LLM overlap

### ⚠ Potential Issues:
1. **No pre-filtering** - All 120 functions go to LLM (could be wasteful)
2. **OTPM limit** - 120 calls may hit Groq per-minute token limits
3. **max_functions=120** - May be too many for large repos
4. **Context depth=1** - Only includes direct local callees (may miss bugs requiring deeper context)
5. **UNCERTAIN validation status** - Currently rejected but comment says "preserve unresolved semantic uncertainty"
6. **No retry logic** - If LLM call fails, function is skipped
7. **No batching** - Each function is a separate LLM call

---

## 10. CONFIGURATION IN .env

**Current LLM Provider Settings:**
```
LLM_PROVIDER=groq
GROQ_MODEL=qwen/qwen3.8-27b
GROQ_API_KEY=gsk_***
GROQ_TIMEOUT_SECONDS=60
```

**Semantic Pipeline Settings:**
```
# None set - using defaults:
# SEMANTIC_MAX_FILES=40
# SEMANTIC_MAX_SOURCE_CHARS=300000
# SEMANTIC_MAX_FUNCTIONS=120
# SEMANTIC_MAX_CONTEXT_CHARS=12000
# SEMANTIC_MAX_CONTEXT_DEPTH=1
# SEMANTIC_MIN_CONFIDENCE=0.75
```

