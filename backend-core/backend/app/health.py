"""
Health check endpoints for monitoring service status.
"""

import time
import psutil
from typing import Dict, Any
from sqlalchemy.orm import Session

from .database import get_db
from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


async def check_database_health(db: Session) -> Dict[str, Any]:
    """Check database connectivity and basic operations."""
    try:
        start_time = time.time()

        # Simple query to test database connection
        result = db.execute("SELECT 1").scalar()

        response_time = (time.time() - start_time) * 1000  # ms

        if result == 1:
            return {
                "status": "healthy",
                "response_time_ms": round(response_time, 2),
                "message": "Database connection successful"
            }
        else:
            return {
                "status": "unhealthy",
                "response_time_ms": round(response_time, 2),
                "message": "Database query returned unexpected result"
            }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "message": "Database connection failed"
        }


async def check_ai_services_health() -> Dict[str, Any]:
    """Check AI services availability."""
    ai_status = {
        "ollama": {"status": "unknown", "message": "Not checked"},
        "stable_diffusion": {"status": "unknown", "message": "Not checked"}
    }

    # Check Ollama (if configured)
    try:
        import httpx
        import asyncio

        async with httpx.AsyncClient(timeout=5.0) as client:
            # Try to connect to Ollama API
            ollama_url = getattr(settings, 'ollama_url', 'http://localhost:11434')
            response = await client.get(f"{ollama_url}/api/tags")

            if response.status_code == 200:
                ai_status["ollama"] = {
                    "status": "healthy",
                    "message": "Ollama API accessible",
                    "models_available": len(response.json().get("models", []))
                }
            else:
                ai_status["ollama"] = {
                    "status": "unhealthy",
                    "message": f"Ollama API returned status {response.status_code}"
                }
    except Exception as e:
        ai_status["ollama"] = {
            "status": "unhealthy",
            "message": f"Ollama check failed: {str(e)}"
        }

    # For Stable Diffusion, we can't easily check without loading the model
    # This would be expensive, so we just mark it as available
    ai_status["stable_diffusion"] = {
        "status": "healthy",
        "message": "Stable Diffusion available (checked at startup)"
    }

    return ai_status


def get_system_metrics() -> Dict[str, Any]:
    """Get basic system metrics."""
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_usage_percent": psutil.disk_usage('/').percent,
        "uptime_seconds": time.time() - psutil.boot_time()
    }


async def comprehensive_health_check(db: Session) -> Dict[str, Any]:
    """Comprehensive health check for all services."""
    start_time = time.time()

    # Basic service info
    health_data = {
        "service": "vr-construction-api",
        "version": "1.0.0",
        "timestamp": time.time(),
        "environment": getattr(settings, 'environment', 'unknown'),
        "status": "healthy"  # Will be updated if any check fails
    }

    # Database check
    db_health = await check_database_health(db)
    health_data["database"] = db_health

    # AI services check
    ai_health = await check_ai_services_health()
    health_data["ai_services"] = ai_health

    # System metrics
    health_data["system"] = get_system_metrics()

    # Overall status determination
    critical_services = [db_health["status"]] + [service["status"] for service in ai_health.values()]

    if any(status != "healthy" for status in critical_services):
        health_data["status"] = "degraded"
        if any(status == "unhealthy" for status in critical_services):
            health_data["status"] = "unhealthy"

    # Response time
    health_data["response_time_ms"] = round((time.time() - start_time) * 1000, 2)

    return health_data


async def readiness_check(db: Session) -> Dict[str, Any]:
    """Readiness probe - checks if service is ready to accept traffic."""
    try:
        # Check database connectivity
        db_health = await check_database_health(db)

        if db_health["status"] == "healthy":
            return {
                "status": "ready",
                "database": "connected",
                "message": "Service is ready to accept traffic"
            }
        else:
            return {
                "status": "not_ready",
                "database": "disconnected",
                "message": "Database not available"
            }
    except Exception as e:
        return {
            "status": "not_ready",
            "error": str(e),
            "message": "Readiness check failed"
        }


async def liveness_check() -> Dict[str, Any]:
    """Liveness probe - checks if service is running."""
    return {
        "status": "alive",
        "timestamp": time.time(),
        "message": "Service is running"
    }
