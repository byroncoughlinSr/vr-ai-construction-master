"""Start an image generation in the background and report it over the
``/ws/image-progress/{generation_id}`` WebSocket."""

import logging
import uuid
from typing import Any, Awaitable, Callable, Dict

from ...background import run_in_background
from .websocket import (
    complete_image_generation,
    fail_image_generation,
    send_image_progress_update,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[Dict[str, Any]], Awaitable[None]]
# Receives the progress callback and the generation id; returns the image
# service's result dict ({"success": bool, "images": [...]} or {"error": ...}).
Generate = Callable[[ProgressCallback, str], Awaitable[Dict[str, Any]]]


def start_image_generation(generate: Generate, label: str = "image") -> str:
    """Run ``generate`` in the background and return its generation id."""
    generation_id = str(uuid.uuid4())

    async def job():
        async def progress(data: Dict[str, Any]):
            await send_image_progress_update(generation_id, data)

        try:
            result = await generate(progress, generation_id)
            if result.get("success"):
                await complete_image_generation(generation_id, result)
                logger.info(f"✅ {label} {generation_id} completed")
            else:
                error = result.get("error", "Unknown error")
                await fail_image_generation(generation_id, error)
                logger.error(f"❌ {label} {generation_id} failed: {error}")
        except Exception as e:
            logger.error(f"❌ {label} {generation_id} error: {e}", exc_info=True)
            await fail_image_generation(generation_id, str(e))

    run_in_background(job(), name=f"{label}-{generation_id}")
    logger.info(f"🎨 Started {label} {generation_id}")
    return generation_id
