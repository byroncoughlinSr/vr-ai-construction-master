import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import base64
from io import BytesIO
from PIL import Image

from app.services.ai_image_service import AIImageService


@pytest.mark.asyncio
class TestAIImageService:
    """Unit tests for AI Image Service."""

    @pytest.fixture
    def service(self):
        """Create a service instance for testing."""
        return AIImageService()

    @pytest.fixture
    def mock_pipeline(self):
        """Create a mock Stable Diffusion pipeline."""
        mock_pipe = MagicMock()
        mock_image = MagicMock()
        mock_pipe.return_value = MagicMock(images=[mock_image])
        return mock_pipe

    @pytest.fixture
    def sample_image(self):
        """Create a sample PIL Image for testing."""
        # Create a small test image
        img = Image.new('RGB', (100, 100), color='red')
        return img

    def test_initialization(self, service):
        """Test service initialization."""
        assert service.pipe is None
        assert service.device in ["cuda", "cpu"]

    @patch('torch.cuda.is_available')
    @patch('app.services.ai_image_service.StableDiffusionPipeline.from_pretrained')
    async def test_initialize_model_cuda(self, mock_from_pretrained, mock_cuda_available, service, mock_pipeline):
        """Test model initialization with CUDA."""
        mock_cuda_available.return_value = True
        mock_from_pretrained.return_value = mock_pipeline

        await service.initialize_model()

        assert service.pipe is not None
        mock_from_pretrained.assert_called_once()
        # Should be moved to cuda device
        mock_pipeline.to.assert_called_with("cuda")

    @patch('torch.cuda.is_available')
    @patch('app.services.ai_image_service.StableDiffusionPipeline.from_pretrained')
    async def test_initialize_model_cpu(self, mock_from_pretrained, mock_cuda_available, service, mock_pipeline):
        """Test model initialization with CPU."""
        mock_cuda_available.return_value = False
        mock_from_pretrained.return_value = mock_pipeline

        await service.initialize_model()

        assert service.pipe is not None
        mock_from_pretrained.assert_called_once()
        # Should be moved to cpu device
        mock_pipeline.to.assert_called_with("cpu")

    @patch('torch.cuda.is_available')
    @patch('app.services.ai_image_service.StableDiffusionPipeline.from_pretrained')
    async def test_initialize_model_failure(self, mock_from_pretrained, mock_cuda_available, service):
        """Test model initialization failure."""
        mock_cuda_available.return_value = True
        mock_from_pretrained.side_effect = Exception("Model load failed")

        with pytest.raises(Exception, match="Model load failed"):
            await service.initialize_model()

        assert service.pipe is None

    @patch('app.services.ai_image_service.settings')
    @patch('torch.no_grad')
    async def test_generate_image_success(self, mock_no_grad, mock_settings, service, sample_image):
        """Test successful image generation."""
        # Setup mocks
        service.pipe = MagicMock()
        service.pipe.return_value = MagicMock(images=[sample_image])

        mock_settings.generated_images_dir = "/tmp/test_images"

        # Mock torch.no_grad context manager
        mock_no_grad.return_value.__enter__ = MagicMock()
        mock_no_grad.return_value.__exit__ = MagicMock()

        # Mock Path and file operations
        with patch('pathlib.Path.mkdir'), \
             patch('pathlib.Path.__truediv__') as mock_truediv, \
             patch('asyncio.get_event_loop') as mock_loop:

            mock_loop.return_value.time.return_value = 1234567890.0
            mock_filepath = MagicMock()
            mock_truediv.return_value = mock_filepath

            result = await service.generate_image(
                prompt="test prompt",
                negative_prompt="test negative",
                width=256,
                height=256,
                num_inference_steps=10,
                guidance_scale=5.0
            )

            assert result["success"] is True
            assert "image_data" in result
            assert "image_url" in result
            assert "metadata" in result
            assert result["metadata"]["prompt"] == "test prompt"
            assert result["metadata"]["negative_prompt"] == "test negative"

    @patch('torch.no_grad')
    async def test_generate_image_failure(self, mock_no_grad, service):
        """Test image generation failure."""
        # Setup mocks
        service.pipe = MagicMock()
        service.pipe.side_effect = Exception("Generation failed")

        # Mock torch.no_grad context manager
        mock_no_grad.return_value.__enter__ = MagicMock()
        mock_no_grad.return_value.__exit__ = MagicMock()

        result = await service.generate_image(prompt="test prompt")

        assert result["success"] is False
        assert "error" in result
        assert result["error"] == "Generation failed"

    async def test_generate_image_default_negative_prompt(self, service):
        """Test that default negative prompt is used when none provided."""
        service.pipe = MagicMock()
        service.pipe.return_value = MagicMock(images=[Image.new('RGB', (10, 10))])

        with patch('torch.no_grad'), \
             patch('pathlib.Path.mkdir'), \
             patch('pathlib.Path.__truediv__'), \
             patch('asyncio.get_event_loop'):

            result = await service.generate_image(prompt="test prompt", negative_prompt=None)

            # Check that pipe was called with default negative prompt
            call_args = service.pipe.call_args
            assert "negative_prompt" in call_args.kwargs
            assert "blurry" in call_args.kwargs["negative_prompt"]

    async def test_generate_architectural_visualization(self, service):
        """Test architectural visualization generation."""
        service.pipe = MagicMock()
        service.pipe.return_value = MagicMock(images=[Image.new('RGB', (10, 10))])

        with patch('torch.no_grad'), \
             patch('pathlib.Path.mkdir'), \
             patch('pathlib.Path.__truediv__'), \
             patch('asyncio.get_event_loop'):

            result = await service.generate_architectural_visualization(
                design_description="a modern house",
                style="contemporary",
                time_of_day="sunset"
            )

            assert result["success"] is True
            # Check that the prompt contains expected elements
            call_args = service.pipe.call_args
            prompt = call_args.kwargs["prompt"]
            assert "modern house" in prompt
            assert "contemporary style" in prompt
            assert "sunset lighting" in prompt
            assert "architectural visualization" in prompt

    async def test_generate_image_base64_encoding(self, service):
        """Test that generated images are properly base64 encoded."""
        service.pipe = MagicMock()
        red_image = Image.new('RGB', (10, 10), color='red')
        service.pipe.return_value = MagicMock(images=[red_image])

        with patch('torch.no_grad'), \
             patch('pathlib.Path.mkdir'), \
             patch('pathlib.Path.__truediv__'), \
             patch('asyncio.get_event_loop'):

            result = await service.generate_image(prompt="test")

            # Decode the base64 to verify it's valid image data
            image_data = base64.b64decode(result["image_data"])
            # Should be able to create image from the decoded data
            decoded_image = Image.open(BytesIO(image_data))
            assert decoded_image.size == (10, 10)
