# Testing Guide - Image Generation Progress Tracking

This document explains how to run tests for the image generation progress tracking feature.

---

## Backend Tests (Python/pytest)

### Prerequisites

```bash
cd backend-core/backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov
```

### Running Tests

#### Run all image progress tests:
```bash
pytest tests/test_image_progress.py -v
```

#### Run with coverage report:
```bash
pytest tests/test_image_progress.py --cov=app.api.v1 --cov=app.services --cov-report=html
```

#### Run specific test:
```bash
pytest tests/test_image_progress.py::TestImageProgressTracking::test_progress_callback_mechanism -v
```

#### Run all tests:
```bash
pytest tests/ -v
```

### Test Coverage

The backend tests cover:
- ✅ Progress callback mechanism
- ✅ API endpoint returns generation_id
- ✅ WebSocket progress update broadcast
- ✅ WebSocket completion notification
- ✅ WebSocket error notification
- ✅ Progress data structure validation
- ✅ Multiple concurrent generations
- ✅ Disconnected WebSocket cleanup
- ✅ UUID generation validation
- ✅ Architectural visualization with progress

### Expected Output

```
tests/test_image_progress.py::TestImageProgressTracking::test_progress_callback_mechanism PASSED
tests/test_image_progress.py::TestImageProgressTracking::test_api_endpoint_returns_generation_id PASSED
tests/test_image_progress.py::TestImageProgressTracking::test_websocket_progress_update_broadcast PASSED
...

==================== 13 passed in 2.45s ====================
```

---

## Frontend Tests (TypeScript/Vitest)

### Prerequisites

```bash
cd backend-core/dashboard
npm install
# or
yarn install
```

### Running Tests

#### Run all tests:
```bash
npm run test
# or
yarn test
```

#### Run in watch mode:
```bash
npm run test:watch
# or
yarn test:watch
```

#### Run with coverage:
```bash
npm run test:coverage
# or
yarn test:coverage
```

#### Run specific test file:
```bash
npm run test -- src/services/__tests__/imageProgress.spec.ts
```

### Test Coverage

The frontend tests cover:
- ✅ WebSocket connection with correct URL
- ✅ Custom WebSocket base URL
- ✅ Progress message handling
- ✅ Completion message handling
- ✅ Error message handling
- ✅ Ping/pong message handling
- ✅ Malformed JSON handling
- ✅ WebSocket disconnection
- ✅ Callback cleanup
- ✅ Connection status checking
- ✅ Ping functionality
- ✅ Automatic reconnection on abnormal closure
- ✅ No reconnection on normal closure
- ✅ Reconnection attempt limits
- ✅ Auto-disconnect after completion
- ✅ Auto-disconnect after error

### Expected Output

```
 ✓ src/services/__tests__/imageProgress.spec.ts (22)
   ✓ ImageProgressService (22)
     ✓ connect (7)
       ✓ should create WebSocket connection with correct URL
       ✓ should accept custom WebSocket base URL
       ✓ should handle progress messages
       ✓ should handle completion messages
       ✓ should handle error messages
       ✓ should respond to ping messages with pong
       ✓ should handle malformed JSON gracefully
     ✓ disconnect (3)
     ✓ isConnected (3)
     ✓ ping (2)
     ✓ reconnection (3)
     ✓ auto-disconnect (2)

Test Files  1 passed (1)
     Tests  22 passed (22)
```

---

## Integration Testing

### Manual End-to-End Test

1. **Start the backend:**
   ```bash
   cd backend-core/backend
   python -m uvicorn app.main:app --reload
   ```

2. **Open test page in browser:**
   ```
   http://localhost:8000/api/v1/ws/image-progress/test/test-id
   ```

3. **Click "Start Image Generation"** and observe real-time progress updates

4. **Verify:**
   - Progress bar updates smoothly
   - Step counter increments (e.g., 1/50, 2/50, etc.)
   - Percentage increases from 0% to 100%
   - Image appears when complete
   - Error handling works if generation fails

### API Testing with cURL

```bash
# Generate image and capture generation_id
curl -X POST http://localhost:8000/api/v1/ai-image/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "modern house with large windows",
    "width": 512,
    "height": 512,
    "num_inference_steps": 20
  }' | jq '.generation_id'

# Connect to WebSocket in browser console:
# const ws = new WebSocket('ws://localhost:8000/api/v1/ws/image-progress/YOUR_GEN_ID');
# ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

### WebSocket Testing with websocat

```bash
# Install websocat (WebSocket client)
# On macOS: brew install websocat
# On Linux: cargo install websocat

# Connect to progress WebSocket
websocat ws://localhost:8000/api/v1/ws/image-progress/test-id
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Test Image Progress Feature

on: [push, pull_request]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          cd backend-core/backend
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov
      - name: Run tests
        run: |
          cd backend-core/backend
          pytest tests/test_image_progress.py -v --cov

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      - name: Install dependencies
        run: |
          cd backend-core/dashboard
          npm install
      - name: Run tests
        run: |
          cd backend-core/dashboard
          npm run test:coverage
```

---

## Troubleshooting

### Backend Test Issues

**Issue:** `ModuleNotFoundError: No module named 'app'`
```bash
# Solution: Install package in development mode
cd backend-core/backend
pip install -e .
```

**Issue:** Tests hang or timeout
```bash
# Solution: Use pytest timeout plugin
pip install pytest-timeout
pytest tests/test_image_progress.py --timeout=30
```

**Issue:** WebSocket import errors
```bash
# Solution: Ensure FastAPI and websockets are installed
pip install 'fastapi[all]' websockets
```

### Frontend Test Issues

**Issue:** `ReferenceError: WebSocket is not defined`
```bash
# Solution: Add jsdom environment to vitest.config.ts
export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true
  }
})
```

**Issue:** TypeScript errors in tests
```bash
# Solution: Update types
npm install -D @types/node @vitest/ui
```

**Issue:** Tests fail with "Cannot find module"
```bash
# Solution: Check path aliases in vite.config.ts and tsconfig.json
```

---

## Performance Testing

### Load Testing WebSocket Connections

```python
# test_load.py
import asyncio
import websockets
import json
from concurrent.futures import ThreadPoolExecutor

async def connect_and_listen(generation_id, num):
    uri = f"ws://localhost:8000/api/v1/ws/image-progress/{generation_id}"
    async with websockets.connect(uri) as websocket:
        print(f"Connection {num} established")
        async for message in websocket:
            data = json.loads(message)
            print(f"Connection {num} received: {data['type']}")

async def load_test(num_connections=10):
    tasks = []
    for i in range(num_connections):
        gen_id = f"test-{i}"
        tasks.append(connect_and_listen(gen_id, i))
    
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(load_test(50))  # Test 50 concurrent connections
```

### Running Load Test

```bash
python test_load.py
```

---

## Test Data

### Sample Progress Message

```json
{
  "type": "progress",
  "generation_id": "550e8400-e29b-41d4-a716-446655440000",
  "step": 25,
  "total_steps": 50,
  "percentage": 50,
  "status": "generating"
}
```

### Sample Completion Message

```json
{
  "type": "completed",
  "generation_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result": {
    "success": true,
    "images": [
      {
        "image_url": "/generated_images/generated_1675789123456_0.png",
        "filename": "generated_1675789123456_0.png"
      }
    ],
    "metadata": {
      "steps": 50,
      "width": 768,
      "height": 512
    }
  },
  "timestamp": "2026-02-07T14:10:00Z"
}
```

### Sample Error Message

```json
{
  "type": "error",
  "generation_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "error": "CUDA out of memory",
  "timestamp": "2026-02-07T14:10:00Z"
}
```

---

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [Vitest Documentation](https://vitest.dev/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [WebSocket Testing Guide](https://websockets.readthedocs.io/en/stable/intro/tutorial2.html)

---

**Last Updated:** February 7, 2026
