# Requirements Document

## Introduction

BugTracker Full-Stack transforms an existing Vite + React frontend (with stub backend) into a production-quality, end-to-end AI-powered code security scanner. A user pastes a public GitHub URL or uploads a ZIP archive, clicks Analyze, and receives: a real file tree, detected languages, a ranked list of static-analysis issues (each with file path, line number, code snippet, rule ID, severity, and priority), per-issue AI explanations and unified-diff fix suggestions, duplicate/similar issue groupings via embedding similarity, and a dashboard summary — all from a real backend with zero mock-data fallback in the live scan flow.

The backend is a Python 3.11+ FastAPI/Uvicorn application backed by SQLite (swappable to Postgres by changing `DATABASE_URL`). AI calls go to Claude via `ANTHROPIC_API_KEY`; when the key is absent the pipeline degrades gracefully. Embeddings and duplicate detection use `sentence-transformers` + ChromaDB in local embedded mode. The existing frontend structure is preserved; only `api.js`, `useBugTracker.jsx`, `TabRepositoryScanner.jsx`, `TabBugManagement.jsx`, `BugDetailsDrawer.jsx`, and `TabReports.jsx` are modified to wire real data and surface real errors.

---

## Glossary

- **Scanner**: The backend pipeline that accepts a repository input and produces a ranked issue report.
- **Issue**: A single detected code vulnerability or risk, conforming to the Issue Schema defined in Requirement 6.
- **Scan**: One end-to-end execution of the Scanner pipeline for a given repository input, identified by a `scan_id`.
- **Static_Analyzer**: The backend component that applies rule-based checks to parsed ASTs.
- **AI_Agent**: The backend component that calls Claude per issue to produce explanations and fix diffs.
- **Duplicate_Detector**: The backend component that embeds issue descriptions, stores them in ChromaDB, and identifies near-duplicate issues.
- **Ranker**: The backend component that scores and sorts issues by severity, priority, duplicate factor, and recency.
- **API**: The FastAPI/Uvicorn HTTP service running on `localhost:8000` by default.
- **Frontend**: The Vite + React application in `frontend/src/`.
- **BugDetailsDrawer**: The existing React component (`src/components/Modals/BugDetailsDrawer.jsx`) that renders single-issue detail.
- **TabRepositoryScanner**: The existing React component (`src/components/Tabs/TabRepositoryScanner.jsx`) for repository input and scan progress.
- **TabBugManagement**: The existing React component (`src/components/Tabs/TabBugManagement.jsx`) for the ranked issue list.
- **useBugTracker**: The existing React context provider (`src/useBugTracker.jsx`) that owns all shared application state.
- **api_js**: The existing client module (`src/api.js`) that wraps all HTTP calls to the API.
- **mockData_js**: The file `src/mockData.js` kept as a dev fixture but never imported in live scan flow.
- **error_type**: A string discriminator on API error responses; one of: `private_repo | not_found | rate_limited | invalid_url | clone_failed | analysis_failed`.
- **DATABASE_URL**: Environment variable pointing to the SQLAlchemy database connection string.
- **ANTHROPIC_API_KEY**: Environment variable holding the Claude API key.
- **ChromaDB**: An embedded vector database used by the Duplicate_Detector.
- **scan_id**: A UUID string returned by `POST /api/scan` that identifies a specific Scan.

---

## Requirements

### Requirement 1: Repository Input Acceptance

**User Story:** As a security engineer, I want to submit a public GitHub URL or a ZIP archive for scanning, so that I can analyze any codebase without needing repository credentials.

#### Acceptance Criteria

1. WHEN a `POST /api/scan` request is received with a `repo_url` field containing a valid public GitHub URL, THE Scanner SHALL clone the repository using `git clone --depth=1` and return a `scan_id` within 5 seconds of receiving the request.
2. WHEN a `POST /api/scan` request is received with a `file` multipart field containing a ZIP archive, THE Scanner SHALL extract the archive to a temporary directory and return a `scan_id` within 5 seconds.
3. WHEN `git clone` returns a non-zero exit code indicating repository not found, THE API SHALL return HTTP 422 with `error_type: "not_found"` and a human-readable `message`.
4. WHEN `git clone` returns a non-zero exit code indicating a private or authentication-required repository, THE API SHALL return HTTP 422 with `error_type: "private_repo"` and a human-readable `message`.
5. WHEN the GitHub API returns HTTP 429 or a `X-RateLimit-Remaining: 0` header during any preflight check, THE API SHALL return HTTP 422 with `error_type: "rate_limited"` and a human-readable `message`.
6. IF the submitted `repo_url` cannot be parsed as a valid `github.com` URL, THEN THE API SHALL return HTTP 422 with `error_type: "invalid_url"` and a human-readable `message` without attempting a clone.
7. WHEN clone or extraction fails for any reason not covered by criteria 3–6, THE API SHALL return HTTP 422 with `error_type: "clone_failed"` and a human-readable `message`.
8. THE Scanner SHALL skip files whose paths contain any of the segments: `node_modules`, `.git`, `vendor`, `dist`, `build`, `__pycache__`, `.venv`.
9. THE Scanner SHALL cap the total number of files analyzed per Scan at 500 and SHALL include a `files_capped: true` flag and `files_analyzed` count in the scan results when the cap is reached.

---

### Requirement 2: Language Detection

**User Story:** As a security engineer, I want the scanner to detect programming languages present in the repository, so that I know which analysis rules were applied.

#### Acceptance Criteria

1. WHEN a Scan is initiated, THE Scanner SHALL detect languages by file extension for at minimum: Python (`.py`), JavaScript (`.js`, `.jsx`), TypeScript (`.ts`, `.tsx`), and Java (`.java`).
2. THE Scanner SHALL skip binary files (determined by attempting UTF-8 decode of the first 512 bytes and checking for null bytes) and SHALL NOT include them in language counts.
3. WHEN language detection completes, THE Scanner SHALL store a `languages` map of `{ language_name: file_count }` in the scan record.
4. THE Scanner SHALL include the detected `languages` map in the response body of `GET /api/scan/{scan_id}/results`.

---

### Requirement 3: AST Parsing

**User Story:** As a security engineer, I want real AST-based parsing applied to source files, so that static analysis rules operate on the actual code structure rather than text heuristics alone.

#### Acceptance Criteria

1. WHEN a Python file is parsed, THE Static_Analyzer SHALL use Python's built-in `ast` module to produce an AST.
2. WHEN a JavaScript, TypeScript, or Java file is parsed, THE Static_Analyzer SHALL use `tree-sitter` to produce an AST.
3. IF an AST parse fails for a given file (syntax error or unsupported construct), THEN THE Static_Analyzer SHALL log the failure and skip that file without crashing the pipeline.
4. THE Static_Analyzer SHALL record the number of successfully parsed files and the number of skipped files, and SHALL include both counts in `GET /api/scan/{scan_id}/results`.

---

### Requirement 4: Static Analysis Rules

**User Story:** As a security engineer, I want real rule-based checks applied to parsed ASTs, so that I receive actionable, evidence-based vulnerability findings.

#### Acceptance Criteria

1. THE Static_Analyzer SHALL check for SQL injection via string concatenation (rule ID: `SQL_INJECTION`) in Python, JavaScript, and Java files.
2. THE Static_Analyzer SHALL check for use of `eval` or `exec` on dynamic input (rule ID: `EVAL_EXEC_USE`) in Python and JavaScript files.
3. THE Static_Analyzer SHALL check for hardcoded secret patterns (AWS keys, generic passwords, private key headers) in all supported languages (rule ID: `HARDCODED_SECRET`).
4. THE Static_Analyzer SHALL check for null/None dereference on unchecked return values (rule ID: `NULL_DEREFERENCE`) in Python and Java files.
5. THE Static_Analyzer SHALL check for unclosed file or network resource handles (rule ID: `UNCLOSED_RESOURCE`) in Python files.
6. THE Static_Analyzer SHALL check for unhandled I/O exceptions in file read/write operations (rule ID: `UNHANDLED_IO`) in Python files.
7. THE Static_Analyzer SHALL check for infinite loop risk (while True / for loop with no break) (rule ID: `INFINITE_LOOP`) in Python and JavaScript files.
8. WHEN a rule check produces a hit, THE Static_Analyzer SHALL record: `file_path`, `line_start`, `line_end`, `code_snippet` (up to 5 surrounding lines), `issue_type` (descriptive label), `rule_id`, and an initial `severity` classification (`critical | high | medium | low`).
9. THE Static_Analyzer SHALL assign an initial `priority` (`P1 | P2 | P3 | P4`) based on severity: critical → P1, high → P2, medium → P3, low → P4.

---

### Requirement 5: AI Agent Layer

**User Story:** As a security engineer, I want an AI-generated explanation and concrete fix for each detected issue, so that I can understand the vulnerability and apply a targeted remediation without deep manual analysis.

#### Acceptance Criteria

1. WHEN `ANTHROPIC_API_KEY` is set and a Scan produces at least one Issue, THE AI_Agent SHALL call Claude once per Issue with a prompt containing the `code_snippet`, `rule_id`, `issue_type`, `file_path`, and up to 20 lines of surrounding context.
2. THE AI_Agent SHALL request a structured JSON response from Claude containing: `confirmed_severity` (`critical|high|medium|low`), `confirmed_priority` (`P1|P2|P3|P4`), `ai_explanation` (plain-English string), and `ai_suggested_fix_diff` (unified diff string).
3. WHEN Claude returns a response that cannot be parsed as valid JSON, THE AI_Agent SHALL log the raw response, set `ai_explanation: null` and `ai_suggested_fix_diff: null` for that Issue, and continue processing remaining Issues without crashing the pipeline.
4. WHEN `ANTHROPIC_API_KEY` is not set, THE AI_Agent SHALL set `ai_explanation` to `"AI explanation unavailable — set ANTHROPIC_API_KEY to enable AI-generated fixes"` and `ai_suggested_fix_diff` to `null` for every Issue, without making any external API calls.
5. THE AI_Agent SHALL update `severity` and `priority` on the Issue using `confirmed_severity` and `confirmed_priority` from Claude when those fields are valid; otherwise THE AI_Agent SHALL retain the Static_Analyzer's initial values.
6. WHEN all AI calls for a Scan are complete, THE AI_Agent SHALL record total AI tokens consumed and total AI call duration in the scan metadata.

---

### Requirement 6: Issue Data Schema

**User Story:** As a frontend developer, I want a consistent, fully-typed issue schema returned by the API, so that the frontend can render issue details without defensive null-checking on every field.

#### Acceptance Criteria

1. THE API SHALL return every Issue with exactly the following fields: `id` (string UUID), `file_path` (string), `line_start` (integer), `line_end` (integer), `code_snippet` (string), `issue_type` (string), `rule_id` (string), `severity` (`critical|high|medium|low`), `priority` (`P1|P2|P3|P4`), `ai_explanation` (string or null), `ai_suggested_fix_diff` (string or null), `is_duplicate_of` (string UUID or null), `similarity_score` (float or null), `created_at` (ISO 8601 datetime string).
2. IF any required field is absent from the Claude response or internal computation, THEN THE API SHALL substitute a typed null or default value rather than omitting the field.
3. THE API SHALL validate the Issue schema using Pydantic before persisting and returning; schema validation failures SHALL be logged and the Issue SHALL be stored with a `schema_error: true` flag rather than crashing the pipeline.

---

### Requirement 7: Duplicate Detection

**User Story:** As a security engineer, I want similar or duplicate issues grouped together, so that I can prioritize the unique root causes instead of triaging the same problem repeatedly.

#### Acceptance Criteria

1. WHEN a Scan produces Issues, THE Duplicate_Detector SHALL embed each Issue's concatenated `issue_type` + `code_snippet` using `sentence-transformers` model `all-MiniLM-L6-v2`.
2. THE Duplicate_Detector SHALL store embeddings in ChromaDB in local embedded mode under a collection namespaced by `scan_id`.
3. WHEN an embedding is stored, THE Duplicate_Detector SHALL query ChromaDB for the nearest neighbor within the same Scan; if cosine similarity ≥ 0.85, THE Duplicate_Detector SHALL set `is_duplicate_of` to the ID of the first-seen similar Issue and `similarity_score` to the computed cosine similarity value.
4. THE Duplicate_Detector SHALL NOT mark the first occurrence of an Issue as a duplicate of itself.
5. WHEN duplicate detection completes, THE Duplicate_Detector SHALL include a `duplicate_groups` list in the scan results, where each group contains the canonical issue ID and the list of duplicate issue IDs.

---

### Requirement 8: Enrichment and Ranking

**User Story:** As a security engineer, I want issues ranked by risk so that I can address the most dangerous vulnerabilities first without manually sorting through a flat list.

#### Acceptance Criteria

1. THE Ranker SHALL assign a numeric score to each Issue using the formula: `severity_weight + priority_weight - duplicate_penalty`, where `severity_weight` is `critical=40, high=30, medium=20, low=10`; `priority_weight` is `P1=10, P2=7, P3=4, P4=1`; and `duplicate_penalty` is `5` if `is_duplicate_of` is set, else `0`.
2. THE Ranker SHALL sort Issues in descending score order in the `GET /api/scan/{scan_id}/results` response.
3. THE API SHALL include in the results response a `summary` object containing: `total_issues` (integer), `by_severity` (`{ critical, high, medium, low }` counts), `by_priority` (`{ P1, P2, P3, P4 }` counts), `duplicate_count` (integer), `files_analyzed` (integer), `languages` (map), `files_capped` (boolean), and `health_score` (integer 0–100, computed as `max(0, 100 - critical*15 - high*8 - medium*3 - low*1)`).

---

### Requirement 9: Asynchronous Scan API

**User Story:** As a frontend developer, I want to poll scan status so that I can display real progress to the user without blocking the UI on a long-running backend operation.

#### Acceptance Criteria

1. WHEN `POST /api/scan` is called with valid input, THE API SHALL immediately return HTTP 202 with `{ "scan_id": "<uuid>", "status": "queued" }` and begin processing asynchronously in a background task.
2. THE API SHALL expose `GET /api/scan/{scan_id}/status` returning `{ "scan_id": "<uuid>", "status": "queued|running|complete|failed", "progress_pct": <0–100 integer>, "stage": "<human-readable stage name>", "error": <null or error object> }`.
3. WHEN the Scan transitions through pipeline stages (clone → language_detection → ast_parse → static_analysis → ai_agent → duplicate_detection → ranking → complete), THE API SHALL update `progress_pct` and `stage` accordingly with monotonically increasing progress values.
4. WHEN `GET /api/scan/{scan_id}/results` is called before the Scan status is `complete`, THE API SHALL return HTTP 202 with `{ "status": "running", "progress_pct": <integer> }`.
5. WHEN `GET /api/scan/{scan_id}/results` is called after the Scan status is `complete`, THE API SHALL return HTTP 200 with the full enriched report including the `summary` object, the ranked `issues` array, the `duplicate_groups` list, and the `file_tree` array.
6. WHEN a Scan fails at any pipeline stage, THE API SHALL set status to `failed` and populate the `error` field with `{ "error_type": "<error_type>", "message": "<string>" }` using the `error_type` values defined in the Glossary.
7. THE API SHALL expose `GET /api/bugs/{issue_id}` returning the full Issue object for a previously scanned issue.

---

### Requirement 10: Data Persistence

**User Story:** As a security engineer, I want scan results persisted between restarts, so that I can review historical scans without re-running the pipeline.

#### Acceptance Criteria

1. THE API SHALL use SQLAlchemy with `DATABASE_URL` from the environment (defaulting to `sqlite:///./bugtracker.db`) to persist the following entities: `repos`, `scans`, `bug_reports`, `status_history`, and `scan_logs`.
2. WHEN `DATABASE_URL` is changed to a PostgreSQL connection string, THE API SHALL connect to PostgreSQL without any code changes.
3. THE API SHALL run Alembic migrations (or `create_all`) on startup to ensure tables exist before accepting requests.
4. THE API SHALL store each Issue in the `bug_reports` table with all fields from the Issue Schema (Requirement 6).
5. WHEN a bug's status is updated via `PATCH /api/bugs/{issue_id}/resolve`, THE API SHALL persist the new status and append a record to `status_history`.
6. WHEN engineer notes are updated via `PATCH /api/bugs/{issue_id}/notes`, THE API SHALL persist the updated `engineer_notes` field on the `bug_reports` row.

---

### Requirement 11: Graceful AI Degradation

**User Story:** As a system operator, I want the platform to function correctly without an AI key, so that static analysis results are still available even when AI features are disabled.

#### Acceptance Criteria

1. WHEN `ANTHROPIC_API_KEY` is absent from the environment, THE Scanner SHALL complete the full pipeline (clone → language detection → AST parse → static analysis → duplicate detection → ranking) and return results with `ai_explanation` set to the placeholder string defined in Requirement 5, Criterion 4.
2. WHEN `ANTHROPIC_API_KEY` is absent, THE Frontend SHALL display the text `"AI analysis disabled"` in the AI explanation section of BugDetailsDrawer instead of a null or empty state.
3. WHEN `ANTHROPIC_API_KEY` is added to the environment and the API is restarted, THE AI_Agent SHALL call Claude for all subsequent Scans with zero code changes required.

---

### Requirement 12: Frontend API Wiring — No Mock Fallback in Scan Flow

**User Story:** As a security engineer, I want the frontend to show only real backend data after a scan, so that I never act on fabricated vulnerability reports.

#### Acceptance Criteria

1. THE api_js SHALL remove the `fetchGitHubRepo` / `github.js` call from the scan flow and replace it with `POST /api/scan` + `GET /api/scan/{scan_id}/status` polling + `GET /api/scan/{scan_id}/results`.
2. WHEN the API returns an HTTP error response during a scan, THE api_js SHALL throw an error object with `{ message, type }` matching the `error_type` from the response body; THE api_js SHALL NOT fall back to `mockData.js` data.
3. THE useBugTracker `runScan` function SHALL replace the simulated progress animation with real polling of `GET /api/scan/{scan_id}/status` every 2 seconds, updating `scanProgress` and `scanStage` from the response fields `progress_pct` and `stage`.
4. WHEN `GET /api/scan/{scan_id}/results` returns HTTP 200 with a valid results body, THE useBugTracker SHALL map the `issues` array to the existing `bugs` state, `summary` to `stats`, and `file_tree` to the `aiSummary.fileSummaries` shape expected by TabAiArchitecture.
5. THE mockData_js file SHALL remain in the repository untouched and SHALL be importable, but no import of `DEFAULT_BUGS`, `DEFAULT_STATS`, or `DEFAULT_AI_SUMMARY` from mockData_js SHALL appear in the live scan code path of `api_js` or `useBugTracker`.

---

### Requirement 13: Frontend Error Display

**User Story:** As a security engineer, I want to see a specific, correctly worded error message for every failure mode, so that I know exactly what went wrong and what action to take.

#### Acceptance Criteria

1. WHEN `scanError.type === "private_repo"`, THE TabRepositoryScanner SHALL display: `"Repository is private. Only public repositories can be analyzed without authentication."`.
2. WHEN `scanError.type === "not_found"`, THE TabRepositoryScanner SHALL display: `"Repository not found. Check the URL and ensure the repository is public."`.
3. WHEN `scanError.type === "rate_limited"`, THE TabRepositoryScanner SHALL display: `"GitHub API rate limit reached. Please wait 60 seconds and try again."`.
4. WHEN `scanError.type === "invalid_url"`, THE TabRepositoryScanner SHALL display: `"Invalid repository URL. Please enter a valid github.com URL."`.
5. WHEN `scanError.type === "clone_failed"`, THE TabRepositoryScanner SHALL display: `"Repository clone failed. The repository may be empty or the server is unreachable."`.
6. WHEN `scanError.type === "analysis_failed"`, THE TabRepositoryScanner SHALL display: `"Analysis failed during processing. Check the backend logs for details."`.
7. WHEN `scanError.type` is any unrecognized value, THE TabRepositoryScanner SHALL display: `"An unexpected scan error occurred. Please try again."`.
8. THE TabRepositoryScanner SHALL never silently swallow an API error and display stale or mock data in place of a real error state.

---

### Requirement 14: AI Suggested Fix Display

**User Story:** As a security engineer, I want to see the AI-generated fix as a readable before/after diff inside the bug inspector, so that I can immediately understand what code change is needed.

#### Acceptance Criteria

1. WHEN `currentBug.ai_suggested_fix_diff` is a non-null string, THE BugDetailsDrawer SHALL render it as a `<pre>` block with lines prefixed by `-` rendered in red and lines prefixed by `+` rendered in green.
2. WHEN `currentBug.ai_explanation` is a non-null string, THE BugDetailsDrawer SHALL render it in the "What is wrong" section, replacing the existing `bug.wrong` field display.
3. WHEN `currentBug.ai_explanation` equals the degradation placeholder string (Requirement 5, Criterion 4), THE BugDetailsDrawer SHALL render the section header as `"AI Analysis Disabled"` instead of `"AI Explanation"`.
4. WHEN `currentBug.ai_suggested_fix_diff` is null, THE BugDetailsDrawer SHALL render a muted placeholder `"No AI fix suggestion available for this issue."` rather than collapsing the section entirely.
5. THE TabBugManagement bug list cards SHALL display an `"AI Fix Available"` badge when `ai_suggested_fix_diff` is non-null.

---

### Requirement 15: Large Repository Handling

**User Story:** As a security engineer, I want the scanner to handle large repositories gracefully and inform me when analysis is capped, so that I understand the scope of the results.

#### Acceptance Criteria

1. WHEN a Scan reaches the 500-file analysis cap (Requirement 1, Criterion 9), THE Scanner SHALL continue to completion with the capped file set rather than failing.
2. WHEN `files_capped: true` is present in the scan results summary, THE Frontend SHALL display a dismissible notice: `"Analysis capped at 500 files. Results may not cover the full repository."`.
3. THE Scanner SHALL skip files whose path matches any of: minified files (`.min.js`, `.min.css`), generated lockfiles (`package-lock.json`, `yarn.lock`, `poetry.lock`), compiled output (`.pyc`, `.class`, `.map`), and binary assets (`.png`, `.jpg`, `.gif`, `.woff`, `.ttf`, `.ico`).
4. WHEN the repository contains more than 500 skipped/excluded files, THE scan results SHALL include a `skipped_files` count so the user understands the total exclusion scope.

---

### Requirement 16: Backend Setup Documentation and Environment Configuration

**User Story:** As a new developer, I want a complete README and `.env.example` so that I can get the backend running locally without guessing at configuration.

#### Acceptance Criteria

1. THE Scanner SHALL read all configuration from environment variables and SHALL NOT contain any hardcoded configuration values (URLs, keys, paths) outside of documented defaults.
2. THE API SHALL load environment variables from `backend/.env` using `python-dotenv`; if the file is absent, THE API SHALL fall back to system environment variables without error.
3. A file `backend/.env.example` SHALL exist and SHALL contain placeholder entries for: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `CHROMA_PERSIST_DIR`, `MAX_FILES_PER_SCAN`, `CLONE_TIMEOUT_SECONDS`, and `CORS_ORIGINS`.
4. A file `backend/README.md` SHALL exist containing: prerequisites (Python 3.11+, Git), exact `pip install` command, exact `uvicorn` run command, a table of all environment variables with defaults, and a brief description of each pipeline stage.
```
