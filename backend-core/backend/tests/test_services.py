import pytest
import asyncio
import base64
import io
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from PIL import Image
from app.services.ai_image_service import AIImageService

@pytest.mark.asyncio
class TestAIImageService:
    """Consolidated unit tests for AI Image Service."""

    @pytest.fixture
    def service(self):
        return AIImageService()

    @pytest.fixture
    def mock_pipe_obj(self):
        """Mocks the StableDiffusionPipeline with chaining support for .to()"""
        pipe = MagicMock()
        pipe.to.return_value = pipe
        mock_result = MagicMock()
        mock_result.images = [Image.new('RGB', (10, 10), color='red')]
        pipe.return_value = mock_result
        pipe.tokenizer = MagicMock()
        pipe.text_encoder = MagicMock()
        return pipe

    @patch('app.services.ai_image_service.torch.cuda.is_available')
    @patch('app.services.ai_image_service.StableDiffusionPipeline.from_pretrained')
    @patch('app.services.ai_image_service.Compel')
    @patch('app.services.ai_image_service.CLIPTokenizer.from_pretrained')
    async def test_initialize_model_cuda(self, mock_clip, mock_compel, mock_sd_from_pretrained, mock_cuda, service, mock_pipe_obj):
        """Test initialization logic with CUDA."""
        # Fix: Overwrite the device set during __init__ to simulate CUDA environment
        service.device = "cuda" 
        mock_sd_from_pretrained.return_value = mock_pipe_obj
        
        await service.initialize_model()
        
        assert service.pipe is not None
        mock_pipe_obj.to.assert_called_with("cuda")

    @patch('app.services.ai_image_service.settings')
    @patch('app.services.ai_image_service.torch.no_grad')
    async def test_generate_image_success(self, mock_no_grad, mock_settings, service):
        """Test generation success and file structure."""
        service.pipe = MagicMock()
        mock_img = Image.new('RGB', (10, 10), color='red')
        service.pipe.return_value = MagicMock(images=[mock_img])
        service.tokenizer = MagicMock()
        service.tokenizer.encode.return_value = [1, 2, 3] # Short prompt
        
        mock_settings.generated_images_dir = "/tmp/test_images"

        # Mock disk operations but NOT PIL's internal save to buffer
        with patch('pathlib.Path.mkdir'), \
             patch('PIL.Image.Image.save'), \
             patch('asyncio.get_event_loop') as mock_loop:
            
            mock_loop.return_value.time.return_value = 123456.0
            
            result = await service.generate_image(prompt="modern house")

            assert result["success"] is True
            assert "images" in result
            assert len(result["images"]) == 1

    async def test_generate_image_failure(self, service):
        """Test the error handling when generation crashes."""
        service.tokenizer = MagicMock()
        # Force the model initialization to fail
        with patch.object(service, 'initialize_model', side_effect=Exception("Generation failed")):
            result = await service.generate_image(prompt="test")
            
            assert result["success"] is False
            assert "Generation failed" in result["error"]

    async def test_generate_image_base64_encoding(self, service):
        """Verify the Image -> Base64 string conversion logic."""
        service.pipe = MagicMock()
        service.initialize_model = AsyncMock() 
        
        test_color = (0, 255, 0) # Pure Green
        mock_img = Image.new('RGB', (10, 10), color=test_color)
        service.pipe.return_value = MagicMock(images=[mock_img])
        service.tokenizer = MagicMock()
        service.tokenizer.encode.return_value = [1, 2, 3]

        with patch('app.services.ai_image_service.settings') as mock_settings, \
             patch('pathlib.Path.mkdir'), \
             patch('torch.no_grad'):
            
            mock_settings.generated_images_dir = "/tmp/test"
            
            with patch('app.services.ai_image_service.Path') as mock_path_class:
                mock_path_instance = MagicMock()
                mock_path_instance.__truediv__.return_value = "test_image.png"
                mock_path_class.return_value = mock_path_instance
                
                # Capture the UNBOUND method
                original_save = Image.Image.save

                # The first argument to an unbound method must be the instance (self)
                def side_effect(img_instance, fp, *args, **kwargs):
                    # If fp is a BytesIO buffer, perform the real save
                    if isinstance(fp, (io.BytesIO, io.RawIOBase)):
                        return original_save(img_instance, fp, *args, **kwargs)
                    # If it's the disk save (filepath), skip it
                    return None 

                with patch('PIL.Image.Image.save', autospec=True, side_effect=side_effect):
                    result = await service.generate_image(prompt="test")
                    
                    if not result["success"]:
                        pytest.fail(f"Service failed: {result.get('error')}")
                    
                    img_b64 = result["images"][0]["image_data"]
                    img_bytes = base64.b64decode(img_b64)
                    
                    decoded_img = Image.open(io.BytesIO(img_bytes))
                    assert decoded_img.getpixel((0, 0)) == test_color

    async def test_generate_architectural_visualization(self, service):
        """Test high-level wrapper builds prompt correctly."""
        service.generate_image = AsyncMock(return_value={"success": True})
        
        await service.generate_architectural_visualization(
            design_description="modern glass villa",
            style="minimalist"
        )
        
        kwargs = service.generate_image.call_args.kwargs
        assert "modern glass villa" in kwargs["prompt"]
        assert "minimalist" in kwargs["prompt"]