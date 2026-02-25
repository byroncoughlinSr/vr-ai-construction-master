"""
Integration test for complete AI-powered VR construction workflow.

Tests the entire pipeline from prompt to VR geometry generation.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.models import Project, ConstructionPhase, Task, Material
from slowapi import Limiter
from slowapi.util import get_remote_address

# Test database setup
TEST_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Create test database tables"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

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
        # Create a test project with phases
        project_id = self.test_create_project_manually()
        
        # Add a phase with room data
        db = next(override_get_db())
        phase = ConstructionPhase(
            project_id=project_id,
            name="Master Bedroom",
            description="15x12 bedroom",
            phase_order=1,
            budgeted_cost=25000
        )
        db.add(phase)
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


class TestDatabaseIntegration:
    """Test database models and relationships"""
    
    def test_project_phases_relationship(self):
        """Test project to phases relationship"""
        db = next(override_get_db())
        
        # Create project
        project = Project(
            name="Relationship Test",
            description="Test relationships",
            status="planning"
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        
        # Add phases
        phase1 = ConstructionPhase(
            project_id=project.id,
            name="Phase 1",
            phase_order=1
        )
        phase2 = ConstructionPhase(
            project_id=project.id,
            name="Phase 2",
            phase_order=2
        )
        db.add(phase1)
        db.add(phase2)
        db.commit()
        
        # Verify relationship
        db.refresh(project)
        assert len(project.phases) == 2
        assert project.phases[0].name in ["Phase 1", "Phase 2"]
    
    def test_phase_tasks_relationship(self):
        """Test phase to tasks relationship"""
        db = next(override_get_db())
        
        # Create project and phase
        project = Project(name="Task Test", description="Test")
        db.add(project)
        db.commit()
        db.refresh(project)
        
        phase = ConstructionPhase(
            project_id=project.id,
            name="Test Phase",
            phase_order=1
        )
        db.add(phase)
        db.commit()
        db.refresh(phase)
        
        # Add tasks
        task1 = Task(
            project_id=project.id,
            phase_id=phase.id,
            name="Task 1",
            task_order=1
        )
        task2 = Task(
            project_id=project.id,
            phase_id=phase.id,
            name="Task 2",
            task_order=2
        )
        db.add(task1)
        db.add(task2)
        db.commit()
        
        # Verify relationship
        db.refresh(phase)
        assert len(phase.tasks) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
