# BugTracker AI — Code Analysis & Bug Tracking System

BugTracker AI is a full-stack platform that analyses software repositories, identifies potential coding and logic issues, and helps developers review and prioritise findings. It combines a deterministic AST-based static analysis engine with an optional LLM-based semantic reviewer, alongside repository architecture analysis, issue management, and report generation.

The project supports repository scanning through a GitHub URL or an uploaded ZIP archive. It is designed to make analysis results easier to inspect, understand, and act on.

---

## Key Features

### Repository Scanning
- Clone a GitHub repository or upload a ZIP archive for analysis.
- Detect and analyse supported source files in Python, JavaScript, and Java.
- Store repository and analysis information for use across the application.
- Upload repository archives to AWS S3 when S3 storage is configured and enabled.

### AST-Based Static Analysis
- Parse source code using language-specific syntax-tree tooling.
- Apply deterministic rules to identify supported coding issues, such as division-by-zero risks, mutable default arguments, unsafe exception handling, and other recognised patterns.
- Keep rule-based findings separate from LLM-based semantic findings.

### LLM-Based Semantic Review
- Uses a local Ollama model by default: `qwen2.5-coder:3b-instruct-q4_K_M`.
- Examines extracted Python functions and relevant code context for potential logical and business-logic bugs.
- Validates findings against source-code evidence before they are accepted into the results.
- The LLM review is an additional analysis path; it does not replace the deterministic rule-based engine. Model output may be incomplete or incorrect and should be reviewed by a developer.

### Codebase Architecture Analysis
- Summarises the detected technology stack and repository structure.
- Groups source files into architectural components.
- Presents potential risk areas and repository-level analysis information.

### Bug Tracking & Inspection
- Search and filter findings.
- Review issue descriptions, severity, priority, file locations, line references, and code snippets where available.
- Inspect issue details and suggested remediation information.
- Track issue status, including resolution workflows supported by the application.

### Ground-Truth Review
- Includes a dedicated review interface for manually labelling candidate issues.
- Supports recording review decisions and rationale for dataset evaluation.
- This review interface is intended for validation work and is separate from ordinary issue triage.

### Bug Report Export
Export supported reports in the following formats:
- PDF
- CSV
- JSON
- Markdown (`.md`)
- HTML

### Authentication & Data Storage
- User registration and login using JWT-based authentication.
- PostgreSQL persistence through SQLAlchemy's asynchronous database layer.
- Alembic database migrations.
- Optional AWS S3 storage for repository archives.

---

## Tech Stack

| Area | Technologies |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS, Lucide React |
| Backend | Python, FastAPI, REST APIs |
| Static Analysis | AST parsing, Tree-sitter, language-specific rules |
| Semantic Review | Ollama, Qwen2.5-Coder 3B (quantised) |
| Other LLM Providers | Ollama, Gemini, Groq, OpenAI (provider-dependent configuration) |
| Database | PostgreSQL, SQLAlchemy, asyncpg |
| Migrations | Alembic |
| Authentication | JWT, PyJWT, password hashing with pwdlib/Argon2 |
| Repository Storage | Local repository workspace, optional AWS S3 via boto3 |
| Testing | pytest |

> The default semantic-review provider is configured through environment variables. Optional cloud providers require their own API credentials and may incur usage costs.

---

## Architecture Overview

```text
GitHub URL / ZIP Upload
          |
          v
Repository Ingestion & Storage
          |
          v
Source File Discovery
          |
          v
AST / Tree-sitter Parsing
          |
          v
Deterministic Static Analysis -----------+
          |                                |
          v                                v
Candidate Issues                 LLM Semantic Review
          |                       (Python functions)
          +---------------+----------------+
                          |
                          v
               Findings & Analysis Data
                          |
          +---------------+----------------+
          |               |                |
          v               v                v
    Bug Tracking    Architecture       Report Export
    & Inspection      Analysis       PDF / CSV / JSON /
                                      Markdown / HTML
```

The LLM review is intended to complement the rule engine by looking for potential logic issues that may not match a predefined rule. It is not a guarantee that every bug will be found, and findings should be validated before making code changes.

---

## Repository Structure

```text
BugTracker-main/
├── backend/
│   ├── app/
│   │   ├── api/v1/                 # Authentication, repository, and issue APIs
│   │   ├── core/                   # Configuration and security utilities
│   │   ├── models/                 # SQLAlchemy database models
│   │   ├── repositories/           # Database access layer
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   └── services/
│   │       ├── llm_logic_reviewer/ # LLM-based semantic review pipeline
│   │       ├── ast_generator.py    # Source parsing / AST generation
│   │       ├── architecture_detector.py
│   │       ├── repository_analysis_service.py
│   │       ├── report_exporter.py
│   │       └── ...                 # Analysis, storage, and enrichment services
│   ├── alembic/                    # Database migrations
│   ├── tests/                      # Backend tests
│   ├── repositories/               # Local cloned/extracted repositories at runtime
│   ├── .env.example                # Environment variable template
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/             # Authentication, layout, tabs, and modals
│   │   ├── pages/                  # Ground-truth review page
│   │   └── ...
│   ├── package.json
│   └── vite.config.js
└── README.md
```

---

## Getting Started

### Prerequisites

Install the following before running the application:

- Python 3.12 recommended for the supplied backend environment
- Node.js and npm
- PostgreSQL
- Git
- Ollama, if using the default local LLM reviewer
- An AWS account and an existing S3 bucket only if S3 storage is enabled

### 1. Clone the Repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd BugTracker-main
```

Replace `<YOUR_GITHUB_REPOSITORY_URL>` with the repository URL. If you already downloaded the project ZIP, extract it and open a terminal in the extracted `BugTracker-main` directory.

### 2. Configure the Backend Environment

```bash
cd backend
python -m venv .venv
```

Activate the environment on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

Install backend dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create `backend/.env` using `backend/.env.example` as a reference. **Do not copy or commit real credentials.** At minimum, configure a database URL and a strong JWT secret.

Example local configuration:

```env
DATABASE_URL=postgresql+asyncpg://YOUR_DB_USER:YOUR_DB_PASSWORD@localhost:5432/bugtracker
JWT_SECRET_KEY=replace-with-a-long-random-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Optional S3 configuration. Keep disabled for local-only storage.
S3_ENABLED=false
AWS_REGION=ap-south-1
S3_BUCKET_NAME=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_PREFIX=repositories
S3_PRESIGNED_EXPIRY=3600

# Default local semantic-review provider
LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:3b-instruct-q4_K_M
OLLAMA_TIMEOUT_SECONDS=120
```

Create the PostgreSQL database before starting the backend. For example, in `psql`:

```sql
CREATE DATABASE bugtracker;
```

If you enable S3, create or select an S3 bucket and configure credentials securely through environment variables or your AWS credential profile. The bucket must exist and the configured AWS identity must have the permissions required by the application.

### 3. Prepare the Local LLM (Ollama)

Install Ollama from the official website, then pull the configured model:

```bash
ollama pull qwen2.5-coder:3b-instruct-q4_K_M
```

Make sure the Ollama service is running and the model is available:

```bash
ollama list
```

The backend's default provider is Ollama. If you select Gemini, Groq, or OpenAI instead, configure the corresponding API key and model settings in `backend/.env`. LLM-based review may be unavailable if the selected provider cannot be reached; the deterministic static-analysis workflow is designed to continue independently of semantic-review failures.

### 4. Apply Database Migrations

From the `backend` directory, with the virtual environment active and `.env` configured:

```bash
alembic upgrade head
```

### 5. Start the Backend

From the `backend` directory:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend root:

```text
http://localhost:8000
```

Interactive API documentation:

```text
http://localhost:8000/docs
```

### 6. Start the Frontend

Open a second terminal from the project root:

```bash
cd frontend
npm install
npm run dev
```

Vite normally serves the frontend at:

```text
http://localhost:5173
```

If you change the backend address or frontend origin, update the relevant frontend API configuration and `CORS_ORIGINS` in `backend/.env` to match your local setup.

---

## Running Tests

From the `backend` directory, activate the virtual environment and run:

```bash
python -m pytest -v
```

To run a specific test file:

```bash
python -m pytest tests/test_report_exporter.py -v
```

The test suite and available test files may change as the project evolves. Run the tests in your current checkout before publishing a test count or benchmark claim.

---

## Application Screenshots
### 1. Login Page
<img width="100%" alt="Home" src="https://github.com/user-attachments/assets/24bff2ad-9745-4779-abd4-1e064ce37ea3" />

### 2. Codebase Scanner Results
<img width="100%" alt="Tab1afterscan" src="https://github.com/user-attachments/assets/b57c23eb-7a16-4734-bc24-4c1782f7f9ae" />

### 3. AI Codebase Architecture & Topology
<img width="100%" alt="Tab2" src="https://github.com/user-attachments/assets/d3566ca9-1547-4da3-a6e5-29f4f44e8c96" />

### 4. Bug Management & Issue Triage
<img width="100%" alt="Tab3long" src="https://github.com/user-attachments/assets/1b940dbf-9e0b-4f68-91d1-6dd23bf3bcf3" />

### 5. Bug Reports & Audit
<img width="100%" alt="Tab4" src="https://github.com/user-attachments/assets/0ca1f74a-48b8-457d-9821-80866f42ceae" />

### 6. Ground-Truth Review
<img width="100%" alt="tab5" src="https://github.com/user-attachments/assets/3129288e-d507-4bf4-8174-44b8a22e6549" />

### 7. Application Settings
<img width="100%" alt="settings" src="https://github.com/user-attachments/assets/53203c61-471f-4e35-bb96-3d55d4be7e6e" />





---

## Security Notes

- Never commit `.env` files, passwords, JWT secrets, API keys, or AWS credentials.
- Keep `backend/.env.example` limited to placeholders and safe defaults.
- If a credential has been committed, removing it from the latest file is not enough: revoke or rotate it and review the Git history.
- Use a strong, unique `JWT_SECRET_KEY` outside local development.
- Only scan repositories you are authorised to access.
- Review AI-generated findings and suggested fixes before applying them.

---

## Known Considerations

- LLM-based semantic review is probabilistic and may miss issues or produce incorrect findings.
- The current semantic reviewer focuses on Python functions; AST-based rules also support Python, JavaScript, and Java.
- LLM review speed depends on the selected model and available hardware. A local model may run more slowly on CPU or when GPU memory is limited.
- Repository scanning time depends on repository size, file count, and configured scan limits.
- S3 storage is optional and requires valid AWS configuration.

---

## Acknowledgements

Built as an internship project at Persistent Systems, with contributions from the project team and guidance from our mentors.

---
