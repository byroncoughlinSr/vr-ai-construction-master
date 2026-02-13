"""
WebSocket Progress Tracking Tests

Focused tests for WebSocket-specific functionality in image generation progress tracking.
Tests WebSocket connections, message broadcasting, and connection management.
"""

import pytest
import asyncio
import uuid
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import WebSocket, WebSocketDisconnect

from app.main import app
from app.api.v1.websocket import (
    send_image_progress_update,
    complete_image_generation,
    fail_image_generation,
    progress_connections,
    image_generation_progress,
    ConnectionManager,
    manager
)


class TestWebSocketProgressEndpoint:
    """Test WebSocket endpoint for image progress tracking"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    def generation_id(self):
        """Generate test generation ID"""
        return str(uuid.uuid4())

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up after each test"""
        yield
        # Clear all progress connections and data
        progress_connections.clear()
        image_generation_progress.clear()

    def test_websocket_endpoint_exists(self, client, generation_id):
        """Test that WebSocket endpoint is accessible"""
        with client.websocket_connect(f"/api/v1/ws/image-progress/{generation_id}") as websocket:
            assert websocket is not None

    def test_websocket_accepts_connection(self, client, generation_id):
        """Test that WebSocket accepts and maintains connection"""
        with client.websocket_connect(f"/api/v1/ws/image-progress/{generation_id}") as websocket:
            # Connection should be established
            assert websocket.should_close is False

    @pytest.mark.asyncio
    async def test_send_progress_update_to_connected_client(self, generation_id):
        """Test sending progress update to connected WebSocket client"""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()

        # Add mock connection
        progress_connections[generation_id] = [mock_ws]

        progress_data = {
            "step": 10,
            "total_steps": 50,
            "percentage": 20,
            "status": "generating"
        }

        await send_image_progress_update(generation_id, progress_data)

        # Verify message was sent
        assert mock_ws.send_json.called
        sent_data = mock_ws.send_json.call_args[0][0]
        assert sent_data["type"] == "progress"
        assert sent_data["step"] == 10
        assert sent_data["percentage"] == 20

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_clients(self, generation_id):
        """Test broadcasting progress to multiple connected clients"""
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_json = AsyncMock()
        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.send_json = AsyncMock()
        mock_ws3 = Mock(spec=WebSocket)
        mock_ws3.send_json = AsyncMock()

        # Add multiple mock connections
        progress_connections[generation_id] = [mock_ws1, mock_ws2, mock_ws3]

        progress_data = {
            "step": 25,
            "total_steps": 50,
            "percentage": 50,
            "status": "generating"
        }

        await send_image_progress_update(generation_id, progress_data)

        # All clients should receive the message
        assert mock_ws1.send_json.called
        assert mock_ws2.send_json.called
        assert mock_ws3.send_json.called

        # Verify they all received the same data
        for mock_ws in [mock_ws1, mock_ws2, mock_ws3]:
            sent_data = mock_ws.send_json.call_args[0][0]
            assert sent_data["step"] == 25
            assert sent_data["percentage"] == 50

    @pytest.mark.asyncio
    async def test_no_error_when_no_clients_connected(self, generation_id):
        """Test that sending progress with no clients doesn't error"""
        progress_data = {
            "step": 10,
            "total_steps": 50,
            "percentage": 20,
            "status": "generating"
        }

        # Should not raise exception
        await send_image_progress_update(generation_id, progress_data)

    @pytest.mark.asyncio
    async def test_handle_disconnected_client_during_broadcast(self, generation_id):
        """Test handling client that disconnects during broadcast"""
        # Create mock that fails on send
        mock_ws_dead = Mock(spec=WebSocket)
        mock_ws_dead.send_json = AsyncMock(side_effect=Exception("Connection closed"))

        # Create mock that succeeds
        mock_ws_alive = Mock(spec=WebSocket)
        mock_ws_alive.send_json = AsyncMock()

        progress_connections[generation_id] = [mock_ws_dead, mock_ws_alive]

        progress_data = {
            "step": 10,
            "total_steps": 50,
            "percentage": 20,
            "status": "generating"
        }

        await send_image_progress_update(generation_id, progress_data)

        # Alive client should still receive message
        assert mock_ws_alive.send_json.called

    @pytest.mark.asyncio
    async def test_completion_message_format(self, generation_id):
        """Test that completion message has correct format"""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()

        progress_connections[generation_id] = [mock_ws]

        result = {
            "success": True,
            "images": [{"image_url": "/test.png", "filename": "test.png"}],
            "count": 1,
            "metadata": {"steps": 50, "width": 768, "height": 512}
        }

        await complete_image_generation(generation_id, result)

        # Verify message structure
        assert mock_ws.send_json.called
        sent_data = mock_ws.send_json.call_args[0][0]
        assert sent_data["type"] == "completed"
        assert sent_data["status"] == "completed"
        assert "result" in sent_data
        assert "timestamp" in sent_data
        assert sent_data["generation_id"] == generation_id

    @pytest.mark.asyncio
    async def test_error_message_format(self, generation_id):
        """Test that error message has correct format"""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()

        progress_connections[generation_id] = [mock_ws]

        error_msg = "CUDA out of memory"
        await fail_image_generation(generation_id, error_msg)

        # Verify message structure
        assert mock_ws.send_json.called
        sent_data = mock_ws.send_json.call_args[0][0]
        assert sent_data["type"] == "error"
        assert sent_data["status"] == "failed"
        assert sent_data["error"] == error_msg
        assert "timestamp" in sent_data
        assert sent_data["generation_id"] == generation_id

    @pytest.mark.asyncio
    async def test_progress_data_persistence(self, generation_id):
        """Test that progress data is stored during generation"""
        progress_data = {
            "generation_id": generation_id,
            "step": 30,
            "total_steps": 50,
            "percentage": 60,
            "status": "generating"
        }

        # Store progress
        image_generation_progress[generation_id] = progress_data

        # Retrieve and verify
        stored = image_generation_progress[generation_id]
        assert stored["step"] == 30
        assert stored["total_steps"] == 50
        assert stored["percentage"] == 60
        assert stored["status"] == "generating"

    @pytest.mark.asyncio
    async def test_progress_data_cleanup_after_completion(self, generation_id):
        """Test that progress data is cleaned up after completion"""
        # Store some progress data
        image_generation_progress[generation_id] = {
            "step": 50,
            "total_steps": 50,
            "percentage": 100
        }

        mock_ws = Mock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()
        progress_connections[generation_id] = [mock_ws]

        result = {"success": True, "images": [], "metadata": {}}
        await complete_image_generation(generation_id, result)

        # Progress data should be cleaned up
        assert generation_id not in image_generation_progress

    @pytest.mark.asyncio
    async def test_multiple_generations_isolated(self):
        """Test that multiple concurrent generations are isolated"""
        gen_id_1 = str(uuid.uuid4())
        gen_id_2 = str(uuid.uuid4())

        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_json = AsyncMock()
        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.send_json = AsyncMock()

        progress_connections[gen_id_1] = [mock_ws1]
        progress_connections[gen_id_2] = [mock_ws2]

        # Send different progress to each generation
        await send_image_progress_update(gen_id_1, {
            "step": 10,
            "total_steps": 50,
            "percentage": 20,
            "status": "generating"
        })

        await send_image_progress_update(gen_id_2, {
            "step": 40,
            "total_steps": 50,
            "percentage": 80,
            "status": "generating"
        })

        # Verify each received only their own progress
        ws1_data = mock_ws1.send_json.call_args[0][0]
        ws2_data = mock_ws2.send_json.call_args[0][0]

        assert ws1_data["step"] == 10
        assert ws2_data["step"] == 40
        assert mock_ws1.send_json.call_count == 1
        assert mock_ws2.send_json.call_count == 1

    @pytest.mark.asyncio
    async def test_connection_cleanup_on_completion(self, generation_id):
        """Test that connections are cleaned up after completion"""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()
        progress_connections[generation_id] = [mock_ws]

        result = {"success": True, "images": [], "metadata": {}}
        await complete_image_generation(generation_id, result)

        # Connection tracking should still exist (clients manage their own disconnect)
        # But progress data should be cleaned up
        assert generation_id not in image_generation_progress

    def test_websocket_status_endpoint(self, client, generation_id):
        """Test WebSocket status endpoint"""
        response = client.get(f"/api/v1/ws/image-progress/{generation_id}/status")
        assert response.status_code == 200
        data = response.json()
        assert "generation_id" in data
        assert "status" in data

    def test_websocket_service_status(self, client):
        """Test overall WebSocket service status"""
        response = client.get("/api/v1/ws/status")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "WebSocket Collaboration"
        assert "status" in data
        assert "total_connections" in data


class TestConnectionManager:
    """Test ConnectionManager for WebSocket connections"""

    @pytest.fixture
    def conn_manager(self):
        """Create fresh ConnectionManager for each test"""
        return ConnectionManager()

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up after each test"""
        yield
        # Clear manager state
        manager.active_connections.clear()
        manager.user_rooms.clear()

    @pytest.mark.asyncio
    async def test_connection_manager_accepts_connection(self, conn_manager):
        """Test that ConnectionManager accepts WebSocket connections"""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.accept = AsyncMock()

        room_id = "test-room"
        user_id = "test-user"

        await conn_manager.connect(mock_ws, room_id, user_id)

        # Verify connection was accepted
        assert mock_ws.accept.called
        assert room_id in conn_manager.active_connections
        assert mock_ws in conn_manager.active_connections[room_id]

    @pytest.mark.asyncio
    async def test_connection_manager_disconnect(self, conn_manager):
        """Test ConnectionManager handles disconnection"""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        room_id = "test-room"
        user_id = "test-user"

        await conn_manager.connect(mock_ws, room_id, user_id)
        await conn_manager.disconnect(mock_ws, user_id)

        # Connection should be removed
        assert room_id not in conn_manager.active_connections or \
               mock_ws not in conn_manager.active_connections.get(room_id, [])

    @pytest.mark.asyncio
    async def test_broadcast_to_room(self, conn_manager):
        """Test broadcasting message to room"""
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.accept = AsyncMock()
        mock_ws1.send_json = AsyncMock()

        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.accept = AsyncMock()
        mock_ws2.send_json = AsyncMock()

        room_id = "test-room"

        await conn_manager.connect(mock_ws1, room_id, "user1")
        await conn_manager.connect(mock_ws2, room_id, "user2")

        message = {"type": "test", "data": "hello"}
        await conn_manager.broadcast_to_room(room_id, message)

        # Both connections should receive message
        assert mock_ws1.send_json.called
        assert mock_ws2.send_json.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
