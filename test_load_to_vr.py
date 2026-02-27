#!/usr/bin/env python3
"""
Test script to diagnose "Load to VR" button image generation issue.
"""
import requests
import json
import time

BASE_URL = "http://192.168.7.249:8000/api/v1"

def test_backend_health():
    """Test if backend is running."""
    print("=" * 60)
    print("1. Testing Backend Health")
    print("=" * 60)
    try:
        response = requests.get(f"{BASE_URL.replace('/api/v1', '')}/health", timeout=5)
        print(f"✅ Backend is running: {response.status_code}")
        print(f"   Response: {response.json()}")
        return True
    except Exception as e:
        print(f"❌ Backend health check failed: {e}")
        return False

def test_get_projects():
    """Get list of projects."""
    print("\n" + "=" * 60)
    print("2. Testing Get Projects")
    print("=" * 60)
    try:
        response = requests.get(f"{BASE_URL}/projects", timeout=10)
        print(f"✅ Projects endpoint: {response.status_code}")
        data = response.json()
        projects = data.get('projects', [])
        print(f"   Found {len(projects)} projects")
        if projects:
            for p in projects[:3]:
                print(f"   - ID: {p['id']}, Name: {p['name']}")
        return projects[0]['id'] if projects else None
    except Exception as e:
        print(f"❌ Get projects failed: {e}")
        return None

def test_load_to_vr(project_id):
    """Test the Load to VR endpoint."""
    print("\n" + "=" * 60)
    print(f"3. Testing Load to VR (Project ID: {project_id})")
    print("=" * 60)
    try:
        response = requests.post(
            f"{BASE_URL}/projects/{project_id}/load-to-vr",
            json={},
            timeout=15
        )
        print(f"✅ Load to VR endpoint: {response.status_code}")
        data = response.json()
        print(f"   Response: {json.dumps(data, indent=2)}")
        
        if data.get('success'):
            print(f"\n   🎉 Success! Generation ID: {data.get('generation_id')}")
            print(f"   📡 WebSocket URL: {data.get('websocket_url')}")
            return data.get('generation_id')
        else:
            print(f"   ⚠️  Request completed but success=False")
            return None
    except requests.exceptions.Timeout:
        print(f"❌ Request timed out after 15 seconds")
        return None
    except Exception as e:
        print(f"❌ Load to VR failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Status: {e.response.status_code}")
            print(f"   Response: {e.response.text}")
        return None

def check_image_generation_status(generation_id):
    """Check if image generation actually started."""
    print("\n" + "=" * 60)
    print(f"4. Checking Image Generation Status")
    print("=" * 60)
    # Wait a moment for background task to start
    time.sleep(2)
    print(f"   Generation ID: {generation_id}")
    print(f"   ⏳ Image generation should be running in background...")
    print(f"   💡 Check backend logs for image generation progress")

def main():
    print("\n" + "=" * 60)
    print("VR AI Construction - Load to VR Diagnostic Test")
    print("=" * 60)
    
    # Test 1: Backend health
    if not test_backend_health():
        print("\n❌ Backend is not running. Please start it first.")
        return
    
    # Test 2: Get projects
    project_id = test_get_projects()
    if not project_id:
        print("\n❌ No projects found. Please create a project first.")
        return
    
    # Test 3: Load to VR
    generation_id = test_load_to_vr(project_id)
    
    # Test 4: Check status
    if generation_id:
        check_image_generation_status(generation_id)
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\n💡 If image generation isn't working:")
        print("   1. Check backend logs: tail -f backend-core/backend/*.log")
        print("   2. Verify Stable Diffusion/Ollama is installed")
        print("   3. Check generated_images/ directory for new files")
        print("   4. Monitor backend process logs in terminal")
    else:
        print("\n" + "=" * 60)
        print("❌ TESTS FAILED")
        print("=" * 60)
        print("\n🔍 Troubleshooting:")
        print("   1. Verify backend is running on port 8000")
        print("   2. Check API base URL in frontend .env")
        print("   3. Review backend logs for errors")
        print("   4. Ensure database has projects")

if __name__ == "__main__":
    main()
