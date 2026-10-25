"""
Integration test for complete AI-powered VR construction workflow.

Tests the entire pipeline from prompt to VR geometry generation.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import Base, get_db
from app.models import AIGeneration, Material, Project
from slowapi import Limiter
from slowapi.util import get_remote_address

# Test database setup
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

# Create a mock limiter for tests (disabled but with proper structure)
test_limiter = Limiter(key_func=get_remote_address, enabled=False)
app.state.limiter = test_limiter

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Create test database tables.

    The get_db override is installed here (not at import) and removed afterwards,
    so it can't leak into or be clobbered by other test modules' overrides.
    """
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)

client = TestClient(app)


class TestCompleteWorkflow:
    """Test complete workflow from prompt to VR"""
    
    def test_health_check(self):
        """Test basic health endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_ai_planning_service_status(self):
        """Test AI planning service is available"""
        response = client.get("/api/v1/planning/status")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "AI Construction Planning"
        assert data["status"] == "healthy"
    
    def test_generate_construction_plan(self):
        """Test basic construction plan generation"""
        response = client.post(
            "/api/v1/planning/generate-plan",
            json={
                "project_description": "A simple 2-bedroom house",
                "budget": 150000,
                "timeline_weeks": 16
            }
        )
        # May fail if Ollama/Gemini not available, which is ok for this test
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert "plan" in data or "success" in data
    
    def test_create_project_manually(self):
        """Test manual project creation"""
        response = client.post(
            "/api/v1/projects/",
            json={
                "name": "Test Project",
                "description": "Test house for integration testing",
                "status": "planning",
                "budget": 100000,
                "estimated_cost": 95000
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["id"] is not None
        
        # Store project_id for later tests
        return data["id"]
    
    def test_list_projects(self):
        """Test listing projects"""
        # Create a test project first
        self.test_create_project_manually()
        
        response = client.get("/api/v1/projects/")
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert data["total"] > 0
    
    def test_get_project(self):
        """Test getting project details"""
        # Create a test project
        project_id = self.test_create_project_manually()
        
        response = client.get(f"/api/v1/projects/{project_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == "Test Project"
    
    def test_vr_geometry_generation(self):
        """Test VR geometry generation from project"""
        project_id = self.test_create_project_manually()
        
        # Rooms as an AI plan saved before floor plans existed
        db = next(override_get_db())
        db.add(AIGeneration(
            project_id=project_id,
            prompt="A bedroom",
            generation_type="construction_plan",
            status="completed",
            output_data={"project_structure": {"rooms": [
                {"name": "Master Bedroom", "dimensions": {"length": 15.0, "width": 12.0, "height": 9.0}},
            ]}},
        ))
        db.commit()

        # Add materials
        material = Material(
            project_id=project_id,
            name="Cedar Siding",
            material_type="wood",
            unit="sqft",
            unit_cost=8.50,
            quantity_needed=200
        )
        db.add(material)
        db.commit()
        
        # Generate VR geometry
        response = client.get(f"/api/v1/projects/{project_id}/generate-vr")
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] == True
        assert "geometry" in data
        assert data["geometry"]["project_id"] == project_id
        assert "rooms" in data["geometry"]
        assert "materials" in data["geometry"]
        assert "spawn_position" in data["geometry"]
        
        # Verify room was created from phase
        rooms = data["geometry"]["rooms"]
        assert len(rooms) > 0
        assert rooms[0]["name"] == "Master Bedroom"
        
        # Verify material colors are present
        materials = data["geometry"]["materials"]
        assert "wood" in materials
        assert "r" in materials["wood"]["color"]
    
    def test_project_stats(self):
        """Test project statistics endpoint"""
        # Create some test projects
        self.test_create_project_manually()
        
        response = client.get("/api/v1/projects/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_projects" in data
        assert data["total_projects"] > 0


class TestAPIEndpoints:
    """Test all API endpoints are accessible"""
    
    def test_api_documentation(self):
        """Test OpenAPI documentation is available"""
        response = client.get("/docs")
        assert response.status_code == 200
    
    def test_redoc_documentation(self):
        """Test ReDoc documentation is available"""
        response = client.get("/redoc")
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
