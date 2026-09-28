# Requirements Document

## Introduction

This document specifies requirements for improving the LLM-based bug detection pipeline in the BugTracker system. A comprehensive audit revealed 15 architectural gaps, 7 drop points where findings can be lost, limited context availability (8KB maximum with no cross-file analysis), sequential execution causing slow analysis, and information loss between database and frontend.

The improvements will address these gaps systematically to create a production-ready, reliable, and efficient bug detection pipeline that can run on resource-constrained hardware (RTX 2050 4GB) while maintaining high detection accuracy and preventing information loss.

## Glossary

- **LLM_Pipeline**: The complete bug detection pipeline that uses Large Language Model analysis
- **Context_Window**: The amount of source code and surrounding information provided to the LLM during analysis
- **Drop_Point**: A location in the pipeline where findings or metadata can be lost during processing
- **Semantic_Analyzer**: The component that uses LLM reasoning to detect semantic bugs and logic errors
- **Static_Analyzer**: The rule-based component that detects syntactic and pattern-based bugs
- **Analysis_Run**: A single execution of the bug detection pipeline on a repository
- **Candidate_Issue**: A potential bug identified by the pipeline requiring verification
- **Evidence**: Supporting information (code snippets, context, reasoning) that justifies a finding
- **Deduplication_Engine**: Component that identifies and merges duplicate findings
- **Repository_Index**: Pre-built index of repository structure for efficient cross-file analysis
- **Hardware_Constraint**: RTX 2050 4GB GPU memory limitation
- **Ollama_Provider**: Local LLM inference service running on user hardware
- **Parallel_Executor**: Component that processes multiple analysis tasks concurrently
- **Context_Budget**: Maximum amount of context (in tokens or characters) that can be provided to the LLM

## Requirements

### Requirement 1: Context Enhancement

**User Story:** As a bug detection engineer, I want the LLM to have access to comprehensive cross-file context, so that it can detect bugs that depend on understanding how functions interact across multiple files.

#### Acceptance Criteria

1. THE Repository_Index SHALL build a complete index of all functions, classes, and their call relationships before LLM analysis begins
2. WHEN analyzing a function, THE Context_Window SHALL include caller and callee function signatures from the Repository_Index
3. WHEN analyzing a function, THE Context_Window SHALL include type definitions and interfaces used by the function
4. THE Context_Budget SHALL expand from 8KB to at least 32KB per analysis call
5. WHEN a function calls external dependencies, THE Context_Window SHALL include imported function signatures and their documentation
6. THE Repository_Index SHALL cache type information and function signatures to avoid redundant parsing
7. FOR ALL analysis requests, building context from the Repository_Index SHALL complete within 200ms per function

### Requirement 2: Prevent Information Drop Points

**User Story:** As a security analyst, I want all bug findings and their supporting evidence to be preserved through the entire pipeline, so that no critical security issues are lost.

#### Acceptance Criteria

1. THE LLM_Pipeline SHALL persist raw LLM responses to the database before any parsing or validation
2. WHEN parsing fails, THE LLM_Pipeline SHALL store the unparsed response with error metadata
3. THE Evidence_Builder SHALL attach complete source code snippets to every finding
4. THE Evidence_Builder SHALL attach LLM reasoning and confidence scores to every finding
5. WHEN deduplication merges findings, THE Deduplication_Engine SHALL preserve evidence from all merged instances
6. THE Database_Schema SHALL store structured evidence in JSONB fields with indexed access
7. THE Frontend_API SHALL return all evidence fields without filtering or transformation
8. FOR ALL findings, a complete audit trail from LLM response to frontend display SHALL be traceable

### Requirement 3: Parallel Execution

**User Story:** As a developer, I want repository analysis to complete quickly, so that I can iterate rapidly on fixes without waiting hours for scan results.

#### Acceptance Criteria

1. THE Parallel_Executor SHALL process multiple functions concurrently within hardware constraints
2. THE Parallel_Executor SHALL maintain at most 2 concurrent LLM inference requests to respect Hardware_Constraint
3. THE Parallel_Executor SHALL queue additional functions when concurrent limit is reached
4. WHEN Hardware_Constraint causes memory pressure, THE Parallel_Executor SHALL reduce concurrency to 1
5. THE Parallel_Executor SHALL process file parsing and context building in parallel with LLM inference
6. THE Parallel_Executor SHALL batch database writes to reduce transaction overhead
7. FOR ALL repositories under 10,000 lines, analysis SHALL complete in under 5 minutes on Hardware_Constraint

### Requirement 4: Architectural Gap Resolution - Drop Point 1 (LLM Response Storage)

**User Story:** As a system administrator, I want raw LLM responses preserved, so that parsing errors or pipeline crashes do not cause data loss.

#### Acceptance Criteria

1. THE LLM_Pipeline SHALL create a database record for each LLM call before invoking the Ollama_Provider
2. THE LLM_Pipeline SHALL store raw response text immediately after receiving from Ollama_Provider
3. THE LLM_Pipeline SHALL store response metadata including model, timestamp, latency, and token counts
4. IF parsing the response fails, THEN THE LLM_Pipeline SHALL mark the record as "parse_failed" with error details
5. THE Database_Schema SHALL include an llm_responses table with columns for raw_response, parsed_findings, error_log, and status

### Requirement 5: Architectural Gap Resolution - Drop Point 2 (Evidence Attachment)

**User Story:** As a security reviewer, I want to see the exact code and reasoning that led to each finding, so that I can validate whether it is a true positive.

#### Acceptance Criteria

1. THE Evidence_Builder SHALL extract source code snippets with 5 lines of context before and after each finding
2. THE Evidence_Builder SHALL include the LLM's explanation and confidence score in the evidence field
3. THE Evidence_Builder SHALL capture function signatures and type annotations in evidence
4. THE Evidence_Builder SHALL include cross-file references when the bug involves multiple files
5. IF source code cannot be retrieved, THEN THE Evidence_Builder SHALL log the error and mark evidence as incomplete
6. THE Database_Schema SHALL validate evidence completeness before marking a finding as "validated"

### Requirement 6: Architectural Gap Resolution - Drop Point 3 (Deduplication Preservation)

**User Story:** As a bug tracking manager, I want merged duplicate findings to retain all original evidence, so that no diagnostic information is lost during consolidation.

#### Acceptance Criteria

1. WHEN THE Deduplication_Engine identifies duplicate findings, it SHALL create a merged record with a unique ID
2. THE Deduplication_Engine SHALL store references to all original finding IDs in a duplicates array
3. THE Deduplication_Engine SHALL merge evidence fields into a composite evidence structure
4. THE Deduplication_Engine SHALL preserve the highest confidence score among duplicates
5. THE Deduplication_Engine SHALL preserve the most severe severity level among duplicates
6. THE Frontend_API SHALL provide access to individual duplicate records when requested

### Requirement 7: Architectural Gap Resolution - Drop Point 4 (Frontend Data Loss)

**User Story:** As a frontend developer, I want the API to return complete finding records with all metadata, so that the UI can display rich diagnostic information.

#### Acceptance Criteria

1. THE Frontend_API SHALL return all finding fields including evidence, metadata, and audit trail
2. THE Frontend_API SHALL support filtering and pagination without truncating evidence fields
3. THE Frontend_API SHALL return findings in JSON format with nested evidence structure preserved
4. THE Frontend_API SHALL include API versioning to prevent breaking changes
5. WHEN evidence exceeds size limits, THE Frontend_API SHALL provide a reference URL to fetch full evidence

### Requirement 8: Architectural Gap Resolution - Drop Point 5 (Parsing Error Recovery)

**User Story:** As a pipeline operator, I want parsing errors to be recoverable, so that a malformed LLM response does not block the entire scan.

#### Acceptance Criteria

1. IF THE LLM_Pipeline fails to parse JSON response, THEN it SHALL attempt text extraction using regex fallback
2. IF regex fallback succeeds, THEN THE LLM_Pipeline SHALL create findings with "fallback_parse" source metadata
3. IF both parsing methods fail, THEN THE LLM_Pipeline SHALL store the raw response for manual review
4. THE LLM_Pipeline SHALL continue processing remaining functions after a parsing failure
5. THE LLM_Pipeline SHALL log parsing failures with function name, line number, and error details

### Requirement 9: Architectural Gap Resolution - Drop Point 6 (Context Retrieval Failures)

**User Story:** As a pipeline developer, I want context retrieval to be resilient, so that missing imports or unavailable files do not cause analysis failures.

#### Acceptance Criteria

1. WHEN THE Context_Retriever cannot locate an imported module, it SHALL use cached signatures from Repository_Index
2. WHEN THE Context_Retriever encounters a file read error, it SHALL log the error and proceed with partial context
3. THE Context_Retriever SHALL implement retry logic with exponential backoff for transient file system errors
4. THE Context_Retriever SHALL track context completeness percentage in metadata
5. IF context completeness falls below 70%, THEN THE LLM_Pipeline SHALL mark the analysis with "limited_context" flag

### Requirement 10: Architectural Gap Resolution - Drop Point 7 (Database Transaction Failures)

**User Story:** As a database administrator, I want database writes to be atomic and recoverable, so that partial failures do not corrupt the analysis results.

#### Acceptance Criteria

1. THE LLM_Pipeline SHALL wrap all database writes in transactions with rollback capability
2. WHEN a database write fails, THE LLM_Pipeline SHALL retry up to 3 times with exponential backoff
3. IF all retries fail, THEN THE LLM_Pipeline SHALL write findings to a local recovery file
4. THE LLM_Pipeline SHALL provide a recovery utility that imports findings from recovery files
5. THE Database_Schema SHALL implement foreign key constraints with ON DELETE CASCADE for data consistency

### Requirement 11: Cross-File Analysis

**User Story:** As a security engineer, I want the LLM to detect bugs that span multiple files, so that inter-module vulnerabilities are not missed.

#### Acceptance Criteria

1. THE Repository_Index SHALL build a call graph connecting all function invocations across files
2. THE Repository_Index SHALL identify data flow paths that cross file boundaries
3. WHEN analyzing a function, THE Context_Window SHALL include summaries of all functions it calls in other files
4. THE Semantic_Analyzer SHALL detect taint propagation bugs across file boundaries
5. THE Semantic_Analyzer SHALL detect authentication bypass bugs involving multiple modules
6. FOR ALL cross-file bugs, the evidence SHALL reference all involved files with line numbers

### Requirement 12: Resource-Constrained Execution

**User Story:** As a developer with limited hardware, I want the pipeline to run efficiently on my RTX 2050 4GB GPU, so that I can perform local analysis without cloud costs.

#### Acceptance Criteria

1. THE Ollama_Provider SHALL configure model quantization to fit within 3.5GB VRAM limit
2. THE Parallel_Executor SHALL monitor GPU memory usage and throttle concurrency when usage exceeds 80%
3. THE LLM_Pipeline SHALL implement model caching to avoid repeated loading between function analyses
4. THE LLM_Pipeline SHALL spill to CPU inference if GPU memory exhaustion is detected
5. THE Context_Budget SHALL be dynamically adjusted based on available GPU memory
6. FOR ALL analysis runs, peak GPU memory usage SHALL NOT exceed 3.8GB

### Requirement 13: Prompt Engineering and Output Quality

**User Story:** As a prompt engineer, I want standardized, optimized prompts that produce consistent, parseable responses, so that parsing errors are minimized.

#### Acceptance Criteria

1. THE LLM_Pipeline SHALL use a versioned prompt template with strict JSON output schema
2. THE Prompt_Builder SHALL include few-shot examples of correct bug reports in the prompt
3. THE Prompt_Builder SHALL explicitly instruct the LLM to return ONLY valid JSON without markdown code blocks
4. THE LLM_Pipeline SHALL include a JSON schema validator that checks response format before parsing
5. WHEN validation fails, THE LLM_Pipeline SHALL request regeneration with a corrective prompt
6. THE LLM_Pipeline SHALL track prompt version in finding metadata for reproducibility

### Requirement 14: Performance Monitoring and Metrics

**User Story:** As a DevOps engineer, I want detailed performance metrics, so that I can identify bottlenecks and optimize the pipeline.

#### Acceptance Criteria

1. THE LLM_Pipeline SHALL record timing metrics for each pipeline stage (indexing, context building, LLM inference, validation, deduplication, database writes)
2. THE LLM_Pipeline SHALL track per-function metrics including context size, inference time, and confidence scores
3. THE LLM_Pipeline SHALL expose metrics via Prometheus-compatible endpoint
4. THE LLM_Pipeline SHALL log slow functions (>30s inference time) for manual review
5. THE LLM_Pipeline SHALL calculate and report throughput metrics (functions analyzed per minute)
6. THE Database_Schema SHALL store aggregate metrics per Analysis_Run for historical comparison

### Requirement 15: Incremental Analysis

**User Story:** As a developer running frequent scans, I want incremental analysis that only re-scans changed files, so that subsequent runs are fast.

#### Acceptance Criteria

1. THE Repository_Index SHALL compute file content hashes to detect changes since previous Analysis_Run
2. THE LLM_Pipeline SHALL skip analysis of unchanged functions based on hash comparison
3. THE LLM_Pipeline SHALL re-analyze functions if their dependencies (callees) have changed
4. THE Database_Schema SHALL track file hashes per Analysis_Run for change detection
5. WHEN running incremental analysis, THE LLM_Pipeline SHALL copy unchanged findings from previous run
6. FOR ALL repositories with <10% file changes, incremental analysis SHALL complete in under 1 minute

### Requirement 16: Semantic Fact Validation

**User Story:** As a quality assurance engineer, I want LLM findings validated against actual source code, so that hallucinated bugs are rejected before reaching the frontend.

#### Acceptance Criteria

1. THE Evidence_Validator SHALL verify that line numbers in findings correspond to actual source lines
2. THE Evidence_Validator SHALL verify that referenced function names exist in the codebase
3. THE Evidence_Validator SHALL verify that the code snippet in evidence matches the actual source file
4. IF validation fails, THEN THE LLM_Pipeline SHALL mark the finding as "validation_failed" and exclude it from frontend results
5. THE Evidence_Validator SHALL perform AST-based validation to confirm that the bug pattern actually exists
6. THE Database_Schema SHALL track validation status and failure reasons for each finding

### Requirement 17: Configuration and Tuning

**User Story:** As a system integrator, I want configurable pipeline parameters, so that I can tune performance for different hardware and accuracy requirements.

#### Acceptance Criteria

1. THE LLM_Pipeline SHALL read configuration from environment variables and config files
2. THE Configuration_Schema SHALL support tuning parameters for context size, concurrency, timeout, and model selection
3. THE Configuration_Schema SHALL support per-repository overrides for specialized analysis requirements
4. THE LLM_Pipeline SHALL validate configuration on startup and report errors clearly
5. THE Configuration_Schema SHALL provide sensible defaults optimized for Hardware_Constraint
6. THE LLM_Pipeline SHALL support hot-reload of configuration without requiring restart

### Requirement 18: Error Handling and Recovery

**User Story:** As a reliability engineer, I want the pipeline to gracefully handle errors and continue analysis, so that one problematic function does not crash the entire scan.

#### Acceptance Criteria

1. THE LLM_Pipeline SHALL wrap each function analysis in a try-catch block with error logging
2. WHEN function analysis fails, THE LLM_Pipeline SHALL record the error and continue with next function
3. THE LLM_Pipeline SHALL implement circuit breaker pattern to temporarily skip functions that repeatedly fail
4. WHEN Ollama_Provider is unavailable, THE LLM_Pipeline SHALL queue analysis for retry
5. THE LLM_Pipeline SHALL provide a manual retry command for failed functions
6. FOR ALL analysis runs, the pipeline SHALL complete even if some functions fail, and report success/failure counts

### Requirement 19: Deduplication Precision

**User Story:** As a developer reviewing findings, I want accurate deduplication that preserves semantically different bugs, so that distinct issues are not incorrectly merged.

#### Acceptance Criteria

1. THE Deduplication_Engine SHALL compare findings using semantic similarity based on bug type, location, and evidence
2. THE Deduplication_Engine SHALL consider findings as duplicates only if they occur within 5 lines of each other
3. THE Deduplication_Engine SHALL preserve findings from different detection sources (Static_Analyzer vs LLM) as separate issues
4. THE Deduplication_Engine SHALL NOT merge findings with different severity levels
5. THE Deduplication_Engine SHALL provide a similarity score (0-1) for each merge decision
6. THE Database_Schema SHALL store deduplication metadata including similarity score and merge reason

### Requirement 20: Output Format Parser Resilience

**User Story:** As a parsing engineer, I want the parser to handle diverse LLM output formats, so that minor formatting variations do not cause parsing failures.

#### Acceptance Criteria

1. THE Output_Parser SHALL strip markdown code block markers (```json) before JSON parsing
2. THE Output_Parser SHALL handle both single-finding and array-of-findings response formats
3. THE Output_Parser SHALL extract findings from free-text responses using regex fallback
4. THE Output_Parser SHALL normalize field names that vary in capitalization (severity vs Severity)
5. THE Output_Parser SHALL provide default values for optional fields that are missing
6. THE Output_Parser SHALL log parsing warnings without failing the entire response

### Requirement 21: Round-Trip Property - JSON Serialization

**User Story:** As a data integrity engineer, I want to ensure that finding data survives serialization and deserialization without loss, so that evidence remains intact through database and API layers.

#### Acceptance Criteria

1. THE Pretty_Printer SHALL format finding records into valid JSON with all fields preserved
2. THE Parser SHALL parse pretty-printed JSON back into equivalent finding objects
3. FOR ALL valid finding records, parsing then printing then parsing SHALL produce an equivalent finding object (round-trip property)
4. THE Parser SHALL validate that required fields (id, title, severity, file_path, line_start) are present
5. THE Pretty_Printer SHALL escape special characters in evidence text to prevent JSON syntax errors

