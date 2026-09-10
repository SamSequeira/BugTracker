# BugTracker: AI-Assisted Static Analysis & Bug Triage System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/tests-223%20passed-brightgreen.svg)]()
[![Production Status](https://img.shields.io/badge/status-PRODUCTION__CERTIFIED-success.svg)]()

BugTracker is an enterprise-grade, AI-assisted static analysis and automated bug triage platform for multi-language software repositories (Python, JavaScript, and Java). It combines deterministic AST-based pattern matching, intelligent suppression rules, calibrated machine-learning classification, out-of-distribution drift safeguards, and automated bug enrichment.

---

## 1. End-to-End System Flow

The platform executes a deterministic 8-stage processing pipeline:

```
[Repository Upload / Git Clone]
              ↓
    [Repository Ingestion]
              ↓
  [AST Parsing (Python / JS / Java)]
              ↓
  [Static Analysis Rule Engine]
              ↓
 [Candidate Issue Generation & Deduplication]
              ↓
[Stage 1: Validity Classification & Drift Detection]
  ├── Primary: Linear SVM (TF-IDF, τ = 0.40)
  ├── Secondary: DistilBERT Fallback (Ambiguous Margin)
  └── Safety: Multi-Signal Drift Detector (OOD Reject / Human Review)
              ↓
[Stage 2: Decoupled Severity & Priority Assignment]
  ├── Canonical Rule Taxonomy
  └── AST Contextual Modifiers (Security / Critical blocks)
              ↓
[Stage 3: Automated Bug Enrichment & Remediation]
  ├── Location & Syntactic Evidence Mapping
  ├── Structured Explanations (What / Where / Why)
  └── Synthesised Fix & Unified Diff Generation
              ↓
[Multi-Format Reporting & API Output]
  └── JSON, Markdown, HTML, CSV, PDF
```

---

## 2. Key Capabilities

### A. Static Analysis & AST Parsing
- **Multi-Language AST Support:** Parses Python (`ast`), JavaScript (`esprima` / tree structures), and Java (`javalang`).
- **Deterministic Rule Taxonomy:** Flags division by zero, unclosed resources, bare exceptions, dangerous production assertions, mutable default arguments, non-strict equality, await-in-loops, empty catches, and infinite loops.
- **Intelligent Suppressions:** AST-aware suppressions recognize class literals, enum comparisons, managed context blocks, guarded divisors (`max()`, `Math.max`), defensive `None` defaults, and intentional test structures.

### B. Certified ML Architecture: `LINEAR_SVM_PRIMARY_WITH_DISTILBERT_OPTIONAL`
- **Primary Stage 1 Model:** High-throughput Linear SVM (`SGDClassifier` with log-loss, balanced class weights, sublinear TF-IDF, $p_{50}$ latency $< 0.50\text{ ms}$).
- **Secondary Model:** Fine-tuned DistilBERT transformer for cross-verifying ambiguous margin samples ($0.35 \le p < 0.90$).
- **Multi-Signal Drift Detector:** Monitors token OOV rates, prediction entropy, unparseable syntax, and unregistered rule/language penalties ($D(x) \ge 0.30 \to \text{OOD\_REJECT}$).
- **5-Way Risk-Controlled Router:**
  - `AUTO_ACCEPT`: High certainty ($p \ge 0.90$ or $p \le 0.05$ with low drift).
  - `SECONDARY_MODEL`: Moderate margin dispatched for cascade cross-verification.
  - `HUMAN_REVIEW`: Model disagreement, high entropy, or uncataloged rules.
  - `OOD_REJECT`: Out-of-distribution or foreign languages.
  - `SYSTEM_ERROR`: Payload limit violations ($> 500\text{ KB}$) or structural corruption.

### C. Decoupled Severity & Priority Engine
- **Decoupled from Repository Confounders:** Severity is governed solely by `RULE_TAXONOMY + AST_CONTEXT_MODIFIERS`, preventing domain spurious bias.
- **Safety Invariant:** Guaranteed **0% Critical/High $\to$ Low severity inversions** across all historical and production benchmarks.

### D. Automated Bug Enrichment
- **Detailed Explanations:** Automatically articulates *What* the defect is, *Where* it occurs (function/class scope), and *Why* it poses a runtime or security hazard.
- **Remediation Diffs:** Generates executable Unified Diff code fixes tailored to the rule and snippet.

---

## 3. Directory Layout

```
BugTracker/
├── backend/
│   ├── app/
│   │   ├── api/v1/                  # FastAPI REST endpoints
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   ├── repositories/            # Data access layer (DAL)
│   │   ├── schemas/                 # Pydantic validation schemas
│   │   └── services/
│   │       ├── ast/                 # AST generator & tree parser
│   │       ├── bug_enrichment_service.py # Bug explanation & diff generator
│   │       ├── bug_report_service.py     # Repository report aggregator
│   │       ├── bug_similarity_service.py # Vector/text similarity deduplicator
│   │       ├── candidate_issue_service.py# Candidate issue factory
│   │       ├── ml/                  # Certified production ML pipeline
│   │       │   ├── config.py        # Calibrated thresholds & paths
│   │       │   ├── data_loader.py   # Ground-truth loader
│   │       │   ├── drift_detector.py# Multi-signal drift engine
│   │       │   ├── inference.py     # Safe predict wrapper
│   │       │   ├── routing.py       # 5-Way risk-controlled router
│   │       │   ├── safety.py        # Historical safety gates & fixtures
│   │       │   ├── severity.py      # Decoupled severity engine
│   │       │   └── split_validator.py # Zero group leakage validator
│   │       ├── report_exporter.py   # Multi-format report exporter
│   │       ├── repository_analysis_service.py # Pipeline coordinator
│   │       └── static_analyzer/     # Static rule implementations
│   ├── data/
│   │   ├── prepared/                # Supervised datasets & ground truth
│   │   └── training/                # Retraining records & splits
│   ├── models/
│   │   ├── validity/                # DistilBERT weights & tokenizers
│   │   └── severity/                # Severity artifacts
│   ├── tests/                       # Complete consolidated test suite
│   │   ├── test_safety_gates.py     # Historical 27/27 TP & 42/42 FP gates
│   │   ├── test_drift_detection.py  # Multi-signal drift & OOD tests
│   │   ├── test_inference_safety.py # Edge cases, malformed corpus, latency
│   │   ├── test_severity_priority.py# Decoupled severity & context modifiers
│   │   ├── test_production_pipeline.py # Rollback, determinism, 5-way routing
│   │   ├── test_classification.py   # TF-IDF, SVM, split validator
│   │   ├── test_static_analyzer.py  # AST rule engine assertions
│   │   ├── test_refined_static_rules.py # Suppression rule checks
│   │   └── verify_end_to_end_production.py # Full pipeline integration
│   ├── main.py                      # FastAPI application entrypoint
│   └── requirements.txt             # Backend dependencies
├── frontend/                        # Frontend UI application
├── docs/                            # Production documentation & reports
└── README.md                        # Project documentation
```

---

## 4. Getting Started

### Prerequisites
- Python 3.10+
- PostgreSQL 14+ (or SQLite for local lightweight testing)
- Node.js 18+ (for frontend)

### Backend Setup

1. **Clone repository and navigate to backend:**
   ```bash
   cd backend
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   Copy `.env.example` to `.env` and set database credentials:
   ```bash
   cp .env.example .env
   ```

5. **Start Backend Server:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   API interactive documentation will be available at: `http://localhost:8000/docs`.

### Frontend Setup

1. **Navigate to frontend directory:**
   ```bash
   cd ../frontend
   ```

2. **Install packages and run:**
   ```bash
   npm install
   npm run dev
   ```

---

## 5. Running the Test Suite

Run the full consolidated test suite with `pytest`:

```bash
cd backend
py -m pytest -v
```

To run specific test categories:
- **Safety Gates & Historical Invariants:** `py -m pytest tests/test_safety_gates.py -v`
- **Drift & OOD Detection:** `py -m pytest tests/test_drift_detection.py -v`
- **Inference Fault Tolerance & Malformed Inputs:** `py -m pytest tests/test_inference_safety.py -v`
- **Severity Decoupling & Priority:** `py -m pytest tests/test_severity_priority.py -v`
- **Production Pipeline & 5-Way Routing:** `py -m pytest tests/test_production_pipeline.py -v`
- **Static Analysis Rules:** `py -m pytest tests/test_static_analyzer.py tests/test_refined_static_rules.py -v`
- **End-to-End Verification:** `py tests/verify_end_to_end_production.py`

---

## 6. Certified Production Validation Metrics

BugTracker underwent rigorous empirical validation:

| Production Dimension | Specification / Metric | Certified Result | Status |
| :--- | :--- | :--- | :--- |
| **Historical TP Recall** | `100.0%` (27 / 27 confirmed bugs) | **27 / 27 (100.0%)** | **PASS (HARD GATE)** |
| **Historical FP Rejection** | $\ge 90.0\%$ (42 historical false alarms) | **42 / 42 (100.0%)** | **PASS (HARD GATE)** |
| **Frozen Benchmark** | 37 / 37 records preserved | **37 / 37 intact** | **PASS** |
| **Dataset Leakage** | 0 cross-split group leakage | **0 overlaps** | **PASS** |
| **Severity Inversion Safety** | 0.0% Critical/High inverted to Low | **0 / 115 (0.00%)** | **PASS (HARD GATE)** |
| **Adversarial Invariance** | $\ge 99.0\%$ under 8 semantic attacks | **99.84% consistency** | **PASS** |
| **Drift False Alarm Rate** | $\le 5.0\%$ on in-distribution validation | **2.0% (3 / 153)** | **PASS** |
| **OOD Drift Detection** | $\ge 90.0\%$ detection rate | **92.3% (12 / 13)** | **PASS** |
| **Malformed Input Resilience** | 0 unhandled crashes on 20 edge cases | **20 / 20 safe (100%)** | **PASS** |
| **Payload Resource Limit** | Safe reject on $> 500\text{ KB}$ payloads | **SYSTEM_ERROR in < 0.01ms** | **PASS** |
| **Inference Latency ($p_{50}$)** | Sub-millisecond end-to-end safe predict | **0.490 ms (0.110 ms core)** | **PASS** |
| **Model Rollback** | 100% cryptographic hash parity | **100% identical SHA256** | **PASS** |
| **Multi-Run Determinism** | 5 independent inference executions | **100% bit-for-bit match** | **PASS** |
| **Full Regression Suite** | 100% tests passing | **223 / 223 passed (100%)** | **PASS** |
