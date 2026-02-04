import asyncio
import logging
from typing import Optional, Dict, Any
from pathlib import Path
import torch
from diffusers import StableDiffusionPipeline
from PIL import Image
import io
import base64

from ..config import settings

logger = logging.getLogger(__name__)


class AIImageService:
    """Service for generating architectural images using Stable Diffusion."""

    def __init__(self):
        self.pipe = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"AI Image Service initialized with device: {self.device}")

    async def initialize_model(self):
        """Initialize the Stable Diffusion model."""
        if self.pipe is None:
            try:
                logger.info("Loading Stable Diffusion model...")
                self.pipe = StableDiffusionPipeline.from_pretrained(
                    "runwayml/stable-diffusion-v1-5",
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                    safety_checker=None,  # Disable safety checker for architectural images
                    requires_safety_checker=False
                )
                self.pipe = self.pipe.to(self.device)
                logger.info("Stable Diffusion model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load Stable Diffusion model: {e}")
                raise

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        width: int = 512,
        height: int = 512,
        num_inference_steps: int = 20,
        guidance_scale: float = 7.5,
        progress_callback: Optional[callable] = None,
        generation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate an architectural image based on the prompt.

        Args:
            prompt: Description of the image to generate
            negative_prompt: What to avoid in the image
            width: Image width
            height: Image height
            num_inference_steps: Number of denoising steps
            guidance_scale: How closely to follow the prompt

        Returns:
            Dict containing image data and metadata
        """
        try:
            await self.initialize_model()

            # Set default negative prompt for architectural images
            if negative_prompt is None:
                negative_prompt = "blurry, low quality, distorted, ugly, poorly drawn, cartoon, anime, text, watermark"

            # Generate image
            logger.info(f"Generating image with prompt: {prompt[:100]}...")

            # Progress callback function
            def progress_callback(step: int, timestep, latents):
                if progress_callback and generation_id:
                    try:
                        percentage = int((step / num_inference_steps) * 100)
                        asyncio.create_task(
                            progress_callback({
                                "generation_id": generation_id,
                                "step": step,
                                "total_steps": num_inference_steps,
                                "percentage": percentage,
                                "status": "generating"
                            })
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send progress update: {e}")

            with torch.no_grad():
                result = self.pipe(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    width=width,
                    height=height,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    callback=progress_callback if progress_callback else None,
                    callback_steps=1  # Update every step
                )

            image = result.images[0]

            # Convert to base64 for API response
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()

            # Save to file
            output_path = Path(settings.generated_images_dir)
            output_path.mkdir(exist_ok=True)

            filename = f"generated_{asyncio.get_event_loop().time()}.png"
            filepath = output_path / filename
            image.save(filepath)

            logger.info(f"Image generated and saved to {filepath}")

            return {
                "success": True,
                "image_data": img_str,
                "image_url": f"/generated_images/{filename}",
                "metadata": {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "width": width,
                    "height": height,
                    "steps": num_inference_steps,
                    "guidance_scale": guidance_scale,
                    "model": "stable-diffusion-v1-5"
                }
            }

        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "metadata": {
                    "prompt": prompt,
                    "model": "stable-diffusion-v1-5"
                }
            }

    async def generate_architectural_visualization(
        self,
        design_description: str,
        style: str = "modern",
        time_of_day: str = "day"
    ) -> Dict[str, Any]:
        """
        Generate an architectural visualization with optimized prompts.

        Args:
            design_description: Description of the architectural design
            style: Architectural style (modern, traditional, industrial, etc.)
            time_of_day: Time of day for lighting (day, night, sunset)

        Returns:
            Generated image data
        """
        # Craft optimized prompt for architectural visualization
        prompt = f"A high-quality architectural visualization of {design_description}, {style} style, {time_of_day} lighting, photorealistic, detailed, professional architectural rendering, 8k"

        return await self.generate_image(
            prompt=prompt,
            width=768,
            height=512,
            num_inference_steps=30,
            guidance_scale=8.0
        )
