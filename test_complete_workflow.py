#!/usr/bin/env python3
"""
Complete Workflow Test for VR AI Construction Project

This script tests the entire pipeline from prompt to VR:
1. Generate project from text prompt
2. Verify database records created
3. Generate VR geometry
4. Verify all components work together

Usage:
    python test_complete_workflow.py
"""

import requests
import json
import time
import sys

# Configuration
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

def print_section(title):
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def test_backend_health():
    """Test that the backend is running and healthy."""
    print_section("Step 1: Backend Health Check")
    
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Backend is healthy")
            print(f"   Environment: {response.json().get('environment')}")
            return True
        else:
            print(f"❌ Backend returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to backend: {e}")
        print(f"   Make sure backend is running at {BASE_URL}")
        return False

def test_ai_service_status():
    """Test that AI services are available."""
    print_section("Step 2: AI Service Status")
    
    try:
        response = requests.get(f"{API_BASE}/planning/status", timeout=5)
        data = response.json()
        
        print(f"Service: {data.get('service')}")
        print(f"Status: {data.get('status')}")
        print(f"Ollama Available: {data.get('ollama_available')}")
        print(f"Gemini Available: {data.get('gemini_available')}")
        
        if data.get('ollama_available') or data.get('gemini_available'):
            print("✅ At least one AI service is available")
            return True
        else:
            print("❌ No AI services available")
            return False
    except Exception as e:
        print(f"❌ Failed to check AI status: {e}")
        return False

def test_generate_project(prompt, budget=75000, timeline=12):
    """Test complete project generation from a prompt."""
    print_section("Step 3: Generate Complete Project")
    
    print(f"Prompt: {prompt}")
    print(f"Budget: ${budget:,}")
    print(f"Timeline: {timeline} weeks")
    
    try:
        payload = {
            "prompt": prompt,
            "budget": budget,
            "timeline_weeks": timeline,
            "generate_image": False  # Skip image generation for faster testing
        }
        
        print("\n📤 Sending request to backend...")
        response = requests.post(
            f"{API_BASE}/planning/generate-project",
            json=payload,
            timeout=60
        )
        
        if response.status_code == 201:
            data = response.json()
            
            print("\n✅ Project generated successfully!")
            print(f"   Project ID: {data.get('project_id')}")
            print(f"   Project Name: {data.get('project_name')}")
            print(f"   Description: {data.get('description')}")
            
            metadata = data.get('metadata', {})
            print(f"\n📊 Project Metadata:")
            print(f"   Total Cost: ${metadata.get('total_cost', 0):,}")
            print(f"   Duration: {metadata.get('total_duration_weeks', 0)} weeks")
            print(f"   Phases: {metadata.get('phases_count', 0)}")
            print(f"   Materials: {metadata.get('materials_count', 0)}")
            print(f"   AI Source: {metadata.get('ai_source', 'unknown')}")
            
            return data.get('project_id')
        else:
            print(f"❌ Project generation failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return None

def test_get_project(project_id):
    """Test retrieving project details."""
    print_section("Step 4: Verify Project in Database")
    
    try:
        response = requests.get(f"{API_BASE}/projects/{project_id}", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"✅ Project retrieved successfully")
            print(f"   ID: {data.get('id')}")
            print(f"   Name: {data.get('name')}")
            print(f"   Status: {data.get('status')}")
            print(f"   Budget: ${data.get('budget', 0):,}")
            print(f"   Estimated Cost: ${data.get('estimated_cost', 0):,}")
            
            return True
        else:
            print(f"❌ Failed to retrieve project: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False

def test_generate_vr_geometry(project_id):
    """Test VR geometry generation."""
    print_section("Step 5: Generate VR Geometry")
    
    try:
        response = requests.get(
            f"{API_BASE}/projects/{project_id}/generate-vr",
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('success'):
                geometry = data.get('geometry', {})
                metadata = geometry.get('metadata', {})
                
                print(f"✅ VR geometry generated successfully!")
                print(f"   Project: {geometry.get('project_name')}")
                print(f"   Rooms: {metadata.get('total_rooms', 0)}")
                print(f"   Doors: {metadata.get('total_doors', 0)}")
                print(f"   Windows: {metadata.get('total_windows', 0)}")
                print(f"   Platform: {metadata.get('platform', 'unknown')}")
                
                spawn = geometry.get('spawn_position', {})
                print(f"   Spawn Position: ({spawn.get('x')}, {spawn.get('y')}, {spawn.get('z')})")
                
                # Show room details
                rooms = geometry.get('rooms', [])
                if rooms:
                    print(f"\n📐 Room Details:")
                    for room in rooms[:3]:  # Show first 3 rooms
                        dims = room.get('dimensions', {})
                        print(f"   • {room.get('name')}: {dims.get('length')}' x {dims.get('width')}' x {dims.get('height')}'")
                    if len(rooms) > 3:
                        print(f"   ... and {len(rooms) - 3} more rooms")
                
                return True
            else:
                print(f"❌ Geometry generation returned success=false")
                return False
        else:
            print(f"❌ Failed to generate VR geometry: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False

def test_list_projects():
    """Test listing all projects."""
    print_section("Step 6: List All Projects")
    
    try:
        response = requests.get(f"{API_BASE}/projects", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            projects = data.get('projects', [])
            total = data.get('total', 0)
            
            print(f"✅ Retrieved {len(projects)} projects (Total: {total})")
            
            if projects:
                print(f"\n📋 Recent Projects:")
                for project in projects[:5]:
                    print(f"   • #{project.get('id')}: {project.get('name')} ({project.get('status')})")
            
            return True
        else:
            print(f"❌ Failed to list projects: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False

def run_complete_test():
    """Run the complete workflow test."""
    print("\n" + "="*60)
    print("  VR AI CONSTRUCTION PROJECT - COMPLETE WORKFLOW TEST")
    print("="*60)
    print("\nThis test will validate the entire pipeline:")
    print("  1. Backend health check")
    print("  2. AI service availability")
    print("  3. Project generation from prompt")
    print("  4. Database storage verification")
    print("  5. VR geometry generation")
    print("  6. Project listing")
    
    time.sleep(2)
    
    # Test 1: Backend health
    if not test_backend_health():
        print("\n❌ WORKFLOW TEST FAILED: Backend not available")
        return False
    
    time.sleep(1)
    
    # Test 2: AI service status
    if not test_ai_service_status():
        print("\n⚠️  WARNING: AI services not available, but continuing...")
    
    time.sleep(1)
    
    # Test 3: Generate project
    test_prompt = "Modern tiny house, 20 square meters, cedar wood siding, tile roof, floor-to-ceiling windows, lofted sleeping area"
    project_id = test_generate_project(test_prompt, budget=67500, timeline=14)
    
    if not project_id:
        print("\n❌ WORKFLOW TEST FAILED: Could not generate project")
        return False
    
    time.sleep(1)
    
    # Test 4: Verify project in database
    if not test_get_project(project_id):
        print("\n❌ WORKFLOW TEST FAILED: Project not in database")
        return False
    
    time.sleep(1)
    
    # Test 5: Generate VR geometry
    if not test_generate_vr_geometry(project_id):
        print("\n❌ WORKFLOW TEST FAILED: VR geometry generation failed")
        return False
    
    time.sleep(1)
    
    # Test 6: List projects
    if not test_list_projects():
        print("\n⚠️  WARNING: Could not list projects")
    
    # Final summary
    print_section("WORKFLOW TEST COMPLETE")
    print("✅ All tests passed successfully!")
    print(f"\n🎉 Your project (ID: {project_id}) is ready!")
    print(f"\nNext steps:")
    print(f"  1. View in dashboard: http://localhost:3000")
    print(f"  2. Load in VR: Open Construction Quest app on Meta Quest")
    print(f"  3. Use project ID {project_id} to load the house")
    print(f"\nVR API endpoint for Quest:")
    print(f"  GET {API_BASE}/projects/{project_id}/generate-vr")
    
    return True

if __name__ == "__main__":
    try:
        success = run_complete_test()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed with unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
