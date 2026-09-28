# Implementation Plan: LLM Pipeline Improvements

## Overview

This plan implements comprehensive improvements to the BugTracker LLM-based bug detection pipeline, addressing 15 architectural gaps and 7 information drop points. The implementation transforms the pipeline from proof-of-concept to production-ready through enhanced context (8KB→32KB), parallel execution (max 2 concurrent LLM calls on RTX 2050), complete evidence preservation, and robust error handling.

Key improvements include: Repository Index Builder with AST-based call graphs, Enhanced Context Retriever with cross-file analysis, Parallel Executor with GPU monitoring, Response Persistence Layer preventing all 7 drop points, Evidence Builder/Validator ensuring data quality, and Incremental Analysis for fast re-scans.

## Tasks

- [ ] 1. Set up database schema and migrations
  - Create Alembic migration for new tables: `llm_responses`, `pipeline_metrics`, `recovery_log`
  - Alter `candidate_issues` table to add columns: `llm_response_id`, `validation_status`, `validation_checks`, `confidence_score`, `merged_into_id`, `deduplication_metadata`
  - Create database indexes for performance: `idx_llm_responses_analysis_run`, `idx_candidate_issues_llm_response`, `idx_candidate_issues_validation_status`, `idx_candidate_issues_merged_into`, `idx_pipeline_metrics_analysis_run`, `idx_recovery_log_analysis_run`
  - Create Pydantic schemas for new data models: `LLMResponseCreate`, `LLMResponseRead`, `EnhancedEvidence`, `CrossFileReference`, `ValidationChecks`, `DeduplicationMetadata`, `CandidateIssueEnhanced`, `PipelineMetrics`
  - _Requirements: 2.6, 4.5, 5.5, 6.6, 7.5, 10.5, 14.6_

- [ ] 2. Implement Repository Index Builder (Phase 1: Core)
  - [ ] 2.1 Create AST-based Python parser
    - Implement `FunctionSignature`, `CallRelationship`, `ClassDefinition`, `TypeInfo`, `ImportInfo` dataclasses
    - Build AST visitor that extracts functions, classes, methods, type annotations, decorators, docstrings
    - Extract parameter types and return type annotations from function signatures
    - Handle nested classes and class methods
    - _Requirements: 1.1, 1.5_
  
  - [ ] 2.2 Implement call graph builder
    - Build forward call graph (caller → callees) by detecting function calls in AST
    - Build reverse call graph (callee → callers) for finding dependencies
    - Detect cross-file calls using import analysis
    - Mark `is_cross_file` flag on call relationships
    - Handle method calls on class instances
    - _Requirements: 1.1, 11.1_
  
  - [ ] 2.3 Create repository indexing orchestrator
    - Implement `RepositoryIndexBuilder.build_index()` method
    - Walk directory tree and parse all `.py` files
    - Aggregate all functions, classes, call relationships into `RepositoryIndexData`
    - Compute file content hashes (SHA256) for change detection
    - Store index metadata (build timestamp, repository path, total files)
    - Implement performance target: <30s for 10K LOC
    - _Requirements: 1.1, 1.7, 15.1_

- [ ] 3. Implement Repository Index Builder (Phase 2: Caching)
  - [ ] 3.1 Create index serialization
    - Implement `save_to_cache()` using MessagePack format
    - Create cache directory at `.bugtracker/cache/{repo_id}/`
    - Store index at `index.msgpack` with metadata in `index.meta.json`
    - Implement `load_from_cache()` with validation
    - _Requirements: 1.6_
  
  - [ ] 3.2 Implement incremental index updates
    - Implement `update_incremental()` method
    - Compare file hashes to detect changed files
    - Re-parse only changed files and update index
    - Rebuild call graph edges for affected functions
    - Preserve unchanged index entries
    - _Requirements: 15.1, 15.2, 15.3_
  
  - [ ]* 3.3 Write unit tests for Repository Index Builder
    - Test AST parsing for simple Python file with 3 functions
    - Test call graph construction for A→B→C call chain
    - Test incremental update: modify 1 file, verify only affected nodes updated
    - Test cache serialization round-trip: save→load→verify equality
    - Test cross-file import tracking
    - _Requirements: 1.1, 1.6, 15.1_

- [ ] 4. Checkpoint - Verify index building works
  - Ensure all tests pass, ask the user if questions arise

- [ ] 5. Implement Enhanced Context Retriever
  - [ ] 5.1 Create context package data structures
    - Implement `ContextPackage` dataclass with all fields from design
    - Implement `FunctionSummary`, `ClassSummary`, `CrossFileRef` types
    - Implement `RetrievalMetadata` to track completeness and errors
    - _Requirements: 1.2, 1.3, 1.5_
  
  - [ ] 5.2 Implement context retrieval with budget allocation
    - Initialize `EnhancedContextRetriever` with `RepositoryIndexData`
    - Implement `retrieve_context()` method with configurable budget (default 32KB)
    - Allocate budget: 40% target function, 25% callees, 15% callers, 10% types, 10% classes
    - Extract target function source code from file
    - Retrieve direct callee signatures and docstrings from index
    - Retrieve direct caller signatures from reverse call graph
    - Retrieve type definitions used by function from index
    - _Requirements: 1.2, 1.3, 1.4, 1.5_
  
  - [ ] 5.3 Implement cross-file context extraction
    - Implement `get_cross_file_context()` with depth parameter
    - Traverse call graph up to max_depth hops
    - Collect cross-file references with file paths and line numbers
    - Include relationship metadata (callee, caller, type_dependency)
    - _Requirements: 1.5, 11.1, 11.2, 11.3_
  
  - [ ] 5.4 Add error handling and completeness tracking
    - Wrap file reads in try-catch with fallback to cached signatures
    - Track context completeness percentage (retrieved_size / attempted_size)
    - Implement retry logic with exponential backoff for file system errors
    - Set "limited_context" flag if completeness < 70%
    - Log context retrieval errors without failing
    - _Requirements: 1.7, 9.1, 9.2, 9.4, 9.5_
  
  - [ ]* 5.5 Write unit tests for Enhanced Context Retriever
    - Test context budget compliance: verify total_size_chars ≤ budget
    - Test context retrieval determinism: same function → same context
    - Test graceful degradation: missing file → partial context + completeness < 100%
    - Test cross-file context depth=2 traversal
    - _Requirements: 1.2, 1.4, 1.7, 9.1_

- [ ] 6. Implement GPU Monitor and Circuit Breaker
  - [ ] 6.1 Create GPU Monitor
    - Implement `GPUMonitor` class with nvidia-smi integration
    - Implement `get_memory_usage()` parsing nvidia-smi output
    - Add fallback estimation if nvidia-smi unavailable
    - Implement `should_throttle()` checking 80% threshold
    - Implement `should_pause()` checking 90% threshold
    - Maintain 60-second memory usage history
    - _Requirements: 12.2, 12.6_
  
  - [ ] 6.2 Create Circuit Breaker
    - Implement `CircuitBreaker` with three states: closed, open, half_open
    - Implement `is_closed()` with timeout-based state transitions
    - Implement `record_success()` and `record_failure()` with threshold logic
    - Default parameters: failure_threshold=5, timeout=60s, success_threshold=2
    - _Requirements: 18.3_
  
  - [ ] 6.3 Create Retry Controller
    - Implement `RetryController` with exponential backoff
    - Implement `execute()` async wrapper with retry logic
    - Classify errors as retryable (ConnectionError, Timeout, 503, 429) vs non-retryable (400, 401, 404)
    - Apply exponential backoff: 1s, 2s, 4s with ±20% jitter
    - Default: max_attempts=3
    - _Requirements: 9.3, 10.2, 18.1_
  
  - [ ]* 6.4 Write unit tests for resource management
    - Test GPU monitor threshold detection
    - Test circuit breaker state transitions
    - Test retry controller backoff calculation
    - Test retry controller error classification
    - _Requirements: 12.2, 18.3, 10.2_

- [ ] 7. Checkpoint - Verify resource management components
  - Ensure all tests pass, ask the user if questions arise

- [ ] 8. Implement LLM Provider Pool
  - [ ] 8.1 Create LLM call metadata and response types
    - Implement `LLMCallMetadata` dataclass
    - Implement `LLMResponse` dataclass with text and metadata
    - _Requirements: 4.3, 14.2_
  
  - [ ] 8.2 Implement LLM Provider Pool with monitoring
    - Initialize with provider, max_concurrent semaphore, circuit_breaker
    - Implement `generate_with_monitoring()` async method
    - Add semaphore-based concurrency control (default max=2)
    - Add circuit breaker protection before LLM calls
    - Track GPU memory before and after inference
    - Measure latency and token counts
    - Record metadata to MetricsCollector
    - Implement timeout (default 30s per call)
    - _Requirements: 3.2, 12.1, 12.3, 14.2, 18.4_
  
  - [ ]* 8.3 Write integration test for LLM Provider Pool
    - Mock LLM provider and test concurrent request limiting
    - Test circuit breaker opens after 5 failures
    - Test timeout handling
    - _Requirements: 3.2, 18.3_

- [ ] 9. Implement Response Persistence Layer (Drop Point 1 Prevention)
  - [ ] 9.1 Create database repository for llm_responses
    - Implement `LLMResponseRepository` with CRUD methods
    - Implement `create_llm_response()` inserting into llm_responses table
    - Add foreign key to analysis_runs table
    - Store request_id, prompt, raw_response, model metadata, timing, GPU memory
    - _Requirements: 4.1, 4.2, 4.3, 4.5_
  
  - [ ] 9.2 Implement persistence layer with retry and recovery
    - Implement `ResponsePersistenceLayer` class
    - Initialize with database session and `RetryController`
    - Implement `persist_raw_response()` async method
    - Wrap database insert in transaction with retry logic (3 attempts)
    - On final failure, call `_persist_to_recovery_file()`
    - Create recovery file at `.bugtracker/recovery/{analysis_run_id}.jsonl`
    - Write JSONL format with request_id, prompt, response, error metadata
    - _Requirements: 4.1, 4.2, 10.1, 10.2, 10.3, 10.4_
  
  - [ ]* 9.3 Write integration test for response persistence
    - Test successful persistence to database
    - Test fallback to recovery file on database failure
    - Test recovery file format and parsing
    - _Requirements: 4.1, 10.3_

- [ ] 10. Implement Output Parser with Fallback (Drop Point 5 Prevention)
  - [ ] 10.1 Create parser result types
    - Implement `ParseResult` dataclass
    - _Requirements: 8.1, 8.4_
  
  - [ ] 10.2 Implement JSON parsing with markdown stripping
    - Implement `_strip_markdown()` removing ```json and ``` markers
    - Implement primary JSON parsing strategy
    - Handle single finding vs array of findings
    - Normalize field names (case-insensitive)
    - Provide default values for optional fields
    - _Requirements: 20.1, 20.2, 20.4, 20.5_
  
  - [ ] 10.3 Implement regex fallback parser
    - Implement `_extract_with_regex()` method
    - Define regex patterns for severity, title, description, line numbers
    - Extract findings from free-text responses
    - Mark parse_method="regex_fallback"
    - _Requirements: 8.2, 20.3_
  
  - [ ] 10.4 Implement parser orchestration
    - Implement `parse()` method with strategy pattern
    - Try JSON parsing first
    - Fall back to regex extraction on JSON failure
    - Return failed ParseResult preserving raw response if all strategies fail
    - Never throw exceptions - always return ParseResult
    - Update llm_responses table with parse_status and parse_method
    - _Requirements: 8.1, 8.3, 8.4, 8.5, 20.6_
  
  - [ ]* 10.5 Write unit tests for Output Parser
    - Test valid JSON parsing
    - Test markdown stripping
    - Test regex fallback on malformed JSON
    - Test raw response preservation on complete failure
    - _Requirements: 8.1, 8.2, 20.1, 20.3_

- [ ] 11. Implement Evidence Builder (Drop Point 2 Prevention)
  - [ ] 11.1 Create evidence data structures
    - Implement `Evidence` dataclass with all fields from design
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  
  - [ ] 11.2 Implement source code snippet extraction
    - Implement `_extract_snippet()` method
    - Read file and extract lines with ±5 context
    - Handle boundary cases (file start, file end)
    - Return snippet with start/end line numbers
    - _Requirements: 5.1_
  
  - [ ] 11.3 Implement cross-file reference extraction
    - Implement `_extract_cross_file_refs()` method
    - Extract references from context package
    - Include file paths, function names, relationships
    - _Requirements: 5.4_
  
  - [ ] 11.4 Implement evidence quality assessment
    - Implement `_assess_quality()` method
    - Quality="complete" if snippet retrieved AND context_completeness > 90%
    - Quality="partial" if context_completeness 70-90%
    - Quality="incomplete" if context_completeness < 70% OR snippet unavailable
    - _Requirements: 5.5, 5.6_
  
  - [ ] 11.5 Implement evidence builder orchestration
    - Implement `build_evidence()` method
    - Extract code snippet, LLM explanation, confidence score
    - Include function signature and type annotations from context
    - Add cross-file references and related functions
    - Calculate evidence quality
    - Handle errors gracefully: return incomplete evidence with error log
    - Never fail - always return Evidence object
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  
  - [ ]* 11.6 Write unit tests for Evidence Builder
    - Test snippet extraction with boundary cases
    - Test evidence quality assessment for different completeness levels
    - Test graceful error handling for missing files
    - _Requirements: 5.1, 5.5_

- [ ] 12. Checkpoint - Verify parsing and evidence pipeline
  - Ensure all tests pass, ask the user if questions arise

- [ ] 13. Implement Evidence Validator (Requirement 16)
  - [ ] 13.1 Create validation result types
    - Implement `ValidationResult` dataclass
    - _Requirements: 16.1, 16.2, 16.3, 16.4_
  
  - [ ] 13.2 Implement validation checks
    - Implement `_validate_line_numbers()` checking line range within file bounds
    - Implement `_validate_function_exists()` querying repository index
    - Implement `_validate_snippet_matches()` comparing snippet with actual source
    - Implement `_validate_pattern_exists()` for deterministic bug types using AST
    - Define DETERMINISTIC_BUG_TYPES list (sql_injection, hardcoded_credentials, etc.)
    - _Requirements: 16.1, 16.2, 16.3, 16.5_
  
  - [ ] 13.3 Implement validation orchestration
    - Implement `validate_finding()` method
    - Run all applicable validation checks
    - Collect failure reasons
    - Calculate confidence adjustment: -0.3 per failed check
    - Mark finding as invalid if critical checks fail
    - _Requirements: 16.4, 16.6_
  
  - [ ]* 13.4 Write unit tests for Evidence Validator
    - Test line number validation
    - Test function existence check
    - Test confidence penalty calculation
    - _Requirements: 16.1, 16.2, 16.4_

- [ ] 14. Implement Deduplication Engine (Drop Point 3 Prevention)
  - [ ] 14.1 Create deduplication metadata types
    - Implement `DeduplicationMetadata` dataclass
    - _Requirements: 6.2, 6.5_
  
  - [ ] 14.2 Implement similarity calculation
    - Implement `_calculate_similarity()` for two findings
    - Compare file_path, bug_type, line_range (±5 lines)
    - Calculate semantic similarity of titles and descriptions
    - Return score 0.0-1.0
    - Verify similarity symmetry property
    - _Requirements: 19.1, 19.2, 19.5_
  
  - [ ] 14.3 Implement grouping and merging logic
    - Implement `_group_candidates()` grouping by (file, bug_type, line_range)
    - Implement `_merge_group()` creating merged finding
    - Merge only if similarity > 0.85
    - Select max severity and max confidence
    - Preserve all original finding IDs in metadata
    - Create composite evidence structure
    - Mark original findings with merged_into_id
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 19.1, 19.3, 19.4_
  
  - [ ] 14.4 Implement deduplication orchestration
    - Implement `deduplicate_findings()` method
    - Group all findings from analysis run
    - Calculate pairwise similarities within groups
    - Merge high-similarity groups
    - Return deduplicated list
    - Store deduplication metadata in database
    - _Requirements: 6.1, 6.2, 6.6_
  
  - [ ]* 14.5 Write unit tests for Deduplication Engine
    - Test similarity calculation symmetry
    - Test merging preserves max severity and confidence
    - Test evidence preservation from all merged findings
    - _Requirements: 19.1, 19.5, 6.3, 6.4_

- [ ] 15. Implement Parallel Executor (Phase 1: Core)
  - [ ] 15.1 Create worker configuration and task types
    - Implement `WorkerConfig` dataclass
    - Implement `AnalysisTask` dataclass
    - _Requirements: 3.1, 3.2_
  
  - [ ] 15.2 Implement task queue and worker pool
    - Initialize `ParallelExecutor` with config, index, LLM pool, GPU monitor
    - Create async task queue with configured size
    - Implement `execute_analysis()` method distributing functions to workers
    - Create worker coroutines (default 2 concurrent)
    - _Requirements: 3.1, 3.2_
  
  - [ ] 15.3 Implement worker coroutine
    - Implement `_worker()` async method
    - Pull tasks from queue
    - Check GPU memory before processing
    - Build context using EnhancedContextRetriever
    - Call LLM via LLMProviderPool
    - Persist raw response via ResponsePersistenceLayer
    - Parse response via OutputParserWithFallback
    - Build evidence via EvidenceBuilder
    - Validate evidence via EvidenceValidator
    - Buffer results for batch write
    - Handle errors per-function without stopping pipeline
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 18.1, 18.2_
  
  - [ ] 15.4 Implement batch database writes
    - Collect results in buffer (size=10)
    - Flush to database every 10 results or 5 seconds
    - Wrap in transaction with rollback on failure
    - _Requirements: 3.6, 10.1_
  
  - [ ]* 15.5 Write integration test for Parallel Executor
    - Test parallel processing with mocked LLM (5 functions)
    - Test error isolation (1 function fails, others succeed)
    - Test batch database writes
    - _Requirements: 3.1, 18.1, 18.2_

- [ ] 16. Implement Parallel Executor (Phase 2: Resource Management)
  - [ ] 16.1 Implement dynamic concurrency adjustment
    - Implement `_adjust_concurrency()` method
    - Check GPU memory via GPUMonitor
    - Reduce concurrency to 1 if should_throttle()=True
    - Pause new tasks if should_pause()=True
    - Increase concurrency back to configured max when memory drops
    - _Requirements: 3.4, 12.2_
  
  - [ ] 16.2 Integrate GPU monitoring loop
    - Start GPU monitor background task when executor starts
    - Call `_adjust_concurrency()` every 2 seconds
    - Log memory usage and concurrency adjustments
    - _Requirements: 3.4, 12.2, 12.6_
  
  - [ ] 16.3 Add performance metrics collection
    - Track per-stage timing (context building, LLM inference, parsing, validation)
    - Track success/failure counts
    - Track GPU memory usage (peak, average)
    - Create `PipelineMetrics` record at end of analysis
    - Write to pipeline_metrics table
    - _Requirements: 14.1, 14.2, 14.5_
  
  - [ ]* 16.4 Write integration test for GPU throttling
    - Mock GPU monitor reporting high memory
    - Verify concurrency reduced to 1
    - Mock GPU monitor reporting normal memory
    - Verify concurrency restored to 2
    - _Requirements: 3.4, 12.2_

- [ ] 17. Checkpoint - Verify parallel execution pipeline
  - Ensure all tests pass, ask the user if questions arise

- [ ] 18. Implement Incremental Analysis
  - [ ] 18.1 Extend analysis_runs table
    - Add `file_hashes` JSONB column to analysis_runs table via migration
    - Store file_path → content_hash mapping
    - _Requirements: 15.4_
  
  - [ ] 18.2 Implement change detection
    - Implement `detect_changed_files()` method
    - Load previous analysis run's file_hashes
    - Compare with current repository index file_hashes
    - Identify added, modified, deleted files
    - _Requirements: 15.1, 15.2_
  
  - [ ] 18.3 Implement dependency tracking
    - Implement `find_affected_functions()` method
    - For each changed file, extract modified functions
    - Traverse call graph to find functions that call modified functions
    - Mark affected functions for re-analysis
    - _Requirements: 15.3_
  
  - [ ] 18.4 Implement incremental execution mode
    - Add `use_incremental` parameter to analysis pipeline
    - Skip unchanged functions (copy findings from previous run)
    - Re-analyze changed functions and their dependents
    - Update analysis_run with new file_hashes
    - _Requirements: 15.2, 15.5_
  
  - [ ]* 18.5 Write integration test for incremental analysis
    - Run full analysis on test repo
    - Modify 1 file
    - Run incremental analysis
    - Verify only modified function re-analyzed
    - Verify findings from unchanged functions preserved
    - _Requirements: 15.1, 15.2, 15.5_

- [ ] 19. Implement Prompt Engineering and Configuration
  - [ ] 19.1 Create versioned prompt templates
    - Create `prompts/` directory with versioned JSON files
    - Implement `PromptTemplate` dataclass with version, schema, examples
    - Create base prompt template v1.0 with strict JSON output schema
    - Include few-shot examples of correct bug reports
    - Add instruction: "Return ONLY valid JSON without markdown code blocks"
    - _Requirements: 13.1, 13.2, 13.3_
  
  - [ ] 19.2 Implement Prompt Builder
    - Implement `PromptBuilder` class
    - Implement `build_prompt()` method combining template + context package
    - Insert function source, callees, callers into prompt
    - Track prompt version in metadata
    - _Requirements: 13.1, 13.6_
  
  - [ ] 19.3 Create configuration system
    - Create `pipeline_config.yaml` for tunable parameters
    - Support: context_size, max_concurrent_llm_calls, timeout, model_name, gpu_memory_threshold
    - Load from environment variables and config file
    - Implement `PipelineConfig` Pydantic model with validation
    - Support per-repository overrides via `.bugtracker/repo_config.yaml`
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5_
  
  - [ ]* 19.4 Write unit test for configuration loading
    - Test config loading from file
    - Test environment variable overrides
    - Test validation and default values
    - _Requirements: 17.1, 17.4, 17.5_

- [ ] 20. Implement Frontend API Enhancements (Drop Point 4 and 7 Prevention)
  - [ ] 20.1 Update candidate issues API endpoint
    - Modify GET `/api/v1/candidate_issues/{id}` to return enhanced fields
    - Include `llm_response_id`, `validation_status`, `validation_checks`, `confidence_score`, `deduplication_metadata`
    - Return full nested evidence structure without truncation
    - Add API versioning header `X-API-Version: v1`
    - _Requirements: 7.1, 7.2, 7.4_
  
  - [ ] 20.2 Add evidence detail endpoint
    - Create GET `/api/v1/candidate_issues/{id}/evidence` endpoint
    - Return full evidence when it exceeds inline size limit
    - Include source code snippet, cross-file references, related functions
    - _Requirements: 7.5_
  
  - [ ] 20.3 Add merged findings expansion endpoint
    - Create GET `/api/v1/candidate_issues/{id}/duplicates` endpoint
    - Return all original findings that were merged into this finding
    - Include individual evidence from each duplicate
    - _Requirements: 6.6_
  
  - [ ] 20.4 Add pagination support
    - Update GET `/api/v1/candidate_issues` with pagination parameters
    - Support query params: page, page_size, severity filter, validation_status filter
    - Preserve full evidence in paginated responses
    - _Requirements: 7.2_
  
  - [ ]* 20.5 Write integration test for API endpoints
    - Test GET finding with enhanced evidence
    - Test evidence detail endpoint
    - Test merged findings expansion
    - Test pagination preserves evidence
    - _Requirements: 7.1, 7.2, 7.5, 6.6_

- [ ] 21. Checkpoint - Verify API enhancements
  - Ensure all tests pass, ask the user if questions arise

- [ ] 22. Implement Recovery Utilities
  - [ ] 22.1 Create recovery file parser
    - Implement `RecoveryFileParser` class
    - Parse JSONL recovery files
    - Validate recovery file schema version
    - Extract LLM responses with metadata
    - _Requirements: 10.4_
  
  - [ ] 22.2 Create recovery import utility
    - Implement `RecoveryImporter` class
    - Import findings from recovery files into database
    - Create llm_responses records
    - Parse responses and create candidate_issues records
    - Update recovery_log table marking recovered=True
    - _Requirements: 10.4_
  
  - [ ] 22.3 Create CLI command for recovery
    - Add `python -m app.cli recover --analysis-run-id <id>` command
    - Find recovery files for analysis run
    - Import findings via RecoveryImporter
    - Report success/failure counts
    - _Requirements: 10.4_
  
  - [ ]* 22.4 Write integration test for recovery flow
    - Create recovery file
    - Run recovery import
    - Verify findings restored to database
    - _Requirements: 10.4_

- [ ] 23. Implement Metrics and Monitoring
  - [ ] 23.1 Create Prometheus metrics endpoint
    - Add `/metrics` endpoint with Prometheus format
    - Expose pipeline stage timings
    - Expose throughput metrics (functions/minute)
    - Expose GPU memory metrics
    - Expose error rates (parsing errors, validation failures, LLM failures)
    - _Requirements: 14.3_
  
  - [ ] 23.2 Add slow function logging
    - Log functions with LLM inference time > 30s
    - Include function name, file path, inference time, context size
    - Write to dedicated log file `slow_functions.log`
    - _Requirements: 14.4_
  
  - [ ] 23.3 Add pipeline metrics summary
    - At end of analysis run, calculate aggregate metrics
    - Write PipelineMetrics record to database
    - Log summary to console: total time, functions analyzed, throughput, error counts
    - _Requirements: 14.1, 14.2, 14.5, 14.6_

- [ ] 24. Integration Testing and End-to-End Validation
  - [ ]* 24.1 Write end-to-end pipeline test
    - Create test repository with 5 Python files
    - Run full analysis with mocked LLM responses
    - Verify llm_responses table has 5 entries
    - Verify candidate_issues table has findings with evidence
    - Verify pipeline_metrics recorded
    - Verify no recovery files created
    - _Requirements: All_Requirements_

  - [ ]* 24.2 Write error recovery integration test
    - Inject database failure during analysis
    - Verify recovery file created
    - Run recovery import
    - Verify findings restored
    - _Requirements: 10.1, 10.2, 10.3, 10.4_
  
  - [ ]* 24.3 Write parsing fallback integration test
    - Mock LLM returning malformed JSON
    - Verify regex fallback used
    - Verify parse_method="regex_fallback" in database
    - Verify finding still created
    - _Requirements: 8.1, 8.2, 8.3, 20.3_
  
  - [ ]* 24.4 Write incremental analysis integration test
    - Run full analysis
    - Modify 1 file
    - Run incremental analysis
    - Verify only 1 function re-analyzed
    - Verify incremental time < 20% of full time
    - _Requirements: 15.1, 15.2, 15.5, 15.6_

- [ ] 25. Performance Testing on Target Hardware
  - [ ]* 25.1 Run throughput benchmark on RTX 2050
    - Use test repository with 50 functions, 1000 LOC
    - Use real Ollama instance with qwen2.5-coder:3b
    - Set max_concurrent_llm_calls=2
    - Measure total analysis time, functions/minute, peak GPU memory
    - Verify functions/minute > 10, peak GPU memory < 3800 MB
    - _Requirements: 3.7, 12.6_
  
  - [ ]* 25.2 Run memory profiling test
    - Enable GPU monitor during analysis
    - Sample memory every 1 second
    - Verify max memory < 3800 MB, average memory < 3000 MB
    - Plot memory over time
    - _Requirements: 12.6_
  
  - [ ]* 25.3 Run context building latency test
    - Build context for 100 functions
    - Measure time per function
    - Verify P50 < 150ms, P95 < 200ms, P99 < 300ms
    - _Requirements: 1.7_

- [ ] 26. Documentation and Deployment
  - [ ] 26.1 Write API documentation
    - Document all new API endpoints with request/response examples
    - Document enhanced evidence structure
    - Document API versioning scheme
    - _Requirements: 7.4_
  
  - [ ] 26.2 Write configuration documentation
    - Document all tunable parameters in pipeline_config.yaml
    - Document per-repository config overrides
    - Document environment variables
    - _Requirements: 17.1, 17.2, 17.3_
  
  - [ ] 26.3 Write operator guide
    - Document recovery file format and import procedure
    - Document metrics endpoint and monitoring setup
    - Document troubleshooting common errors
    - _Requirements: 10.4, 14.3_
  
  - [ ] 26.4 Create deployment checklist
    - Run database migrations
    - Create cache directories
    - Configure GPU monitoring (if available)
    - Set pipeline configuration
    - Verify Ollama provider running
    - Run smoke test analysis

- [ ] 27. Final Checkpoint - Production Readiness Validation
  - Ensure all tests pass
  - Verify all 7 drop points prevented
  - Verify performance targets met on RTX 2050 hardware
  - Verify incremental analysis <1 minute for <10% file changes
  - Ask the user if questions arise before declaring feature complete

## Notes

- Tasks marked with `*` are optional testing tasks and can be skipped for faster MVP delivery
- All test tasks are complementary to implementation - they validate correctness but are not blocking for core functionality
- Each task references specific requirements for traceability back to the requirements document
- Checkpoints ensure incremental validation and provide opportunities for user feedback
- The implementation follows a layered approach: data layer → core components → orchestration → API → testing
- Property-based tests are intentionally omitted because this feature involves infrastructure, external services, and high-cost operations unsuitable for PBT
- Integration tests use mocked LLM providers except for final performance validation on real hardware
- Database transactions ensure atomicity per Requirement 10.1
- All 7 drop points are addressed: (1) Response persistence before parsing, (2) Evidence attachment with completeness tracking, (3) Deduplication with evidence preservation, (4) Frontend API returns complete records, (5) Parser fallback strategies, (6) Context retrieval graceful degradation, (7) Database retry + recovery files

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "6.1", "8.1"] },
    { "id": 2, "tasks": ["2.2", "6.2", "8.2"] },
    { "id": 3, "tasks": ["2.3", "3.1", "6.3", "9.1"] },
    { "id": 4, "tasks": ["3.2", "5.1", "9.2", "10.1"] },
    { "id": 5, "tasks": ["5.2", "10.2"] },
    { "id": 6, "tasks": ["5.3", "10.3", "11.1"] },
    { "id": 7, "tasks": ["5.4", "10.4", "11.2", "13.1"] },
    { "id": 8, "tasks": ["11.3", "13.2", "14.1"] },
    { "id": 9, "tasks": ["11.4", "13.3", "14.2"] },
    { "id": 10, "tasks": ["11.5", "14.3"] },
    { "id": 11, "tasks": ["14.4", "15.1", "18.1"] },
    { "id": 12, "tasks": ["15.2", "18.2"] },
    { "id": 13, "tasks": ["15.3", "18.3", "19.1"] },
    { "id": 14, "tasks": ["15.4", "18.4", "19.2"] },
    { "id": 15, "tasks": ["16.1", "19.3"] },
    { "id": 16, "tasks": ["16.2", "20.1"] },
    { "id": 17, "tasks": ["16.3", "20.2", "22.1"] },
    { "id": 18, "tasks": ["20.3", "22.2"] },
    { "id": 19, "tasks": ["20.4", "22.3", "23.1"] },
    { "id": 20, "tasks": ["23.2", "26.1"] },
    { "id": 21, "tasks": ["23.3", "26.2"] },
    { "id": 22, "tasks": ["26.3"] },
    { "id": 23, "tasks": ["26.4"] },
    { "id": 24, "tasks": ["3.3", "5.5", "6.4", "8.3", "9.3", "10.5", "11.6", "13.4", "14.5", "15.5", "16.4", "18.5", "19.4", "20.5", "22.4", "24.1", "24.2", "24.3", "24.4", "25.1", "25.2", "25.3"] }
  ]
}
```
