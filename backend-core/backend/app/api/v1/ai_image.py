from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from pathlib import Path
from pydantic import BaseModel, Field
import uuid
import logging

from ...config import settings
from ...services import get_image_service
from .image_jobs import start_image_generation

logger = logging.getLogger(__name__)

router = APIRouter()
image_service = get_image_service()


class ImageGenerationRequest(BaseModel):
    """Request model for image generation."""
    prompt: str = Field(..., min_length=1, max_length=2000)
    negative_prompt: Optional[str] = Field(None, max_length=2000)
    # Bounded so one request can't exhaust GPU memory. SD needs multiples of 8.
    width: int = Field(512, ge=256, le=1024, multiple_of=8)
    height: int = Field(512, ge=256, le=1024, multiple_of=8)
    num_inference_steps: int = Field(20, ge=1, le=100)
    guidance_scale: float = Field(7.5, ge=1.0, le=20.0)


class ArchitecturalVisualizationRequest(BaseModel):
    """Request model for architectural visualization."""
    design_description: str
    style: Optional[str] = "modern"
    time_of_day: Optional[str] = "day"


def _accepted(generation_id: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=202,  # Accepted - processing in background
        content={
            "success": True,
            "generation_id": generation_id,
            "status": "processing",
            "message": message,
            "websocket_url": f"/api/v1/ws/image-progress/{generation_id}"
        }
    )


@router.post("/generate")
async def generate_image(request: ImageGenerationRequest):
    """
    Generate an image using Stable Diffusion based on the provided prompt.

    Returns immediately with a generation_id; the image is generated in the
    background. Connect to /ws/image-progress/{generation_id} for progress —
    connecting after this call is fine: late clients get the current step, or
    the final result/error if it already finished.
    """
    generation_id = start_image_generation(
        lambda progress, gen_id: image_service.generate_image(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            width=request.width,
            height=request.height,
            num_inference_steps=request.num_inference_steps,
            guidance_scale=request.guidance_scale,
            progress_callback=progress,
            generation_id=gen_id,
        ),
        label="image generation",
    )
    return _accepted(generation_id, "Image generation started. Connect to WebSocket for progress updates.")


@router.post("/architectural-visualization")
async def generate_architectural_visualization(request: ArchitecturalVisualizationRequest):
    """
    Generate an architectural visualization optimized for construction projects.

    Returns immediately with a generation_id; progress is reported on
    /ws/image-progress/{generation_id}.
    """
    generation_id = start_image_generation(
        lambda progress, gen_id: image_service.generate_architectural_visualization(
            design_description=request.design_description,
            style=request.style,
            time_of_day=request.time_of_day,
            progress_callback=progress,
            generation_id=gen_id,
        ),
        label="architectural visualization",
    )
    return _accepted(generation_id, "Architectural visualization started. Connect to WebSocket for progress updates.")


@router.delete("/{generation_id}")
async def delete_generated_image(generation_id: str):
    """
    Delete all image files on disk associated with a generation_id.

    Used by the VR app when the user chooses "Edit Prompt" or "Start Over"
    during the 2D image review loop, so iterated-over images don't accumulate
    in generated_images/.

    Idempotent: returns success even if no files exist for the given id.
    """
    # The id goes into a glob pattern: anything but a real UUID ("*", "?", "[")
    # could match other generations' files.
    try:
        generation_id = str(uuid.UUID(generation_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="generation_id must be a UUID")

    output_dir = Path(settings.generated_images_dir)
    pattern = f"generated_{generation_id}_*.png"

    deleted_files: list[str] = []
    try:
        for path in output_dir.glob(pattern):
            try:
                path.unlink()
                deleted_files.append(path.name)
            except OSError as unlink_err:
                logger.warning(f"Failed to unlink {path}: {unlink_err}")
    except Exception as e:
        logger.error(f"Error while deleting images for {generation_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(
        f"DELETE image {generation_id}: removed {len(deleted_files)} file(s)"
    )
    return {
        "success": True,
        "generation_id": generation_id,
        "deleted_files": deleted_files,
    }


@router.get("/status")
async def get_service_status():
    """Check the status of the AI image generation service."""
    try:
        # Check if service is initialized
        device = image_service.device
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
