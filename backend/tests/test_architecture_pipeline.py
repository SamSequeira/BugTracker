"""
test_architecture_pipeline.py
-----------------------------
Comprehensive tests for Architecture & Topology pipeline:
1. Technology Stack Detection (requirements.txt, package.json, pom.xml, Dockerfile, docker-compose.yml)
2. Architecture Component Detection & SourceFile Linking
3. Architecture Summary Generation (intent, architecture_overview, health_assessment, parser_version)
4. DAL Operations (technology_repo, architecture_component_repo, architecture_summary_repo)
5. End-to-End Pipeline Integration in complete_analysis_run
"""

import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.analysis_run import AnalysisRun
from app.models.analysis_technology import AnalysisTechnology
from app.models.architecture_component import ArchitectureComponent
from app.models.architecture_summary import ArchitectureSummary
from app.models.candidate_issues import CandidateIssue
from app.models.source_file import SourceFile
from app.repositories.architecture_component_repo import architecture_component_repository
from app.repositories.architecture_summary_repo import architecture_summary_repository
from app.repositories.technology_repo import technology_repository
from app.services.architecture_detector import architecture_detector
from app.services.architecture_summary_generator import architecture_summary_generator, PARSER_VERSION
from app.services.repository_analysis_service import repository_analysis_service
from app.services.technology_detector import technology_detector


# ===========================================================================
# 1. Technology Stack Detection Tests (Phase 2)
# ===========================================================================

def test_technology_detector_python_manifests(tmp_path):
    run_id = str(uuid.uuid4())
    req_file = tmp_path / "requirements.txt"
    req_file.write_text(
        "fastapi==0.115.0\n"
        "sqlalchemy>=2.0.0\n"
        "pydantic~=2.5.0\n"
        "pytest\n"
        "psycopg2-binary==2.9.9\n"
        "# Comment line\n",
        encoding="utf-8",
    )

    technologies = technology_detector.detect_technologies(
        str(tmp_path),
        run_id,
    )

    tech_names = {t.name: t for t in technologies}
    assert "FastAPI" in tech_names
    assert tech_names["FastAPI"].category == "Framework"
    assert tech_names["FastAPI"].version == "0.115.0"
    assert tech_names["FastAPI"].detection_source == "requirements.txt"

    assert "SQLAlchemy" in tech_names
    assert tech_names["SQLAlchemy"].category == "Database/ORM"
    assert tech_names["SQLAlchemy"].version == "2.0.0"

    assert "Pytest" in tech_names
    assert tech_names["Pytest"].category == "Testing"


def test_technology_detector_primary_ranking_and_directory_filtering(tmp_path):
    run_id = str(uuid.uuid4())

    # Root requirements.txt with primary and secondary libraries
    req_file = tmp_path / "requirements.txt"
    req_file.write_text(
        "colorama==0.4.6\n"
        "anyio==4.14.2\n"
        "fastapi==0.115.0\n"
        "click==8.4.2\n"
        "sqlalchemy>=2.0.0\n"
        "annotated-types==0.8.0\n",
        encoding="utf-8",
    )

    # Fake virtual environment directory that should be ignored
    venv_dir = tmp_path / ".venv" / "lib"
    venv_dir.mkdir(parents=True)
    (venv_dir / "requirements.txt").write_text("unwanted-subpackage==1.0\n", encoding="utf-8")

    technologies = technology_detector.detect_technologies(
        str(tmp_path),
        run_id,
        ast_result={"languages_detected": {"Python": 10}},
    )

    # 1. Verify virtualenv file was ignored
    tech_names = [t.name for t in technologies]
    assert "Unwanted Subpackage" not in tech_names

    # 2. Verify primary technologies (Language, Framework, Database/ORM) appear BEFORE secondary packages
    assert tech_names[0] == "Python"  # Programming Language (Priority 1)
    assert tech_names[1] == "FastAPI"  # Framework (Priority 2)
    assert tech_names[2] == "SQLAlchemy"  # Database/ORM (Priority 5)

    # 3. Verify secondary packages appear after
    secondary_index_anyio = tech_names.index("Anyio")
    secondary_index_click = tech_names.index("Click")
    secondary_index_colorama = tech_names.index("Colorama")
    assert secondary_index_anyio > 2
    assert secondary_index_click > 2
    assert secondary_index_colorama > 2

    # 4. Verify architecture summary generator prioritizes primary technologies
    summary = architecture_summary_generator.generate_summary(
        analysis_run_id=run_id,
        technologies=technologies,
        components=[],
        source_files=[],
        candidate_issues=[],
    )
    assert "Identified technology stack: Python, FastAPI, SQLAlchemy" in summary.architecture_overview
    assert "Colorama" not in summary.architecture_overview



def test_technology_detector_javascript_manifests(tmp_path):
    run_id = str(uuid.uuid4())
    pkg_file = tmp_path / "package.json"
    pkg_file.write_text(
        """{
            "dependencies": {
                "react": "^18.2.0",
                "lucide-react": "^0.300.0",
                "prisma": "~5.0.0"
            },
            "devDependencies": {
                "typescript": "^5.0.0",
                "vite": "^5.1.0",
                "vitest": "^1.0.0"
            }
        }""",
        encoding="utf-8",
    )

    technologies = technology_detector.detect_technologies(
        str(tmp_path),
        run_id,
    )

    tech_names = {t.name: t for t in technologies}
    assert "React" in tech_names
    assert tech_names["React"].category == "Frontend"
    assert tech_names["React"].version == "18.2.0"

    assert "Prisma" in tech_names
    assert tech_names["Prisma"].category == "Database/ORM"

    assert "TypeScript" in tech_names
    assert "Vite" in tech_names
    assert "Vitest" in tech_names


def test_technology_detector_docker_and_compose(tmp_path):
    run_id = str(uuid.uuid4())
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        "FROM python:3.11-slim\nWORKDIR /app\n",
        encoding="utf-8",
    )

    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n"
        "  db:\n"
        "    image: postgres:15-alpine\n"
        "  cache:\n"
        "    image: redis:7.0-alpine\n",
        encoding="utf-8",
    )

    technologies = technology_detector.detect_technologies(
        str(tmp_path),
        run_id,
    )

    tech_names = {t.name: t for t in technologies}
    assert "Docker" in tech_names
    assert "Python" in tech_names
    assert tech_names["Python"].version == "3.11"

    assert "PostgreSQL" in tech_names
    assert tech_names["PostgreSQL"].version == "15"

    assert "Redis" in tech_names
    assert tech_names["Redis"].version == "7.0"


# ===========================================================================
# 2. Architecture Component Detection Tests (Phase 3)
# ===========================================================================

def test_architecture_detector_component_grouping():
    run_id = str(uuid.uuid4())
    sample_files = [
        {"file": "app/api/v1/repositories.py", "language": "Python"},
        {"file": "app/api/v1/auth.py", "language": "Python"},
        {"file": "app/services/repository_analysis_service.py", "language": "Python"},
        {"file": "app/services/ast_generator.py", "language": "Python"},
        {"file": "app/models/source_file.py", "language": "Python"},
        {"file": "app/models/candidate_issues.py", "language": "Python"},
        {"file": "app/repositories/source_file_repo.py", "language": "Python"},
        {"file": "app/utils/git.py", "language": "Python"},
        {"file": "tests/test_api.py", "language": "Python"},
    ]

    components, file_map = architecture_detector.detect_components(
        repo_path="",
        analysis_run_id=run_id,
        files_data=sample_files,
    )

    comp_names = {c.name for c in components}
    assert "API & Endpoints Layer" in comp_names
    assert "Business Logic & Services" in comp_names
    assert "Data Persistence & Models" in comp_names
    assert "Utilities & Shared Helpers" in comp_names
    assert "Automated Test Suite" in comp_names

    # Check file to component mapping
    api_comp = next(c for c in components if c.name == "API & Endpoints Layer")
    service_comp = next(c for c in components if c.name == "Business Logic & Services")
    model_comp = next(c for c in components if c.name == "Data Persistence & Models")

    assert file_map["app/api/v1/repositories.py"]["component_id"] == api_comp.id
    assert file_map["app/services/ast_generator.py"]["component_id"] == service_comp.id
    assert file_map["app/models/source_file.py"]["component_id"] == model_comp.id
    assert file_map["app/models/source_file.py"]["role"] == "Data Model / Persistence Accessor"
    assert "source file" in file_map["app/models/source_file.py"]["intent"].lower()


# ===========================================================================
# 3. Architecture Summary Generation Tests (Phase 4)
# ===========================================================================

def test_architecture_summary_generator_deterministic():
    run_id = str(uuid.uuid4())

    techs = [
        AnalysisTechnology(id="t1", analysis_run_id=run_id, name="FastAPI", category="Framework"),
        AnalysisTechnology(id="t2", analysis_run_id=run_id, name="PostgreSQL", category="Database"),
    ]
    comps = [
        ArchitectureComponent(id="c1", analysis_run_id=run_id, name="API & Endpoints Layer", component_type="api_layer"),
        ArchitectureComponent(id="c2", analysis_run_id=run_id, name="Data Persistence & Models", component_type="persistence_layer"),
    ]
    source_files = [
        SourceFile(id="s1", analysis_run_id=run_id, component_id="c1", file_path="api/v1/auth.py", file_name="auth.py", language="Python", line_count=100),
        SourceFile(id="s2", analysis_run_id=run_id, component_id="c2", file_path="models/user.py", file_name="user.py", language="Python", line_count=50),
    ]
    issues = [
        CandidateIssue(id="i1", analysis_run_id=run_id, severity="critical", title="Issue 1", description="desc", file_path="api/v1/auth.py", urgency="high"),
        CandidateIssue(id="i2", analysis_run_id=run_id, severity="medium", title="Issue 2", description="desc", file_path="models/user.py", urgency="medium"),
    ]

    summary = architecture_summary_generator.generate_summary(
        analysis_run_id=run_id,
        technologies=techs,
        components=comps,
        source_files=source_files,
        candidate_issues=issues,
    )

    assert summary.analysis_run_id == run_id
    assert "FastAPI" in summary.intent
    assert "2 analyzed source files" in summary.architecture_overview
    assert "API & Endpoints Layer (1 files)" in summary.architecture_overview
    assert "2 candidate issues" in summary.health_assessment
    assert "1 critical" in summary.health_assessment
    assert summary.parser_version == PARSER_VERSION


# ===========================================================================
# 4. DAL Repository Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_technology_repo_crud():
    mock_db = AsyncMock()
    mock_db.add_all = MagicMock()
    mock_db.flush = AsyncMock()
    run_id = str(uuid.uuid4())
    tech = AnalysisTechnology(
        id=str(uuid.uuid4()),
        analysis_run_id=run_id,
        name="FastAPI",
        category="Framework",
        version="0.115.0",
    )

    created = await technology_repository.create_bulk(mock_db, [tech])
    assert len(created) == 1
    mock_db.add_all.assert_called_once_with([tech])
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_architecture_component_repo_crud():
    mock_db = AsyncMock()
    mock_db.add_all = MagicMock()
    mock_db.flush = AsyncMock()
    run_id = str(uuid.uuid4())
    comp = ArchitectureComponent(
        id=str(uuid.uuid4()),
        analysis_run_id=run_id,
        name="API Layer",
        component_type="api_layer",
    )

    created = await architecture_component_repository.create_bulk(mock_db, [comp])
    assert len(created) == 1
    mock_db.add_all.assert_called_once_with([comp])
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_architecture_summary_repo_crud():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    run_id = str(uuid.uuid4())
    summary = ArchitectureSummary(
        id=str(uuid.uuid4()),
        analysis_run_id=run_id,
        intent="Test intent",
        architecture_overview="Test overview",
        health_assessment="Test health",
        parser_version=PARSER_VERSION,
    )

    exec_result = MagicMock()
    exec_result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = exec_result

    saved = await architecture_summary_repository.create_or_update(mock_db, summary)
    assert saved.intent == "Test intent"
    mock_db.add.assert_called_once_with(summary)
    mock_db.flush.assert_called_once()


# ===========================================================================
# 5. End-to-End Pipeline Integration Test (Phase 5)
# ===========================================================================

@pytest.mark.asyncio
async def test_complete_analysis_run_end_to_end_architecture_pipeline(tmp_path):
    mock_db = AsyncMock()
    run_id = str(uuid.uuid4())

    analysis_run_mock = AnalysisRun(
        id=run_id,
        repository_id=str(uuid.uuid4()),
        status="running",
    )
    mock_db.get.return_value = analysis_run_mock

    # Create dummy repository files
    (tmp_path / "requirements.txt").write_text("fastapi==0.115.0\nsqlalchemy>=2.0.0\n", encoding="utf-8")
    api_dir = tmp_path / "api"
    api_dir.mkdir()
    (api_dir / "routes.py").write_text("def index():\n    return {'status': 'ok'}\n", encoding="utf-8")
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "user.py").write_text("class User:\n    id = 1\n", encoding="utf-8")

    sample_analysis_result = {
        "repository_path": str(tmp_path),
        "summary": {
            "total_files": 2,
            "supported_files": 2,
            "languages": {"Python": 2},
        },
        "_files_analyzed": [
            {
                "file": str(api_dir / "routes.py"),
                "file_name": "routes.py",
                "extension": ".py",
                "language": "Python",
                "line_count": 2,
                "is_supported": True,
                "success": True,
            },
            {
                "file": str(models_dir / "user.py"),
                "file_name": "user.py",
                "extension": ".py",
                "language": "Python",
                "line_count": 2,
                "is_supported": True,
                "success": True,
            },
        ],
        "candidate_issues": [
            {
                "rule_id": "PY_DIV_001",
                "issue_type": "division_by_zero",
                "message": "Division by zero",
                "file_path": str(api_dir / "routes.py"),
                "line_number": 1,
                "code_snippet": "x / 0",
                "severity": "high",
                "recommendation": "Add zero-division check",
            },
        ],
        "total_candidate_issues": 1,
    }

    captured_technologies = []
    captured_components = []
    captured_source_files = []
    captured_issues = []
    captured_statuses = []
    captured_recs = []
    captured_summary = None

    async def fake_tech_create(db, techs):
        captured_technologies.extend(techs)
        return techs

    async def fake_comp_create(db, comps):
        captured_components.extend(comps)
        return comps

    async def fake_sf_create(db, sfs):
        captured_source_files.extend(sfs)
        return sfs

    async def fake_issue_create(db, issues):
        captured_issues.extend(issues)
        return issues

    async def fake_status_create(db, statuses):
        captured_statuses.extend(statuses)
        return statuses

    async def fake_rec_create(db, recs):
        captured_recs.extend(recs)
        return recs

    async def fake_summary_save(db, summary):
        nonlocal captured_summary
        captured_summary = summary
        return summary

    with patch(
        "app.services.repository_analysis_service.technology_repository.create_bulk",
        side_effect=fake_tech_create,
    ), patch(
        "app.services.repository_analysis_service.architecture_component_repository.create_bulk",
        side_effect=fake_comp_create,
    ), patch(
        "app.services.repository_analysis_service.source_file_repository.create_bulk",
        side_effect=fake_sf_create,
    ), patch(
        "app.services.repository_analysis_service.candidate_issue_repository.create_bulk",
        side_effect=fake_issue_create,
    ), patch(
        "app.services.repository_analysis_service.issue_status_repository.create_bulk",
        side_effect=fake_status_create,
    ), patch(
        "app.services.repository_analysis_service.issue_recommendation_repository.create_bulk",
        side_effect=fake_rec_create,
    ), patch(
        "app.services.repository_analysis_service.architecture_summary_repository.create_or_update",
        side_effect=fake_summary_save,
    ):
        completed_run = await repository_analysis_service.complete_analysis_run(
            mock_db,
            run_id,
            sample_analysis_result,
        )

        assert completed_run.status == "completed"
        assert completed_run.candidate_issues_count == 1
        assert completed_run.completed_at is not None

        # 1. Technologies detected & persisted
        tech_names = {t.name for t in captured_technologies}
        assert "FastAPI" in tech_names
        assert "SQLAlchemy" in tech_names

        # 2. Components detected & persisted
        comp_names = {c.name for c in captured_components}
        assert "API & Endpoints Layer" in comp_names
        assert "Data Persistence & Models" in comp_names

        # 3. SourceFiles linked to Components
        assert len(captured_source_files) == 2
        for sf in captured_source_files:
            assert sf.component_id is not None
            assert sf.role is not None
            assert sf.intent is not None

        # 4. CandidateIssues linked to SourceFiles
        assert len(captured_issues) == 1
        assert captured_issues[0].source_file_id is not None
        routes_sf = next(sf for sf in captured_source_files if sf.file_name == "routes.py")
        assert captured_issues[0].source_file_id == routes_sf.id

        # 5. IssueRecommendations persisted
        assert len(captured_recs) == 1
        assert captured_recs[0].recommendation == "Add zero-division check"

        # 6. ArchitectureSummary persisted
        assert captured_summary is not None
        assert captured_summary.analysis_run_id == run_id
        assert "FastAPI" in captured_summary.intent
        assert "API & Endpoints Layer" in captured_summary.architecture_overview
        assert "1 high-severity" in captured_summary.health_assessment
        assert captured_summary.parser_version == PARSER_VERSION

        # 7. Single atomic commit executed
        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_not_called()
