from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
import uuid
import logging
import asyncio

from ...services import AIImageService
from .websocket import (
    send_image_progress_update,
    complete_image_generation,
    fail_image_generation
)

logger = logging.getLogger(__name__)

# Rate limiter for AI endpoints
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()
image_service = AIImageService()


class ImageGenerationRequest(BaseModel):
    """Request model for image generation."""
    prompt: str
    negative_prompt: Optional[str] = None
    width: Optional[int] = 512
    height: Optional[int] = 512
    num_inference_steps: Optional[int] = 20
    guidance_scale: Optional[float] = 7.5


class ArchitecturalVisualizationRequest(BaseModel):
    """Request model for architectural visualization."""
    design_description: str
    style: Optional[str] = "modern"
    time_of_day: Optional[str] = "day"


@router.post("/generate")
async def generate_image(request: ImageGenerationRequest, background_tasks: BackgroundTasks):
    """
    Generate an image using Stable Diffusion based on the provided prompt.

    This endpoint returns immediately with a generation_id.
    The actual generation happens in the background.
    
    Clients should connect to WebSocket endpoint /ws/image-progress/{generation_id}
    BEFORE calling this endpoint to receive real-time progress updates.
    """
    # Generate unique ID for tracking this generation
    generation_id = str(uuid.uuid4())
    logger.info(f"Starting background image generation with ID: {generation_id}")
    
    # Define the background generation task
    async def background_generation():
        try:
            logger.info(f"Background task started for generation {generation_id}")
            
            # Define progress callback to send updates via WebSocket
            async def progress_callback(progress_data):
                await send_image_progress_update(generation_id, progress_data)
            
            # Start generation with progress tracking
            result = await image_service.generate_image(
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                width=request.width,
                height=request.height,
                num_inference_steps=request.num_inference_steps,
                guidance_scale=request.guidance_scale,
                progress_callback=progress_callback,
                generation_id=generation_id
            )

            # Notify completion or failure via WebSocket
            if result["success"]:
                await complete_image_generation(generation_id, result)
                logger.info(f"Image generation {generation_id} completed successfully")
            else:
                error_msg = result.get('error', 'Unknown error')
                await fail_image_generation(generation_id, error_msg)
                logger.error(f"Image generation {generation_id} failed: {error_msg}")

        except Exception as e:
            logger.error(f"Image generation {generation_id} error: {str(e)}")
            await fail_image_generation(generation_id, str(e))
    
    # Create the task in the background using asyncio (fire-and-forget)
    asyncio.create_task(background_generation())
    
    # Return immediately with generation_id
    return JSONResponse(
        status_code=202,  # Accepted - processing in background
        content={
            "success": True,
            "generation_id": generation_id,
            "status": "processing",
            "message": "Image generation started. Connect to WebSocket for progress updates.",
            "websocket_url": f"/api/v1/ws/image-progress/{generation_id}"
        }
    )


@router.post("/architectural-visualization")
async def generate_architectural_visualization(
    request: ArchitecturalVisualizationRequest,
    background_tasks: BackgroundTasks
):
    """
    Generate an architectural visualization optimized for construction projects.

    This endpoint returns immediately with a generation_id.
    The actual generation happens in the background.
    
    Clients should connect to WebSocket endpoint /ws/image-progress/{generation_id}
    to receive real-time progress updates during generation.
    """
    # Generate unique ID for tracking this generation
    generation_id = str(uuid.uuid4())
    logger.info(f"Starting background architectural visualization with ID: {generation_id}")
    
    # Define the background generation task
    async def background_generation():
        try:
            logger.info(f"Background task started for architectural visualization {generation_id}")
            
            # Define progress callback to send updates via WebSocket
            async def progress_callback(progress_data):
                await send_image_progress_update(generation_id, progress_data)
            
            # Start generation with progress tracking
            result = await image_service.generate_architectural_visualization(
                design_description=request.design_description,
                style=request.style,
                time_of_day=request.time_of_day,
                progress_callback=progress_callback,
                generation_id=generation_id
            )

            # Notify completion or failure via WebSocket
            if result["success"]:
                await complete_image_generation(generation_id, result)
                logger.info(f"Architectural visualization {generation_id} completed successfully")
            else:
                error_msg = result.get('error', 'Unknown error')
                await fail_image_generation(generation_id, error_msg)
                logger.error(f"Architectural visualization {generation_id} failed: {error_msg}")

        except Exception as e:
            logger.error(f"Architectural visualization {generation_id} error: {str(e)}")
            await fail_image_generation(generation_id, str(e))
    
    # Create the task in the background using asyncio (fire-and-forget)
    asyncio.create_task(background_generation())
    
    # Return immediately with generation_id
    return JSONResponse(
        status_code=202,  # Accepted - processing in background
        content={
            "success": True,
            "generation_id": generation_id,
            "status": "processing",
            "message": "Architectural visualization started. Connect to WebSocket for progress updates.",
            "websocket_url": f"/api/v1/ws/image-progress/{generation_id}"
        }
    )


@router.get("/status")
async def get_service_status():
    """Check the status of the AI image generation service."""
    try:
        # Check if service is initialized
        device = "cuda" if image_service.pipe is not None and hasattr(image_service.pipe, 'device') else "cpu"
        model_loaded = image_service.pipe is not None

        return {
            "service": "AI Image Generation",
            "status": "healthy",
            "model_loaded": model_loaded,
            "device": device,
            "supported_formats": ["PNG"],
            "max_resolution": "1024x1024"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Service status check failed: {str(e)}"
        )
