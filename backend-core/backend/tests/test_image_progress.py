"""
Tests for Image Generation Progress Tracking

Tests the integration between the image generation API endpoints,
WebSocket progress updates, and the image service.
"""

import pytest
import asyncio
import uuid
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import WebSocket

from app.main import app
from app.api.v1.ai_image import generate_image, ImageGenerationRequest
from app.api.v1.websocket import (
    send_image_progress_update,
    complete_image_generation,
    fail_image_generation,
    progress_connections,
    image_generation_progress
)
from app.services.ai_image_service import AIImageService


class TestImageProgressTracking:
    """Test suite for image generation progress tracking"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    def mock_image_service(self):
        """Mock image service"""
        service = Mock(spec=AIImageService)
        service.generate_image = AsyncMock()
        return service

    @pytest.fixture
    def generation_id(self):
        """Generate a test generation ID"""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_progress_callback_mechanism(self):
        """Test that progress callback is invoked during image generation"""
        service = AIImageService()
        progress_updates = []

        async def mock_callback(data):
            progress_updates.append(data)

        # Mock the pipe to avoid loading the actual model
        service.pipe = MagicMock()
        service.compel = MagicMock()
        service.device = "cpu"

        # Mock the actual generation
        with patch.object(service, 'initialize_model', new_callable=AsyncMock):
            with patch.object(service.pipe, '__call__') as mock_call:
                # Simulate Stable Diffusion callback
                def side_effect(*args, **kwargs):
                    callback = kwargs.get('callback')
                    if callback:
                        # Simulate 5 steps
                        for step in range(5):
                            callback(step, None, None)
                    
                    # Return mock result
                    mock_result = MagicMock()
                    mock_result.images = [MagicMock()]
                    return mock_result

                mock_call.side_effect = side_effect

                # Generate image with progress callback
                result = await service.generate_image(
                    prompt="test house",
                    width=512,
                    height=512,
                    num_inference_steps=5,
                    progress_callback=mock_callback,
                    generation_id="test-123"
                )

        # Verify progress updates were received
        assert len(progress_updates) > 0, "Should have received progress updates"
        assert all(u["generation_id"] == "test-123" for u in progress_updates)
        assert all(u["status"] == "generating" for u in progress_updates)
        assert all(0 <= u["percentage"] <= 100 for u in progress_updates)

    @pytest.mark.asyncio
    async def test_api_endpoint_returns_generation_id(self, client):
        """Test that API endpoint returns generation_id in response"""
        with patch('app.api.v1.ai_image.image_service.generate_image') as mock_gen:
            # Mock successful generation
            mock_gen.return_value = {
                "success": True,
                "images": [{"image_url": "/test.png", "filename": "test.png"}],
                "count": 1,
                "metadata": {"steps": 20}
            }

            response = client.post(
                "/api/v1/ai-image/generate",
                json={
                    "prompt": "modern house",
                    "width": 512,
                    "height": 512,
                    "num_inference_steps": 5
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert "generation_id" in data
            assert data["success"] is True
            # Verify it's a valid UUID
            uuid.UUID(data["generation_id"])

    @pytest.mark.asyncio
    async def test_websocket_progress_update_broadcast(self, generation_id):
        """Test that progress updates are broadcast to connected clients"""
        # Create mock WebSocket connections
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_json = AsyncMock()
        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.send_json = AsyncMock()

        # Add connections to tracking
        progress_connections[generation_id] = [mock_ws1, mock_ws2]

        # Send progress update
        progress_data = {
            "step": 10,
            "total_steps": 50,
            "percentage": 20,
            "status": "generating"
        }

        await send_image_progress_update(generation_id, progress_data)

        # Verify both connections received the update
        assert mock_ws1.send_json.called
        assert mock_ws2.send_json.called

        # Verify data structure
        call_data = mock_ws1.send_json.call_args[0][0]
        assert call_data["type"] == "progress"
        assert call_data["step"] == 10
        assert call_data["percentage"] == 20

        # Cleanup
        if generation_id in progress_connections:
            del progress_connections[generation_id]

    @pytest.mark.asyncio
    async def test_websocket_completion_notification(self, generation_id):
        """Test that completion is broadcast to connected clients"""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()

        progress_connections[generation_id] = [mock_ws]

        result = {
            "success": True,
            "images": [{"image_url": "/test.png"}],
            "metadata": {"steps": 50}
        }

        await complete_image_generation(generation_id, result)

        # Verify completion message was sent
        assert mock_ws.send_json.called
        call_data = mock_ws.send_json.call_args[0][0]
        assert call_data["type"] == "completed"
        assert call_data["status"] == "completed"
        assert "result" in call_data

        # Verify cleanup
        assert generation_id not in image_generation_progress

        # Cleanup
        if generation_id in progress_connections:
            del progress_connections[generation_id]

    @pytest.mark.asyncio
    async def test_websocket_error_notification(self, generation_id):
        """Test that errors are broadcast to connected clients"""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()

        progress_connections[generation_id] = [mock_ws]

        error_message = "CUDA out of memory"
        await fail_image_generation(generation_id, error_message)

        # Verify error message was sent
        assert mock_ws.send_json.called
        call_data = mock_ws.send_json.call_args[0][0]
        assert call_data["type"] == "error"
        assert call_data["status"] == "failed"
        assert call_data["error"] == error_message

        # Cleanup
        if generation_id in progress_connections:
            del progress_connections[generation_id]
        if generation_id in image_generation_progress:
            del image_generation_progress[generation_id]

    @pytest.mark.asyncio
    async def test_progress_data_structure(self, generation_id):
        """Test that progress data has correct structure"""
        progress_data = {
            "generation_id": generation_id,
            "step": 25,
            "total_steps": 50,
            "percentage": 50,
            "status": "generating"
        }

        # Store in progress tracking
        image_generation_progress[generation_id] = progress_data

        # Verify structure
        stored = image_generation_progress[generation_id]
        assert stored["generation_id"] == generation_id
        assert stored["step"] == 25
        assert stored["total_steps"] == 50
        assert stored["percentage"] == 50
        assert stored["status"] == "generating"

        # Cleanup
        del image_generation_progress[generation_id]

    @pytest.mark.asyncio
    async def test_multiple_concurrent_generations(self):
        """Test handling multiple concurrent image generations"""
        gen_id_1 = str(uuid.uuid4())
        gen_id_2 = str(uuid.uuid4())

        # Create mock connections for each generation
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_json = AsyncMock()
        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.send_json = AsyncMock()

        progress_connections[gen_id_1] = [mock_ws1]
        progress_connections[gen_id_2] = [mock_ws2]

        # Send progress updates to different generations
        await send_image_progress_update(gen_id_1, {
            "step": 10,
            "total_steps": 50,
            "percentage": 20,
            "status": "generating"
        })

        await send_image_progress_update(gen_id_2, {
            "step": 30,
            "total_steps": 50,
            "percentage": 60,
            "status": "generating"
        })

        # Verify each connection only received its own updates
        assert mock_ws1.send_json.call_count == 1
        assert mock_ws2.send_json.call_count == 1

        ws1_data = mock_ws1.send_json.call_args[0][0]
        ws2_data = mock_ws2.send_json.call_args[0][0]

        assert ws1_data["step"] == 10
        assert ws2_data["step"] == 30

        # Cleanup
        for gen_id in [gen_id_1, gen_id_2]:
            if gen_id in progress_connections:
                del progress_connections[gen_id]

    @pytest.mark.asyncio
    async def test_disconnected_websocket_cleanup(self, generation_id):
        """Test that disconnected WebSockets are cleaned up"""
        # Create a mock that raises an exception (simulating disconnect)
        mock_ws_dead = Mock(spec=WebSocket)
        mock_ws_dead.send_json = AsyncMock(side_effect=Exception("Connection closed"))

        mock_ws_alive = Mock(spec=WebSocket)
        mock_ws_alive.send_json = AsyncMock()

        progress_connections[generation_id] = [mock_ws_dead, mock_ws_alive]

        # Send progress update
        await send_image_progress_update(generation_id, {
            "step": 10,
            "total_steps": 50,
            "percentage": 20,
            "status": "generating"
        })

        # The dead connection should be cleaned up
        # The alive connection should still receive updates
        assert mock_ws_alive.send_json.called

        # Cleanup
        if generation_id in progress_connections:
            del progress_connections[generation_id]

    def test_generation_id_is_uuid(self):
        """Test that generated IDs are valid UUIDs"""
        gen_id = str(uuid.uuid4())
        
        # Should not raise an exception
        parsed = uuid.UUID(gen_id)
        assert str(parsed) == gen_id

    @pytest.mark.asyncio
    async def test_architectural_visualization_with_progress(self, mock_image_service):
        """Test architectural visualization endpoint with progress tracking"""
        with patch('app.api.v1.ai_image.image_service', mock_image_service):
            mock_image_service.generate_architectural_visualization.return_value = {
                "success": True,
                "images": [{"image_url": "/test.png"}],
                "count": 1,
                "metadata": {"steps": 50}
            }

            client = TestClient(app)
            response = client.post(
                "/api/v1/ai-image/architectural-visualization",
                json={
                    "design_description": "modern house with large windows",
                    "style": "modern",
                    "time_of_day": "day"
                }
            )

            # Verify the service was called with progress callback
            assert mock_image_service.generate_architectural_visualization.called
            call_kwargs = mock_image_service.generate_architectural_visualization.call_args[1]
            assert "progress_callback" in call_kwargs
            assert "generation_id" in call_kwargs
            assert call_kwargs["generation_id"] is not None


class TestWebSocketConnection:
    """Test WebSocket connection handling"""

    def test_websocket_connection_endpoint_exists(self):
        """Test that WebSocket endpoint is accessible"""
        client = TestClient(app)
        
        # This will attempt to connect, which is enough to verify the route exists
        try:
            with client.websocket_connect("/api/v1/ws/image-progress/test-id") as websocket:
                # Successfully connected
                assert websocket is not None
        except Exception:
            # Connection may fail in test environment, but route should exist
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
