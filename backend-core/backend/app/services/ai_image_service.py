import asyncio
import logging
import time
from typing import Optional, Dict, Any
from pathlib import Path
import torch
from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler
from compel import Compel
from transformers import CLIPTokenizer
from PIL import Image
import io
import base64
import re

from ..config import settings

logger = logging.getLogger(__name__)


class AIImageService:
    """Service for generating architectural images using Stable Diffusion with Compel support."""

    def __init__(self):
        self.pipe = None
        self.compel = None
        self.tokenizer = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.max_tokens = 75  # Safe limit for SD 1.5 (77 including special tokens)
        logger.info(f"AI Image Service initialized with device: {self.device}")

    def _load_model_sync(self):
        """Synchronous model loading - runs in thread pool."""
        logger.info("Loading Stable Diffusion model (Realistic Vision)...")
        
        # Use architecture-focused realistic model
        pipe = StableDiffusionPipeline.from_pretrained(
            "SG161222/Realistic_Vision_V5.1_noVAE",
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            safety_checker=None,
            requires_safety_checker=False
        )
        
        # Use better scheduler for quality
        pipe.scheduler = DPMSolverMultistepScheduler(
            beta_start=0.00085,
            beta_end=0.012,
            beta_schedule="scaled_linear",
            num_train_timesteps=1000,
            algorithm_type="dpmsolver++",
            solver_order=2,
            final_sigmas_type="sigma_min"
        )
        
        return pipe.to(self.device)
    
    async def initialize_model(self):
        """Initialize the Stable Diffusion model with Compel support."""
        if self.pipe is None:
            try:
                # Run blocking model loading in thread pool
                loop = asyncio.get_event_loop()
                self.pipe = await loop.run_in_executor(None, self._load_model_sync)
                
                # Initialize Compel for long prompt support (bypasses 77 token limit)
                self.compel = Compel(
                    tokenizer=self.pipe.tokenizer,
                    text_encoder=self.pipe.text_encoder
                )
                
                # Initialize tokenizer for prompt compression
                self.tokenizer = CLIPTokenizer.from_pretrained(
                    "openai/clip-vit-large-patch14"
                )
                
                logger.info("Stable Diffusion model loaded successfully with Compel support")
                
            except Exception as e:
                logger.error(f"Failed to load Stable Diffusion model: {e}")
                raise
    
    def count_tokens(self, prompt: str) -> int:
        """Count tokens in a prompt."""
        if self.tokenizer is None:
            return 0
        tokens = self.tokenizer.encode(prompt)
        return len(tokens)
    
    def compress_prompt(self, long_prompt: str) -> str:
        """
        Intelligently compress prompt to fit 77 token limit.
        Only used as fallback if Compel is unavailable.
        """
        
        # Check current length
        token_count = self.count_tokens(long_prompt)
        
        if token_count <= self.max_tokens:
            logger.info(f"Prompt fits in {token_count} tokens")
            return long_prompt
        
        logger.warning(f"Prompt has {token_count} tokens, compressing to fit {self.max_tokens}")
        
        # Compression rules - remove quality descriptors, keep specifics
        replacements = {
            'professional': '',
            'high quality': '',
            'sharp focus': '',
            'high detail': '',
            'detailed': '',
            'quality': '',
            'professional construction documentation': '',
            'architectural visualization': 'arch rendering',
            'photorealistic': 'photo',
            'rendering': '',
            'feet': 'ft',
            'degree': '°',
            'DIMENSIONS:': '',
            'MATERIALS:': '',
            'STRUCTURE:': '',
            'STYLE:': '',
            'QUALITY:': '',
            '  ': ' ',
        }
        
        compressed = long_prompt
        for old, new in replacements.items():
            compressed = compressed.replace(old, new)
        
        # Remove extra whitespace and commas
        compressed = ' '.join(compressed.split())
        compressed = re.sub(r',\s*,', ',', compressed)
        
        # Re-check token count
        new_token_count = self.count_tokens(compressed)
        
        if new_token_count > self.max_tokens:
            logger.warning(f"Still {new_token_count} tokens after compression, aggressive trimming...")
            
            # Extract only essential parts
            essential_parts = []
            
            # Keep dimensions
            dims = re.findall(r'\d+\s*(?:ft|feet|\'|\")', compressed)
            if dims:
                essential_parts.extend(dims[:3])  # Max 3 dimensions
            
            # Keep materials
            materials = []
            if 'cedar' in compressed.lower():
                materials.append('cedar siding')
            if 'tile' in compressed.lower():
                materials.append('tile roof')
            if materials:
                essential_parts.extend(materials)
            
            # Keep roof type
            if '°' in compressed or 'gable' in compressed.lower():
                essential_parts.append('gable roof')
            
            # Keep colors
            colors = re.findall(r'\b(?:dark|light)?\s*(?:brown|red|white|gray|grey|black)\b', compressed.lower())
            if colors:
                essential_parts.append(colors[0])
            
            # Reconstruct minimal prompt
            compressed = f"dog house, {', '.join(essential_parts)}, photo, 8k"
        
        final_count = self.count_tokens(compressed)
        logger.info(f"Compressed from {token_count} to {final_count} tokens")
        logger.debug(f"Compressed prompt: {compressed}")
        
        return compressed

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        width: int = 768,
        height: int = 512,
        num_inference_steps: int = 50,
        guidance_scale: float = 8.0,
        num_images: int = 1,
        progress_callback: Optional[callable] = None,
        generation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            await self.initialize_model()

            if negative_prompt is None:
                negative_prompt = "cartoon, low quality, blurry, text"

            # 1. Define Callback Logic at the very beginning of the method
            def stable_diffusion_callback(step: int, timestep, latents):
                if progress_callback and generation_id:
                    try:
                        percentage = int(((step + 1) / num_inference_steps) * 100)
                        progress_data = {
                            "generation_id": generation_id,
                            "step": step + 1,
                            "total_steps": num_inference_steps,
                            "percentage": min(percentage, 100),
                            "status": "generating"
                        }
                        
                        # Schedule callback as a task on the running event loop
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(progress_callback(progress_data))
                        except RuntimeError:
                            pass  # No running loop; skip callback
                    except Exception as e:
                        logger.warning(f"Callback failure: {e}")

            # 2. Package all shared arguments into a dictionary
            # This ensures BOTH paths below are forced to use the callback
            pipeline_kwargs = {
                "width": width,
                "height": height,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "num_images_per_prompt": num_images,
                "callback": stable_diffusion_callback if progress_callback else None,
                "callback_steps": 1
            }

            prompt_tokens = self.count_tokens(prompt)
            use_compel = prompt_tokens > self.max_tokens or self.compel is not None

            # Create synchronous generation function to run in thread pool
            def generate_sync():
                if use_compel and self.compel is not None:
                    logger.info("Using Compel path")
                    prompt_embeds = self.compel.build_conditioning_tensor(prompt)
                    negative_embeds = self.compel.build_conditioning_tensor(negative_prompt)
                    with torch.no_grad():
                        return self.pipe(
                            prompt_embeds=prompt_embeds,
                            negative_prompt_embeds=negative_embeds,
                            **pipeline_kwargs
                        )
                else:
                    logger.info("Using standard prompt (fits in 77 tokens)")
                    with torch.no_grad():
                        return self.pipe(
                            prompt=prompt,
                            negative_prompt=negative_prompt,
                            **pipeline_kwargs
                        )
            
            # Run SD generation in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, generate_sync)

            # Encode each image to base64 and save to disk
            images_output = []
            output_dir = Path(settings.generated_images_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            for i, img in enumerate(result.images):
                filename = f"generated_{generation_id or int(time.time() * 1000)}_{i}.png"
                filepath = output_dir / filename

                # Save to disk
                img.save(str(filepath))

                # Encode to base64 for API response
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                buffer.seek(0)
                img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

                images_output.append({
                    "image_data": img_base64,
                    "filename": filename,
                    "path": str(filepath),
                    "image_url": f"/generated_images/{filename}",
                })

            return {"success": True, "images": images_output, "count": len(images_output)}

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return {"success": False, "error": str(e)}
        
    async def generate_architectural_visualization(
        self,
        design_description: str,
        style: str = "modern",
        time_of_day: str = "day",
        view_type: str = "exterior",
        progress_callback: Optional[callable] = None,
        generation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate an architectural visualization with optimized prompts.
        This is the main entry point for voice-to-image generation.

        Args:
            design_description: Description from voice input or text
            style: Architectural style (modern, traditional, craftsman, etc.)
            time_of_day: Time of day for lighting (day, night, sunset, golden_hour)
            view_type: Type of view (exterior, interior, aerial, detail)
            progress_callback: Optional callback for progress updates
            generation_id: Optional ID for tracking

        Returns:
            Generated image data
        """
        
        # Build comprehensive architectural prompt
        prompt = self.build_architectural_prompt(
            design_description, 
            style, 
            time_of_day, 
            view_type
        )
        
        # Enhanced negative prompt for architecture
        negative_prompt = """cartoon, anime, sketch, drawing, painting,
        illustration, 3d render, cgi, toy, miniature, plastic,
        low quality, blurry, distorted, deformed, ugly,
        bad architecture, bad proportions, unrealistic,
        multiple structures, people, animals,
        text, watermark, signature, extra elements,
        oversaturated, undersaturated"""
        
        logger.info(f"Generating architectural visualization: {style} {view_type}")
        
        return await self.generate_image(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=768,
            height=512,  # Landscape format for architecture
            num_inference_steps=50,  # High quality
            guidance_scale=8.0,  # Follow prompt closely
            num_images=1,
            progress_callback=progress_callback,
            generation_id=generation_id
        )
    
    def build_architectural_prompt(
        self,
        description: str,
        style: str = "modern",
        time_of_day: str = "day",
        view_type: str = "exterior"
    ) -> str:
        """
        Build detailed architectural prompt from voice description.
        Handles long descriptions using Compel (no token limit).
        """
        
        # Time of day lighting presets
        lighting_map = {
            "day": "natural daylight, clear sky, soft shadows",
            "night": "evening lighting, warm interior lights, twilight sky",
            "sunset": "golden hour, warm sunset lighting, long shadows",
            "golden_hour": "golden hour photography, warm tones, dramatic lighting",
            "overcast": "overcast soft lighting, even illumination, cloudy sky"
        }
        
        lighting = lighting_map.get(time_of_day, lighting_map["day"])
        
        # Build comprehensive prompt (Compel handles any length)
        prompt = f"""professional architectural {view_type} photograph,
        
        SUBJECT: {description},
        
        STYLE: {style} architectural design,
        residential construction aesthetic,
        clean professional craftsmanship,
        
        LIGHTING: {lighting},
        
        QUALITY: photorealistic architectural visualization,
        professional real estate photography quality,
        sharp focus, high detail, natural materials and textures,
        8k resolution, architectural digest style,
        trending on architectural platforms"""
        
        return prompt
    
    async def generate_from_voice_input(
        self,
        voice_text: str,
        num_options: int = 3
    ) -> Dict[str, Any]:
        """
        Generate architectural images from voice input.
        Creates multiple options for user to choose from.
        
        Args:
            voice_text: Transcribed voice input
            num_options: Number of image variations to generate (1-4)
            
        Returns:
            Dict with multiple image options
        """
        
        logger.info(f"Voice-to-image generation: '{voice_text}'")
        
        # Extract architectural details from voice input
        details = self.extract_architectural_details(voice_text)
        
        # Build enhanced prompt
        prompt = self.build_architectural_prompt(
            description=voice_text,
            style=details.get("style", "modern"),
            time_of_day=details.get("time", "day"),
            view_type=details.get("view", "exterior")
        )
        
        # Generate multiple options
        result = await self.generate_image(
            prompt=prompt,
            width=768,
            height=512,
            num_inference_steps=50,
            guidance_scale=8.0,
            num_images=min(num_options, 4)  # Max 4 to avoid memory issues
        )
        
        if result["success"]:
            logger.info(f"Generated {result['count']} image options from voice input")
        
        return result
    
    def extract_architectural_details(self, voice_text: str) -> Dict[str, str]:
        """
        Extract architectural style, time, and view type from voice input.
        Uses simple keyword matching.
        """
        
        text_lower = voice_text.lower()
        details = {}
        
        # Detect style
        style_keywords = {
            "modern": ["modern", "contemporary", "minimalist"],
            "traditional": ["traditional", "classic", "colonial"],
            "craftsman": ["craftsman", "arts and crafts"],
            "industrial": ["industrial", "loft"],
            "mediterranean": ["mediterranean", "spanish", "tuscan"],
            "farmhouse": ["farmhouse", "rustic", "country"]
        }
        
        for style, keywords in style_keywords.items():
            if any(kw in text_lower for kw in keywords):
                details["style"] = style
                break
        
        # Detect time of day
        if any(word in text_lower for word in ["night", "evening", "dark"]):
            details["time"] = "night"
        elif any(word in text_lower for word in ["sunset", "dusk", "golden"]):
            details["time"] = "sunset"
        else:
            details["time"] = "day"
        
        # Detect view type
        if any(word in text_lower for word in ["interior", "inside", "room"]):
            details["view"] = "interior"
        elif any(word in text_lower for word in ["aerial", "overhead", "drone"]):
            details["view"] = "aerial"
        else:
            details["view"] = "exterior"
        
        return details