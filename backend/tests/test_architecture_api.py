"""
test_architecture_api.py
-------------------------
Integration tests for Architecture & Topology API endpoints:
- GET /api/v1/repositories/analysis/{analysis_run_id}/architecture
- GET /api/v1/repositories/{repository_id}/architecture
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.repositories import router as repositories_router
from app.models.analysis_run import AnalysisRun
from app.models.analysis_technology import AnalysisTechnology
from app.models.architecture_component import ArchitectureComponent
from app.models.architecture_summary import ArchitectureSummary
from app.models.candidate_issues import CandidateIssue
from app.models.repository import Repository
from app.models.source_file import SourceFile
from app.schemas.architecture import ArchitectureTopologyResponse
from data.dbconnection.session import get_db


# Setup dedicated test app with repositories router
architecture_test_app = FastAPI(title="Architecture API Test App")
architecture_test_app.include_router(repositories_router, prefix="/api/v1")


@pytest.fixture
def mock_db_session():
    """Fixture providing an AsyncMock session for database dependency injection."""
    session = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def test_client(mock_db_session):
    """Fixture providing an AsyncClient with overridden database session dependency."""
    async def override_get_db():
        yield mock_db_session

    architecture_test_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=architecture_test_app)
    client = AsyncClient(transport=transport, base_url="http://test")
    return client, mock_db_session


@pytest.mark.asyncio
async def test_get_analysis_run_architecture_success(test_client):
    client, mock_db = test_client
    run_id = str(uuid.uuid4())
    repo_id = str(uuid.uuid4())
    comp_id1 = str(uuid.uuid4())
    comp_id2 = str(uuid.uuid4())

    analysis_run = AnalysisRun(
        id=run_id,
        repository_id=repo_id,
        status="completed",
    )
    summary = ArchitectureSummary(
        id=str(uuid.uuid4()),
        analysis_run_id=run_id,
        intent="Implements a backend API built with FastAPI and PostgreSQL.",
        architecture_overview="Organized into 2 logical components.",
        health_assessment="Codebase exhibits good hygiene.",
        parser_version="Tree-Sitter 0.22 / BugTracker AST Engine v1.0.0",
    )
    techs = [
        AnalysisTechnology(id=str(uuid.uuid4()), analysis_run_id=run_id, name="Anyio", category="Library/Package", version="4.14.2", detection_source="requirements.txt"),
        AnalysisTechnology(id=str(uuid.uuid4()), analysis_run_id=run_id, name="FastAPI", category="Framework", version="0.115.0", detection_source="requirements.txt"),
        AnalysisTechnology(id=str(uuid.uuid4()), analysis_run_id=run_id, name="PostgreSQL", category="Database", version="15", detection_source="Dockerfile"),
        AnalysisTechnology(id=str(uuid.uuid4()), analysis_run_id=run_id, name="Pydantic", category="Utility/Library", version="2.13.4", detection_source="requirements.txt"),
    ]
    comps = [
        ArchitectureComponent(id=comp_id1, analysis_run_id=run_id, name="API Layer", component_type="api_layer", description="HTTP endpoints", root_path="app/api"),
        ArchitectureComponent(id=comp_id2, analysis_run_id=run_id, name="Data Layer", component_type="persistence_layer", description="DB models", root_path="app/models"),
    ]
    source_files = [
        SourceFile(id=str(uuid.uuid4()), analysis_run_id=run_id, component_id=comp_id1, file_path="app/api/auth.py", file_name="auth.py", extension=".py", language="Python", line_count=100, role="API Request Handler", intent="Handles login", is_supported=True),
        SourceFile(id=str(uuid.uuid4()), analysis_run_id=run_id, component_id=comp_id2, file_path="app/models/user.py", file_name="user.py", extension=".py", language="Python", line_count=50, role="Data Model", intent="Defines User entity", is_supported=True),
        SourceFile(id=str(uuid.uuid4()), analysis_run_id=run_id, component_id=None, file_path="README.md", file_name="README.md", extension=".md", language="Markdown", line_count=20, role="Documentation", intent="Project docs", is_supported=False),
    ]

    mock_db.get.return_value = analysis_run

    with patch("app.api.v1.repositories.architecture_summary_repository.get_by_analysis_run_id", new=AsyncMock(return_value=summary)), \
         patch("app.api.v1.repositories.technology_repository.list_by_analysis_run_id", new=AsyncMock(return_value=techs)), \
         patch("app.api.v1.repositories.architecture_component_repository.list_by_analysis_run_id", new=AsyncMock(return_value=comps)), \
         patch("app.api.v1.repositories.source_file_repository.list_by_analysis_run_id", new=AsyncMock(return_value=source_files)):

        response = await client.get(f"/api/v1/repositories/analysis/{run_id}/architecture")

        assert response.status_code == 200
        data = response.json()

        # Validate schema conformance
        parsed_response = ArchitectureTopologyResponse(**data)
        assert parsed_response.analysis_run_id == run_id
        assert parsed_response.repository_id == repo_id
        assert parsed_response.summary.intent == summary.intent
        assert parsed_response.summary.parser_version == summary.parser_version

        # Technologies (all 4, sorted with primary first)
        assert len(parsed_response.technologies) == 4
        # Primary technologies must be first (FastAPI, PostgreSQL)
        assert parsed_response.technologies[0].name == "FastAPI"
        assert parsed_response.technologies[1].name == "PostgreSQL"
        # Secondary technologies follow (Pydantic, Anyio)
        assert parsed_response.technologies[2].name == "Pydantic"
        assert parsed_response.technologies[3].name == "Anyio"

        # Primary and secondary technology separation
        assert len(parsed_response.primary_technologies) == 2
        assert len(parsed_response.secondary_technologies) == 2
        assert {t.name for t in parsed_response.primary_technologies} == {"FastAPI", "PostgreSQL"}
        assert {t.name for t in parsed_response.secondary_technologies} == {"Pydantic", "Anyio"}

        assert parsed_response.total_technologies == 4
        assert parsed_response.total_primary_technologies == 2
        assert parsed_response.total_secondary_technologies == 2

        # Components and nested source files
        assert len(parsed_response.components) == 2
        api_comp = next(c for c in parsed_response.components if c.name == "API Layer")
        assert len(api_comp.source_files) == 1
        assert api_comp.source_files[0].file_name == "auth.py"

        data_comp = next(c for c in parsed_response.components if c.name == "Data Layer")
        assert len(data_comp.source_files) == 1
        assert data_comp.source_files[0].file_name == "user.py"

        # Uncategorized files
        assert len(parsed_response.uncategorized_files) == 1
        assert parsed_response.uncategorized_files[0].file_name == "README.md"

        assert parsed_response.total_source_files == 3
        assert parsed_response.total_components == 2


@pytest.mark.asyncio
async def test_get_analysis_run_architecture_not_found(test_client):
    client, mock_db = test_client
    run_id = str(uuid.uuid4())
    mock_db.get.return_value = None

    response = await client.get(f"/api/v1/repositories/analysis/{run_id}/architecture")
    assert response.status_code == 404
    assert "Analysis run not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_repository_architecture_success(test_client):
    client, mock_db = test_client
    repo_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    repo = Repository(id=repo_id, name="sample-repo", s3_key="repos/sample.zip")
    latest_run = AnalysisRun(id=run_id, repository_id=repo_id, status="completed")

    summary = ArchitectureSummary(
        id=str(uuid.uuid4()),
        analysis_run_id=run_id,
        intent="Sample application intent",
        architecture_overview="Overview details",
        health_assessment="Healthy",
        parser_version="Tree-Sitter 0.22",
    )

    with patch("app.api.v1.repositories.repository_repository.get_by_id", new=AsyncMock(return_value=repo)), \
         patch("app.api.v1.repositories.architecture_summary_repository.get_by_analysis_run_id", new=AsyncMock(return_value=summary)), \
         patch("app.api.v1.repositories.technology_repository.list_by_analysis_run_id", new=AsyncMock(return_value=[])), \
         patch("app.api.v1.repositories.architecture_component_repository.list_by_analysis_run_id", new=AsyncMock(return_value=[])), \
         patch("app.api.v1.repositories.source_file_repository.list_by_analysis_run_id", new=AsyncMock(return_value=[])):

        # Mock db.execute for finding latest completed run
        exec_mock = MagicMock()
        exec_mock.scalars.return_value.first.return_value = latest_run
        mock_db.execute.return_value = exec_mock

        response = await client.get(f"/api/v1/repositories/{repo_id}/architecture")

        assert response.status_code == 200
        data = response.json()
        assert data["analysis_run_id"] == run_id
        assert data["repository_id"] == repo_id
        assert data["summary"]["intent"] == "Sample application intent"


@pytest.mark.asyncio
async def test_get_repository_architecture_repo_not_found(test_client):
    client, mock_db = test_client
    repo_id = str(uuid.uuid4())

    with patch("app.api.v1.repositories.repository_repository.get_by_id", new=AsyncMock(return_value=None)):
        response = await client.get(f"/api/v1/repositories/{repo_id}/architecture")
        assert response.status_code == 404
        assert response.json()["detail"] == "Repository not found."


@pytest.mark.asyncio
async def test_get_repository_architecture_no_completed_run(test_client):
    client, mock_db = test_client
    repo_id = str(uuid.uuid4())
    repo = Repository(id=repo_id, name="sample-repo", s3_key="repos/sample.zip")

    with patch("app.api.v1.repositories.repository_repository.get_by_id", new=AsyncMock(return_value=repo)):
        exec_mock = MagicMock()
        exec_mock.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = exec_mock

        response = await client.get(f"/api/v1/repositories/{repo_id}/architecture")
        assert response.status_code == 404
        assert "No completed analysis run found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_list_repository_candidate_issues_success(test_client):
    client, mock_db = test_client
    repo_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    issue_id = str(uuid.uuid4())

    repo = Repository(id=repo_id, name="sample-repo", s3_key="repos/sample.zip")
    latest_run = AnalysisRun(id=run_id, repository_id=repo_id, status="completed")
    issue = CandidateIssue(
        id=issue_id,
        analysis_run_id=run_id,
        title="Division By Zero (PY_DIV_001)",
        description="Division by zero found",
        file_path="src/calc.py",
        line_number=10,
        severity="high",
        urgency="high",
        code_snippet="return a / b",
        evidence={"security_impact": "Potential denial of service"},
    )
    issue.status = None
    issue.recommendations = []

    with patch("app.api.v1.repositories.repository_repository.get_by_id", new=AsyncMock(return_value=repo)):
        exec_run = MagicMock()
        exec_run.scalars.return_value.first.return_value = latest_run

        exec_issues = MagicMock()
        exec_issues.scalars.return_value.all.return_value = [issue]

        mock_db.execute.side_effect = [exec_run, exec_issues]

        response = await client.get(f"/api/v1/repositories/{repo_id}/candidate-issues")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["id"] == issue_id
        assert item["file_path"] == "src/calc.py"
        assert item["severity"] == "high"
        assert item["security_impact"] == "Potential denial of service"
        assert item["status"] == "open"


@pytest.mark.asyncio
async def test_list_repository_candidate_issues_repo_not_found(test_client):
    client, mock_db = test_client
    repo_id = str(uuid.uuid4())

    with patch("app.api.v1.repositories.repository_repository.get_by_id", new=AsyncMock(return_value=None)):
        response = await client.get(f"/api/v1/repositories/{repo_id}/candidate-issues")
        assert response.status_code == 404
        assert response.json()["detail"] == "Repository not found."


@pytest.mark.asyncio
async def test_list_repository_candidate_issues_no_completed_run(test_client):
    client, mock_db = test_client
    repo_id = str(uuid.uuid4())
    repo = Repository(id=repo_id, name="sample-repo", s3_key="repos/sample.zip")

    with patch("app.api.v1.repositories.repository_repository.get_by_id", new=AsyncMock(return_value=repo)):
        exec_mock = MagicMock()
        exec_mock.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = exec_mock

        response = await client.get(f"/api/v1/repositories/{repo_id}/candidate-issues")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
"""
test_architecture_api.py
-------------------------
Integration tests for Architecture & Topology API endpoints:
- GET /api/v1/repositories/analysis/{analysis_run_id}/architecture
- GET /api/v1/repositories/{repository_id}/architecture
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.repositories import router as repositories_router
from app.models.analysis_run import AnalysisRun
from app.models.analysis_technology import AnalysisTechnology
from app.models.architecture_component import ArchitectureComponent
from app.models.architecture_summary import ArchitectureSummary
from app.models.candidate_issues import CandidateIssue
from app.models.repository import Repository
from app.models.source_file import SourceFile
from app.schemas.architecture import ArchitectureTopologyResponse
from data.dbconnection.session import get_db


# Setup dedicated test app with repositories router
architecture_test_app = FastAPI(title="Architecture API Test App")
architecture_test_app.include_router(repositories_router, prefix="/api/v1")


@pytest.fixture
def mock_db_session():
    """Fixture providing an AsyncMock session for database dependency injection."""
    session = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def test_client(mock_db_session):
    """Fixture providing an AsyncClient with overridden database session dependency."""
    async def override_get_db():
        yield mock_db_session

    architecture_test_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=architecture_test_app)
    client = AsyncClient(transport=transport, base_url="http://test")
    return client, mock_db_session


@pytest.mark.asyncio
async def test_get_analysis_run_architecture_success(test_client):
    client, mock_db = test_client
    run_id = str(uuid.uuid4())
    repo_id = str(uuid.uuid4())
    comp_id1 = str(uuid.uuid4())
    comp_id2 = str(uuid.uuid4())

    analysis_run = AnalysisRun(
        id=run_id,
        repository_id=repo_id,
        status="completed",
    )
    summary = ArchitectureSummary(
        id=str(uuid.uuid4()),
        analysis_run_id=run_id,
        intent="Implements a backend API built with FastAPI and PostgreSQL.",
        architecture_overview="Organized into 2 logical components.",
        health_assessment="Codebase exhibits good hygiene.",
        parser_version="Tree-Sitter 0.22 / BugTracker AST Engine v1.0.0",
    )
    techs = [
        AnalysisTechnology(id=str(uuid.uuid4()), analysis_run_id=run_id, name="Anyio", category="Library/Package", version="4.14.2", detection_source="requirements.txt"),
        AnalysisTechnology(id=str(uuid.uuid4()), analysis_run_id=run_id, name="FastAPI", category="Framework", version="0.115.0", detection_source="requirements.txt"),
        AnalysisTechnology(id=str(uuid.uuid4()), analysis_run_id=run_id, name="PostgreSQL", category="Database", version="15", detection_source="Dockerfile"),
        AnalysisTechnology(id=str(uuid.uuid4()), analysis_run_id=run_id, name="Pydantic", category="Utility/Library", version="2.13.4", detection_source="requirements.txt"),
    ]
    comps = [
        ArchitectureComponent(id=comp_id1, analysis_run_id=run_id, name="API Layer", component_type="api_layer", description="HTTP endpoints", root_path="app/api"),
        ArchitectureComponent(id=comp_id2, analysis_run_id=run_id, name="Data Layer", component_type="persistence_layer", description="DB models", root_path="app/models"),
    ]
    source_files = [
        SourceFile(id=str(uuid.uuid4()), analysis_run_id=run_id, component_id=comp_id1, file_path="app/api/auth.py", file_name="auth.py", extension=".py", language="Python", line_count=100, role="API Request Handler", intent="Handles login", is_supported=True),
        SourceFile(id=str(uuid.uuid4()), analysis_run_id=run_id, component_id=comp_id2, file_path="app/models/user.py", file_name="user.py", extension=".py", language="Python", line_count=50, role="Data Model", intent="Defines User entity", is_supported=True),
        SourceFile(id=str(uuid.uuid4()), analysis_run_id=run_id, component_id=None, file_path="README.md", file_name="README.md", extension=".md", language="Markdown", line_count=20, role="Documentation", intent="Project docs", is_supported=False),
    ]

    mock_db.get.return_value = analysis_run

    with patch("app.api.v1.repositories.architecture_summary_repository.get_by_analysis_run_id", new=AsyncMock(return_value=summary)), \
         patch("app.api.v1.repositories.technology_repository.list_by_analysis_run_id", new=AsyncMock(return_value=techs)), \
         patch("app.api.v1.repositories.architecture_component_repository.list_by_analysis_run_id", new=AsyncMock(return_value=comps)), \
         patch("app.api.v1.repositories.source_file_repository.list_by_analysis_run_id", new=AsyncMock(return_value=source_files)):

        response = await client.get(f"/api/v1/repositories/analysis/{run_id}/architecture")

        assert response.status_code == 200
        data = response.json()

        # Validate schema conformance
        parsed_response = ArchitectureTopologyResponse(**data)
        assert parsed_response.analysis_run_id == run_id
        assert parsed_response.repository_id == repo_id
        assert parsed_response.summary.intent == summary.intent
        assert parsed_response.summary.parser_version == summary.parser_version

        # Technologies (all 4, sorted with primary first)
        assert len(parsed_response.technologies) == 4
        # Primary technologies must be first (FastAPI, PostgreSQL)
        assert parsed_response.technologies[0].name == "FastAPI"
        assert parsed_response.technologies[1].name == "PostgreSQL"
        # Secondary technologies follow (Pydantic, Anyio)
        assert parsed_response.technologies[2].name == "Pydantic"
        assert parsed_response.technologies[3].name == "Anyio"

        # Primary and secondary technology separation
        assert len(parsed_response.primary_technologies) == 2
        assert len(parsed_response.secondary_technologies) == 2
        assert {t.name for t in parsed_response.primary_technologies} == {"FastAPI", "PostgreSQL"}
        assert {t.name for t in parsed_response.secondary_technologies} == {"Pydantic", "Anyio"}

        assert parsed_response.total_technologies == 4
        assert parsed_response.total_primary_technologies == 2
        assert parsed_response.total_secondary_technologies == 2

        # Components and nested source files
        assert len(parsed_response.components) == 2
        api_comp = next(c for c in parsed_response.components if c.name == "API Layer")
        assert len(api_comp.source_files) == 1
        assert api_comp.source_files[0].file_name == "auth.py"

        data_comp = next(c for c in parsed_response.components if c.name == "Data Layer")
        assert len(data_comp.source_files) == 1
        assert data_comp.source_files[0].file_name == "user.py"

        # Uncategorized files
        assert len(parsed_response.uncategorized_files) == 1
        assert parsed_response.uncategorized_files[0].file_name == "README.md"

        assert parsed_response.total_source_files == 3
        assert parsed_response.total_components == 2


@pytest.mark.asyncio
async def test_get_analysis_run_architecture_not_found(test_client):
    client, mock_db = test_client
    run_id = str(uuid.uuid4())
    mock_db.get.return_value = None

    response = await client.get(f"/api/v1/repositories/analysis/{run_id}/architecture")
    assert response.status_code == 404
    assert "Analysis run not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_repository_architecture_success(test_client):
    client, mock_db = test_client
    repo_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    repo = Repository(id=repo_id, name="sample-repo", s3_key="repos/sample.zip")
    latest_run = AnalysisRun(id=run_id, repository_id=repo_id, status="completed")

    summary = ArchitectureSummary(
        id=str(uuid.uuid4()),
        analysis_run_id=run_id,
        intent="Sample application intent",
        architecture_overview="Overview details",
        health_assessment="Healthy",
        parser_version="Tree-Sitter 0.22",
    )

    with patch("app.api.v1.repositories.repository_repository.get_by_id", new=AsyncMock(return_value=repo)), \
         patch("app.api.v1.repositories.architecture_summary_repository.get_by_analysis_run_id", new=AsyncMock(return_value=summary)), \
         patch("app.api.v1.repositories.technology_repository.list_by_analysis_run_id", new=AsyncMock(return_value=[])), \
         patch("app.api.v1.repositories.architecture_component_repository.list_by_analysis_run_id", new=AsyncMock(return_value=[])), \
         patch("app.api.v1.repositories.source_file_repository.list_by_analysis_run_id", new=AsyncMock(return_value=[])):

        # Mock db.execute for finding latest completed run
        exec_mock = MagicMock()
        exec_mock.scalars.return_value.first.return_value = latest_run
        mock_db.execute.return_value = exec_mock

        response = await client.get(f"/api/v1/repositories/{repo_id}/architecture")

        assert response.status_code == 200
        data = response.json()
        assert data["analysis_run_id"] == run_id
        assert data["repository_id"] == repo_id
        assert data["summary"]["intent"] == "Sample application intent"


@pytest.mark.asyncio
async def test_get_repository_architecture_repo_not_found(test_client):
    client, mock_db = test_client
    repo_id = str(uuid.uuid4())

    with patch("app.api.v1.repositories.repository_repository.get_by_id", new=AsyncMock(return_value=None)):
        response = await client.get(f"/api/v1/repositories/{repo_id}/architecture")
        assert response.status_code == 404
        assert response.json()["detail"] == "Repository not found."


@pytest.mark.asyncio
async def test_get_repository_architecture_no_completed_run(test_client):
    client, mock_db = test_client
    repo_id = str(uuid.uuid4())
    repo = Repository(id=repo_id, name="sample-repo", s3_key="repos/sample.zip")

    with patch("app.api.v1.repositories.repository_repository.get_by_id", new=AsyncMock(return_value=repo)):
        exec_mock = MagicMock()
        exec_mock.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = exec_mock

        response = await client.get(f"/api/v1/repositories/{repo_id}/architecture")
        assert response.status_code == 404
        assert "No completed analysis run found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_list_repository_candidate_issues_success(test_client):
    client, mock_db = test_client
    repo_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    issue_id = str(uuid.uuid4())

    repo = Repository(id=repo_id, name="sample-repo", s3_key="repos/sample.zip")
    latest_run = AnalysisRun(id=run_id, repository_id=repo_id, status="completed")
    issue = CandidateIssue(
        id=issue_id,
        analysis_run_id=run_id,
        title="Division By Zero (PY_DIV_001)",
        description="Division by zero found",
        file_path="src/calc.py",
        line_number=10,
        severity="high",
        urgency="high",
        security_impact="Potential denial of service",
        code_snippet="return a / b",
    )
    issue.status = None
    issue.recommendations = []

    with patch("app.api.v1.repositories.repository_repository.get_by_id", new=AsyncMock(return_value=repo)):
        exec_run = MagicMock()
        exec_run.scalars.return_value.first.return_value = latest_run

        exec_issues = MagicMock()
        exec_issues.scalars.return_value.all.return_value = [issue]

        mock_db.execute.side_effect = [exec_run, exec_issues]

        response = await client.get(f"/api/v1/repositories/{repo_id}/candidate-issues")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["id"] == issue_id
        assert item["file_path"] == "src/calc.py"
        assert item["severity"] == "high"
        assert item["security_impact"] == "Potential denial of service"
        assert item["status"] == "open"


@pytest.mark.asyncio
async def test_list_repository_candidate_issues_repo_not_found(test_client):
    client, mock_db = test_client
    repo_id = str(uuid.uuid4())

    with patch("app.api.v1.repositories.repository_repository.get_by_id", new=AsyncMock(return_value=None)):
        response = await client.get(f"/api/v1/repositories/{repo_id}/candidate-issues")
        assert response.status_code == 404
        assert response.json()["detail"] == "Repository not found."


@pytest.mark.asyncio
async def test_list_repository_candidate_issues_no_completed_run(test_client):
    client, mock_db = test_client
    repo_id = str(uuid.uuid4())
    repo = Repository(id=repo_id, name="sample-repo", s3_key="repos/sample.zip")

    with patch("app.api.v1.repositories.repository_repository.get_by_id", new=AsyncMock(return_value=repo)):
        exec_mock = MagicMock()
        exec_mock.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = exec_mock

        response = await client.get(f"/api/v1/repositories/{repo_id}/candidate-issues")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
