import pytest
import asyncio
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.api.v1.websocket import progress_connections, image_generation_progress

class TestImageProgressTracking:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Reset global state between tests."""
        yield
        progress_connections.clear()
        image_generation_progress.clear()

    @pytest.mark.asyncio
    async def test_progress_callback_mechanism(self):
        """Verify the service triggers the callback during the SD loop."""
        from app.services.ai_image_service import AIImageService
        service = AIImageService()
        progress_updates = []

        async def mock_callback(data):
            progress_updates.append(data)

        # Mock core attributes
        service.pipe = MagicMock()
        service.tokenizer = MagicMock()
        # Mocking short prompt (3 tokens) to ensure the standard path is tested
        service.tokenizer.encode.return_value = [1, 2, 3] 
        service.device = "cpu"

        def sd_loop_side_effect(*args, **kwargs):
            callback = kwargs.get('callback')
            if callback:
                # Diffusers triggers callback per step
                for step in range(5):
                    callback(step, None, None)

            mock_res = MagicMock()
            mock_res.images = [Image.new('RGB', (10, 10), color='red')]
            return mock_res

        # patch.object on __call__ of a MagicMock does NOT intercept instance
        # calls (Python looks up magic methods on the type, not the instance).
        # Set side_effect directly on the mock instead.
        service.pipe.side_effect = sd_loop_side_effect

        with patch.object(service, 'initialize_model', new_callable=AsyncMock):
            await service.generate_image(
                prompt="test",
                num_inference_steps=5,
                progress_callback=mock_callback,
                generation_id="test-gen-id"
            )

        # FIX: asyncio.ensure_future needs a tick of the event loop to run.
        # We use a small sleep to ensure all 5 callbacks are processed.
        await asyncio.sleep(0.05)

        assert len(progress_updates) == 5, f"Expected 5 updates, got {len(progress_updates)}"
        
        # With the (step + 1) logic:
        # Step 0: (1/5) * 100 = 20%
        # Step 4: (5/5) * 100 = 100%
        assert progress_updates[0]["percentage"] == 20
        assert progress_updates[-1]["percentage"] == 100
        assert all(u["status"] == "generating" for u in progress_updates)

    def test_api_endpoint_returns_generation_id(self, client):
        """Verify POST /generate returns 202 and a valid UUID."""
        target_url = "/api/v1/image/generate" 
        
        with patch('app.api.v1.ai_image.image_service') as mock_service:
            # We don't await here because TestClient is synchronous
            mock_service.generate_image = AsyncMock()

            response = client.post(
                target_url,
                json={"prompt": "modern house", "num_inference_steps": 5}
            )

            assert response.status_code == 202
            data = response.json()
            assert "generation_id" in data
            uuid.UUID(data["generation_id"])

    def test_architectural_visualization_with_progress(self, client):
        """Verify the visualization wrapper returns 202."""
        target_url = "/api/v1/image/architectural-visualization"
        
        with patch('app.api.v1.ai_image.image_service') as mock_service:
            mock_service.generate_architectural_visualization = AsyncMock()
            response = client.post(
                target_url,
                json={"design_description": "glass villa", "style": "modern"}
            )
            assert response.status_code == 202