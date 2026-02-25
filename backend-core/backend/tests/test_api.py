import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from slowapi import Limiter
from slowapi.util import get_remote_address

# Test database URL
TEST_DATABASE_URL = "sqlite:///:memory:"

# Create test database engine
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Create test session
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override the get_db dependency to use the test database
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# Create a mock limiter for tests (disabled but with proper structure)
test_limiter = Limiter(key_func=get_remote_address, enabled=False)
app.state.limiter = test_limiter

# Create test client
client = TestClient(app)

@pytest.fixture(scope="function", autouse=True)
def setup_database():
    """Create tables before each test and drop after.

    Re-asserts the dependency override each time because other test modules
    (e.g. test_complete_workflow.py) set their own override at module level,
    which would otherwise clobber this file's in-memory engine.
    """
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_health_check():
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"
    assert "environment" in data

def test_root_endpoint():
    """Test root endpoint returns 404 (not configured)."""
    response = client.get("/")
    assert response.status_code == 404

def test_docs_endpoint():
    """Test that API documentation is accessible."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "VR Construction API" in response.text

def test_openapi_json():
    """Test OpenAPI JSON endpoint."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "info" in data
    assert data["info"]["title"] == "VR Construction API"

# Project CRUD tests
def test_create_project():
    """Test creating a new project."""
    project_data = {
        "name": "Test Project",
        "description": "A test construction project",
        "budget": 100000.0,
        "timeline_weeks": 12,
        "status": "planning"
    }
    response = client.post("/api/v1/projects/", json=project_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == project_data["name"]
    assert data["description"] == project_data["description"]
    assert "id" in data

def test_get_projects():
    """Test getting all projects."""
    response = client.get("/api/v1/projects/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["projects"], list)
    assert "total" in data
    assert "page" in data

def test_get_nonexistent_project():
    """Test getting a project that doesn't exist."""
    response = client.get("/api/v1/projects/999")
    assert response.status_code == 404

# Design tests
def test_create_design():
    """Test creating a new design."""
    # First create a project
    project_data = {
        "name": "Design Test Project",
        "description": "Project for design testing",
        "budget": 50000.0,
        "timeline_weeks": 8,
        "status": "design"
    }
    project_response = client.post("/api/v1/projects/", json=project_data)
    project_id = project_response.json()["id"]

    design_data = {
        "name": "Floor Plan Design",
        "description": "Main floor plan for the project",
        "project_id": project_id,
        "design_type": "floor_plan",
        "version": "1.0",
        "status": "draft"
    }
    response = client.post("/api/v1/designs/", json=design_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == design_data["name"]
    assert data["project_id"] == project_id
    assert data["design_type"] == "floor_plan"

def test_get_designs():
    """Test getting all designs."""
    response = client.get("/api/v1/designs/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

# Material tests
def test_get_materials():
    """Test getting materials catalog."""
    response = client.get("/api/v1/materials/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["materials"], list)
    assert "total" in data
    assert "page" in data

# AI Image tests (mock required for actual functionality)
def test_ai_image_generation_requires_auth_or_mock():
    """Test AI image generation endpoint structure."""
    # This will likely fail without proper setup, but tests the route exists
    image_data = {
        "project_id": 1,
        "prompt": "modern house exterior",
        "style": "realistic"
    }
    response = client.post("/api/v1/image/generate", json=image_data)
    # Expect 400 or 500 without proper AI setup, but not 404
    assert response.status_code != 404
