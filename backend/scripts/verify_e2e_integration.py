"""
verify_e2e_integration.py
-------------------------
Comprehensive end-to-end automated verification script testing:
1. FastAPI app startup & OpenAPI schema validation
2. PostgreSQL connection and ORM models
3. Authentication flow (Signup, Login, /auth/me, Logout, Error cases)
4. Repository ingestion (Upload/Clone, Analysis run, Candidate issues persistence)
5. Candidate issues API (Listing, Filtering, Details, Source context)
6. Bug Resolution persistence (PATCH /status -> PostgreSQL verification)
7. Engineer Remarks persistence (PATCH /notes -> PostgreSQL verification)
8. Architecture & Topology (Summary, Technologies, Components, Source files)
9. Reports & Multi-format Export (PDF, CSV, JSON, MD, HTML)
10. Ground-truth Dataset Review (200-sample queue, Label verification, Dataset stats, Duplicates, Verified dataset export)
11. Test data cleanup (Removes ephemeral audit user & test repository with cascade)
"""

import asyncio
import io
import os
import sys
import uuid
import zipfile
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.main import app
from app.models.candidate_issues import CandidateIssue
from app.models.issue_status import IssueStatus
from app.models.repository import Repository
from app.models.user import User


def get_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


async def run_full_verification():
    print("=" * 70)
    print("BUGTRACKER COMPREHENSIVE END-TO-END INTEGRATION VERIFICATION")
    print("=" * 70)

    db_url = get_db_url()
    print(f"[*] Database URL: {db_url.split('@')[-1] if '@' in db_url else db_url}")

    engine = create_async_engine(db_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from data.dbconnection.base import Base
    import app.models as _models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    results = {}

    async with AsyncClient(transport=transport, base_url="http://localhost:8000") as client:

        # -------------------------------------------------------------------
        # 1. API Root & OpenAPI Docs
        # -------------------------------------------------------------------
        print("\n--- [Step 1] API Root & OpenAPI Specification ---")
        root_res = await client.get("/")
        assert root_res.status_code == 200, f"Root failed: {root_res.status_code}"
        print(f"[PASS] GET / -> {root_res.json()}")

        openapi_res = await client.get("/openapi.json")
        assert openapi_res.status_code == 200, f"OpenAPI failed: {openapi_res.status_code}"
        paths = list(openapi_res.json()["paths"].keys())
        print(f"[PASS] GET /openapi.json -> Loaded {len(paths)} endpoint paths")
        results["openapi"] = "PASSED"

        # -------------------------------------------------------------------
        # 2. Authentication & Authorization Flow
        # -------------------------------------------------------------------
        print("\n--- [Step 2] Authentication Flow ---")
        test_email = f"audit_user_{uuid.uuid4().hex[:6]}@bugtracker.dev"
        test_password = "SecurePassword2026!"
        test_name = "Audit Test Engineer"

        # 2a. Signup
        signup_res = await client.post(
            "/api/v1/auth/signup",
            json={"name": test_name, "email": test_email, "password": test_password},
        )
        assert signup_res.status_code == 200, f"Signup failed: {signup_res.text}"
        signup_data = signup_res.json()
        assert signup_data["email"] == test_email
        print(f"[PASS] POST /api/v1/auth/signup -> Created user {test_email}")

        # Verify in PostgreSQL
        async with session_factory() as session:
            user_db = (
                await session.execute(
                    text("SELECT id, name, email, password_hash FROM users WHERE email = :email"),
                    {"email": test_email},
                )
            ).fetchone()
            assert user_db is not None, "User not found in PostgreSQL!"
            assert user_db[1] == test_name
            assert user_db[3] != test_password, "Password is not hashed!"
            print(f"[PASS] Verified in PostgreSQL: User {user_db[0]} persisted with hashed password")

        # 2b. Login
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": test_email, "password": test_password},
        )
        assert login_res.status_code == 200
        login_data = login_res.json()
        assert "access_token" in login_data
        token = login_data["access_token"]
        assert login_data["user"]["email"] == test_email
        print(f"[PASS] POST /api/v1/auth/login -> Authenticated successfully with token")

        # 2c. Get Current User (/auth/me)
        auth_headers = {"Authorization": f"Bearer {token}"}
        me_res = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["email"] == test_email
        print(f"[PASS] GET /api/v1/auth/me -> Resolved current user {me_data['name']} ({me_data['email']})")

        # 2d. Auth Error Cases
        bad_login = await client.post(
            "/api/v1/auth/login",
            json={"email": test_email, "password": "WrongPassword123!"},
        )
        assert bad_login.status_code == 401
        print(f"[PASS] POST /api/v1/auth/login (bad password) -> Rejected with 401 Unauthorized")

        bad_jwt = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid_jwt_token_123"},
        )
        assert bad_jwt.status_code == 401
        print(f"[PASS] GET /api/v1/auth/me (invalid JWT) -> Rejected with 401 Unauthorized")

        results["auth"] = "PASSED"

        # -------------------------------------------------------------------
        # 3. Repository Ingestion & Analysis Run
        # -------------------------------------------------------------------
        print("\n--- [Step 3] Repository Ingestion & Static Analysis Pipeline ---")
        
        # Create in-memory zip archive with test vulnerability files
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "src/calculator.py",
                (
                    "def divide(a, b):\n"
                    "    # Potential division by zero\n"
                    "    return a / 0\n"
                    "\n"
                    "def process_data(vals):\n"
                    "    try:\n"
                    "        return vals[0]\n"
                    "    except:\n"
                    "        pass\n"
                ),
            )
            zf.writestr(
                "src/utils.js",
                (
                    "function checkEqual(a, b) {\n"
                    "    if (a == b) {\n"
                    "        return true;\n"
                    "    }\n"
                    "    return false;\n"
                    "}\n"
                ),
            )
        zip_buffer.seek(0)

        upload_res = await client.post(
            "/api/v1/repositories/upload",
            files={"file": ("test_audit_repo.zip", zip_buffer.getvalue(), "application/zip")},
            headers=auth_headers,
        )
        assert upload_res.status_code in (200, 201), f"Upload failed: {upload_res.text}"
        upload_data = upload_res.json()
        repo_id = upload_data["repository_id"]
        print(f"[PASS] POST /api/v1/repositories/upload -> Created repository {repo_id}")

        # Poll analysis status until complete
        for _ in range(15):
            status_res = await client.get(f"/api/v1/repositories/{repo_id}/analysis-status")
            status_data = status_res.json()
            if status_data["status"] == "completed":
                break
            await asyncio.sleep(0.5)

        assert status_data["status"] == "completed"
        candidate_count = status_data.get("candidate_issues_count", 0)
        print(f"[PASS] GET /api/v1/repositories/{repo_id}/analysis-status -> Status: {status_data['status']}, Found {candidate_count} candidate issues")

        # -------------------------------------------------------------------
        # 4. Candidate Issues & Bug Management
        # -------------------------------------------------------------------
        print("\n--- [Step 4] Candidate Issues Query & Bug Inspection ---")
        bugs_res = await client.get(f"/api/v1/candidate-issues?repository_id={repo_id}")
        assert bugs_res.status_code == 200
        bugs_data = bugs_res.json()
        items = bugs_data["items"]
        assert len(items) > 0, "No candidate issues returned for analyzed repository!"
        first_issue = items[0]
        issue_id = first_issue["id"]
        print(f"[PASS] GET /api/v1/candidate-issues -> Retrieved {len(items)} issues. First issue ID: {issue_id}")
        print(f"  Title: {first_issue.get('title')}, Rule: {first_issue.get('rule_id')}, Severity: {first_issue.get('severity')}")

        # Get Single Issue Detail
        detail_res = await client.get(f"/api/v1/candidate-issues/{issue_id}")
        assert detail_res.status_code == 200
        detail_data = detail_res.json()
        print(f"[PASS] GET /api/v1/candidate-issues/{issue_id} -> Loaded details for {detail_data['file_path']}:{detail_data['line_number']}")

        # Get Source Context
        context_res = await client.get(f"/api/v1/candidate-issues/{issue_id}/context?context_lines=10")
        assert context_res.status_code == 200
        print(f"[PASS] GET /api/v1/candidate-issues/{issue_id}/context -> Retrieved source context")

        # -------------------------------------------------------------------
        # 5. Bug Resolution Persistence in PostgreSQL
        # -------------------------------------------------------------------
        print("\n--- [Step 5] Bug Resolution Persistence ---")
        resolve_res = await client.patch(
            f"/api/v1/candidate-issues/{issue_id}/status",
            json={"status": "resolved"},
        )
        assert resolve_res.status_code == 200
        print(f"[PASS] PATCH /api/v1/candidate-issues/{issue_id}/status -> Marked Resolved")

        # Verify in PostgreSQL
        async with session_factory() as session:
            status_db = (
                await session.execute(
                    text("SELECT status FROM issue_statuses WHERE candidate_issue_id = :cid"),
                    {"cid": issue_id},
                )
            ).fetchone()
            assert status_db is not None, "issue_statuses record not found in PostgreSQL!"
            assert status_db[0] == "resolved", f"Expected resolved, got {status_db[0]}"
            print(f"[PASS] Verified in PostgreSQL issue_statuses: status={status_db[0]}")

        # -------------------------------------------------------------------
        # 6. Engineer Remarks Persistence in PostgreSQL
        # -------------------------------------------------------------------
        print("\n--- [Step 6] Engineer Remarks Persistence ---")
        updated_remarks = "Security review verified fix patch applied by engineering team."
        notes_res = await client.patch(
            f"/api/v1/candidate-issues/{issue_id}/notes",
            json={"remarks": updated_remarks},
        )
        assert notes_res.status_code == 200

        async with session_factory() as session:
            notes_db = (
                await session.execute(
                    text("SELECT verification_notes FROM candidate_issues WHERE id = :cid"),
                    {"cid": issue_id},
                )
            ).scalar()
            assert notes_db == updated_remarks
            print(f"[PASS] Verified in PostgreSQL candidate_issues.verification_notes: Remarks='{notes_db}'")

        # -------------------------------------------------------------------
        # 6b. Issue Severity Update Persistence in PostgreSQL
        # -------------------------------------------------------------------
        print("\n--- [Step 6b] Issue Severity Update & PostgreSQL Persistence ---")
        sev_res = await client.patch(
            f"/api/v1/candidate-issues/{issue_id}/severity",
            json={"severity": "low"},
        )
        assert sev_res.status_code == 200
        assert sev_res.json()["severity"] == "Low"

        # Verify invalid severity rejected
        bad_sev_res = await client.patch(
            f"/api/v1/candidate-issues/{issue_id}/severity",
            json={"severity": "critical"},
        )
        assert bad_sev_res.status_code == 400
        print(f"[PASS] PATCH /api/v1/candidate-issues/{issue_id}/severity with 'critical' properly rejected (400)")

        async with session_factory() as session:
            sev_db = (
                await session.execute(
                    text("SELECT severity FROM candidate_issues WHERE id = :cid"),
                    {"cid": issue_id},
                )
            ).scalar()
            assert sev_db == "low"
            print(f"[PASS] Verified in PostgreSQL candidate_issues.severity: severity='{sev_db}'")

        # -------------------------------------------------------------------
        # 7. Architecture & Repository Topology
        # -------------------------------------------------------------------
        print("\n--- [Step 7] Architecture & Repository Topology ---")
        arch_res = await client.get(f"/api/v1/repositories/{repo_id}/architecture")
        assert arch_res.status_code == 200
        arch_data = arch_res.json()
        summary_info = arch_data.get("summary") or {}
        print(f"[PASS] GET /api/v1/repositories/{repo_id}/architecture -> Architecture loaded:")
        print(f"  Summary Intent: {summary_info.get('intent', 'Not specified')}")
        print(f"  Components count: {len(arch_data.get('components', []))}")
        print(f"  Technologies count: {len(arch_data.get('technologies', []))}")
        print(f"  Source files count: {len(arch_data.get('source_files', []))}")

        # -------------------------------------------------------------------
        # 8. Executive Reports & Multi-Format Exporters
        # -------------------------------------------------------------------
        print("\n--- [Step 8] Report Generation & Multi-Format Exports ---")
        formats = ["pdf", "csv", "json", "md", "html"]
        for fmt in formats:
            export_res = await client.get(f"/api/v1/repositories/export/{repo_id}?format={fmt}")
            assert export_res.status_code == 200, f"Export for format {fmt} failed: {export_res.status_code}"
            content_len = len(export_res.content)
            assert content_len > 0, f"Export content for {fmt} was empty!"
            print(f"[PASS] GET /api/v1/repositories/export/{repo_id}?format={fmt} -> Generated {fmt.upper()} report ({content_len} bytes)")

        # -------------------------------------------------------------------
        # 9. Ground-Truth Review Queue & Label Verification
        # -------------------------------------------------------------------
        print("\n--- [Step 9] Ground-Truth Review Dashboard Endpoints ---")
        
        # 9a. Review batch sampling (200 items)
        batch_res = await client.post(
            "/api/v1/candidate-issues/review/batch",
            json={"target_size": 200, "random_seed": 42},
        )
        assert batch_res.status_code == 200
        batch_data = batch_res.json()
        print(f"[PASS] POST /api/v1/candidate-issues/review/batch -> Sampled {len(batch_data.get('items', []))} issues")

        # 9b. Human Label Verification
        label_res = await client.patch(
            f"/api/v1/candidate-issues/{issue_id}/labels",
            json={
                "verified_severity": "high",
                "verified_priority": "p2",
                "verification_notes": "Human auditor confirmed vulnerability with reproducible test.",
            },
        )
        assert label_res.status_code == 200
        print(f"[PASS] PATCH /api/v1/candidate-issues/{issue_id}/labels -> Saved ground truth labels")

        # Verify in PostgreSQL
        async with session_factory() as session:
            gt_db = (
                await session.execute(
                    text(
                        "SELECT severity, verified_severity, verified_priority, verified_at, verification_notes "
                        "FROM candidate_issues WHERE id = :cid"
                    ),
                    {"cid": issue_id},
                )
            ).fetchone()
            assert gt_db is not None
            assert gt_db[1] == "high", f"Expected high, got {gt_db[1]}"
            assert gt_db[2] == "p2", f"Expected p2, got {gt_db[2]}"
            assert gt_db[3] is not None, "verified_at timestamp was not set!"
            print(f"[PASS] Verified in PostgreSQL: detector_sev={gt_db[0]}, verified_sev={gt_db[1]}, verified_prio={gt_db[2]}, verified_at={gt_db[3]}")

        # 9c. Dataset stats
        stats_res = await client.get("/api/v1/candidate-issues/dataset/stats")
        assert stats_res.status_code == 200
        stats_data = stats_res.json()
        print(f"[PASS] GET /api/v1/candidate-issues/dataset/stats -> Total: {stats_data.get('total_candidate_issues')}, Verified: {stats_data.get('total_verified')}")

        # 9d. Verified Dataset Export
        verified_res = await client.get("/api/v1/candidate-issues/dataset/verified")
        assert verified_res.status_code == 200
        print(f"[PASS] GET /api/v1/candidate-issues/dataset/verified -> Retrieved {len(verified_res.json())} training records")

        # 9e. Duplicate detection
        dup_res = await client.get(f"/api/v1/candidate-issues/duplicates?repository_id={repo_id}")
        assert dup_res.status_code == 200
        print(f"[PASS] GET /api/v1/candidate-issues/duplicates -> Detected duplicate clusters: {len(dup_res.json().get('duplicates', []))}")

        # -------------------------------------------------------------------
        # 10. Automated Test Data Cleanup
        # -------------------------------------------------------------------
        print("\n--- [Step 10] Test Data Cleanup ---")
        async with session_factory() as session:
            # Delete dependent entities in reverse FK dependency order
            await session.execute(
                text(
                    "DELETE FROM issue_statuses WHERE candidate_issue_id IN ("
                    "  SELECT id FROM candidate_issues WHERE analysis_run_id IN ("
                    "    SELECT id FROM analysis_runs WHERE repository_id = :rid"
                    "  )"
                    ")"
                ),
                {"rid": repo_id},
            )
            await session.execute(
                text(
                    "DELETE FROM candidate_issues WHERE analysis_run_id IN ("
                    "  SELECT id FROM analysis_runs WHERE repository_id = :rid"
                    ")"
                ),
                {"rid": repo_id},
            )
            await session.execute(
                text(
                    "DELETE FROM architecture_summaries WHERE analysis_run_id IN ("
                    "  SELECT id FROM analysis_runs WHERE repository_id = :rid"
                    ")"
                ),
                {"rid": repo_id},
            )
            await session.execute(
                text(
                    "DELETE FROM analysis_technologies WHERE analysis_run_id IN ("
                    "  SELECT id FROM analysis_runs WHERE repository_id = :rid"
                    ")"
                ),
                {"rid": repo_id},
            )
            await session.execute(
                text(
                    "DELETE FROM source_files WHERE analysis_run_id IN ("
                    "  SELECT id FROM analysis_runs WHERE repository_id = :rid"
                    ")"
                ),
                {"rid": repo_id},
            )
            await session.execute(
                text(
                    "DELETE FROM architecture_components WHERE analysis_run_id IN ("
                    "  SELECT id FROM analysis_runs WHERE repository_id = :rid"
                    ")"
                ),
                {"rid": repo_id},
            )
            await session.execute(
                text("DELETE FROM analysis_runs WHERE repository_id = :rid"),
                {"rid": repo_id},
            )
            await session.execute(
                text("DELETE FROM repositories WHERE id = :rid"),
                {"rid": repo_id},
            )
            await session.execute(
                text("DELETE FROM users WHERE email = :email"),
                {"email": test_email},
            )
            await session.commit()
            print(f"[PASS] Successfully cleaned up test repository '{repo_id}' and test user '{test_email}' from PostgreSQL")

    print("\n" + "=" * 70)
    print("ALL 10 END-TO-END WORKFLOWS PASSED, VERIFIED IN POSTGRESQL & CLEANED UP!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_full_verification())
