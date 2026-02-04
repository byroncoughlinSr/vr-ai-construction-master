from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from ...services import AIPlanningService

# Rate limiter for AI endpoints
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()
planning_service = AIPlanningService()


class ConstructionPlanRequest(BaseModel):
    """Request model for construction plan generation."""
    project_description: str
    budget: Optional[float] = None
    timeline_weeks: Optional[int] = None
    constraints: Optional[List[str]] = None


@router.post("/generate-plan")
@limiter.limit("3/minute")  # 3 plan generations per minute
async def generate_construction_plan(request: ConstructionPlanRequest):
    """
    Generate a comprehensive construction plan using AI.

    This endpoint creates detailed project plans including phases, tasks,
    material requirements, timelines, and cost estimates.
    """
    try:
        result = await planning_service.generate_construction_plan(
            project_description=request.project_description,
            budget=request.budget,
            timeline_weeks=request.timeline_weeks,
            constraints=request.constraints
        )

        if result["success"]:
            return JSONResponse(
                status_code=200,
                content=result
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Plan generation failed: {result.get('error', 'Unknown error')}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Construction planning service error: {str(e)}"
        )


@router.get("/status")
async def get_service_status():
    """Check the status of the AI planning service."""
    try:
        return {
            "service": "AI Construction Planning",
            "status": "healthy",
            "ollama_available": planning_service.ollama_available,
            "gemini_available": planning_service.gemini_available,
            "models": {
                "primary": "Llama 3.1 8B (Ollama)" if planning_service.ollama_available else None,
                "fallback": "Gemini Pro" if planning_service.gemini_available else None
            },
            "capabilities": [
                "construction plan generation",
                "cost estimation",
                "timeline planning",
                "risk assessment",
                "material requirements"
            ]
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Service status check failed: {str(e)}"
        )


@router.get("/models")
async def list_available_models():
    """List available AI models for planning."""
    try:
        models = []

        if planning_service.ollama_available:
            models.append({
                "name": "Llama 3.1 8B",
                "provider": "Ollama",
                "status": "available",
                "capabilities": ["text generation", "planning", "analysis"]
            })

        if planning_service.gemini_available:
            models.append({
                "name": "Gemini Pro",
                "provider": "Google",
                "status": "available",
                "capabilities": ["text generation", "planning", "analysis"]
            })

        if not models:
            models.append({
                "name": "No models available",
                "provider": "None",
                "status": "unavailable",
                "capabilities": []
            })

        return {
            "models": models,
            "total_available": len([m for m in models if m["status"] == "available"])
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Model listing failed: {str(e)}"
        )
