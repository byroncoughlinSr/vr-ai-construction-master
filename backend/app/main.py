from fastapi import FastAPI, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import logging
import time
import uuid

from .config import settings
from .database import create_tables, get_db
from .logging_config import setup_logging, get_logger
from .health import comprehensive_health_check, readiness_check, liveness_check

# Import API routers
from .api.v1.ai_image import router as ai_image_router
from .api.v1.ai_planning import router as ai_planning_router
from .api.v1.projects import router as projects_router
from .api.v1.designs import router as designs_router
from .api.v1.materials import router as materials_router
from .api.v1.voice import router as voice_router
from .api.v1.websocket import router as websocket_router

# Configure structured logging
setup_logging(
    log_level=settings.log_level if hasattr(settings, 'log_level') else "INFO",
    json_format=settings.environment == "production"
)
logger = get_logger(__name__)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI app
app = FastAPI(
    title="VR Construction API",
    description="Backend API for VR Construction platform with AI-powered planning and visualization",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Security middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"] if settings.environment == "development" else ["yourdomain.com"]
)

# Compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else ["https://yourfrontend.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=86400,  # 24 hours
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    request_id = str(uuid.uuid4())

    # Add request ID to request state for use in handlers
    request.state.request_id = request_id

    # Log incoming request
    logger.info("Incoming request", extra={
        'request_id': request_id,
        'method': request.method,
        'url': str(request.url),
        'user_agent': request.headers.get('user-agent', ''),
        'client_ip': request.client.host if request.client else 'unknown',
        'request_size': request.headers.get('content-length', 0)
    })

    # Get response
    response = await call_next(request)

    # Calculate processing time
    process_time = (time.time() - start_time) * 1000  # Convert to milliseconds

    # Log response
    logger.info("Request completed", extra={
        'request_id': request_id,
        'method': request.method,
        'url': str(request.url),
        'status_code': response.status_code,
        'processing_time_ms': round(process_time, 2),
        'response_size': response.headers.get('content-length', 0)
    })

    # Add request ID to response headers for client tracking
    response.headers['X-Request-ID'] = request_id

    return response

# Mount static file directories
app.mount("/generated_images", StaticFiles(directory=settings.generated_images_dir), name="generated_images")
app.mount("/exports", StaticFiles(directory=settings.exports_dir), name="exports")
app.mount("/uploads", StaticFiles(directory=settings.uploads_dir), name="uploads")

# Include API routers
app.include_router(
    ai_image_router,
    prefix="/api/v1/image",
    tags=["AI Image Generation"]
)

app.include_router(
    ai_planning_router,
    prefix="/api/v1/planning",
    tags=["AI Construction Planning"]
)

app.include_router(
    projects_router,
    prefix="/api/v1/projects",
    tags=["Project Management"]
)

app.include_router(
    designs_router,
    prefix="/api/v1/designs",
    tags=["Design Management"]
)

app.include_router(
    materials_router,
    prefix="/api/v1/materials",
    tags=["Material Management"]
)

app.include_router(
    voice_router,
    prefix="/api/v1/voice",
    tags=["Voice Processing"]
)

app.include_router(
    websocket_router,
    prefix="/api/v1/ws",
    tags=["WebSocket Collaboration"]
)

# Health check endpoints
@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "environment": settings.environment}


@app.get("/health/live")
async def liveness_probe():
    """Liveness probe for Kubernetes."""
    return await liveness_check()


@app.get("/health/ready")
async def readiness_probe(db: Session = Depends(get_db)):
    """Readiness probe for Kubernetes."""
    return await readiness_check(db)


@app.get("/health/detailed")
async def detailed_health_check(db: Session = Depends(get_db)):
    """Comprehensive health check with all service statuses."""
    return await comprehensive_health_check(db)


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    # Create database tables on startup
    create_tables()
    print("Database tables created successfully")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development",
    )
