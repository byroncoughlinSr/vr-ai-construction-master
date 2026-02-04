from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from ...services import AIImageService

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
@limiter.limit("5/minute")  # 5 image generations per minute
async def generate_image(request: ImageGenerationRequest, background_tasks: BackgroundTasks):
    """
    Generate an image using Stable Diffusion based on the provided prompt.

    This endpoint generates images asynchronously and returns the result.
    For large images or complex prompts, generation may take several seconds.
    """
    try:
        result = await image_service.generate_image(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            width=request.width,
            height=request.height,
            num_inference_steps=request.num_inference_steps,
            guidance_scale=request.guidance_scale
        )

        if result["success"]:
            return JSONResponse(
                status_code=200,
                content=result
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Image generation failed: {result.get('error', 'Unknown error')}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Image generation service error: {str(e)}"
        )


@router.post("/architectural-visualization")
async def generate_architectural_visualization(
    request: ArchitecturalVisualizationRequest,
    background_tasks: BackgroundTasks
):
    """
    Generate an architectural visualization optimized for construction projects.

    This endpoint creates professional architectural renderings with appropriate
    lighting, perspective, and detail for construction planning.
    """
    try:
        result = await image_service.generate_architectural_visualization(
            design_description=request.design_description,
            style=request.style,
            time_of_day=request.time_of_day
        )

        if result["success"]:
            return JSONResponse(
                status_code=200,
                content=result
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Architectural visualization failed: {result.get('error', 'Unknown error')}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Architectural visualization service error: {str(e)}"
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
