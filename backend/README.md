# VR Construction Backend API

A FastAPI-based backend service for VR Construction platform with AI-powered planning and visualization capabilities.

## Features

- **AI-Powered Generation**: Stable Diffusion for architectural visualization, Ollama for construction planning
- **Comprehensive API**: RESTful endpoints for projects, designs, materials, and AI services
- **Database**: PostgreSQL with SQLAlchemy ORM and Alembic migrations
- **Monitoring**: Structured logging, health checks, and metrics
- **Containerization**: Docker support for development and production
- **Testing**: Comprehensive test suite with pytest

## Quick Start

### Development

1. **Clone and setup:**
   ```bash
   git clone <repository>
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Environment setup:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Run with Docker Compose:**
   ```bash
   docker compose --profile dev up -d
   ```

4. **Or run locally:**
   ```bash
   # Start PostgreSQL (if not using Docker)
   # Start Ollama service for AI features

   uvicorn app.main:app --reload
   ```

5. **Access:**
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_api.py -v
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | - | PostgreSQL connection string |
| `OLLAMA_URL` | http://localhost:11434 | Ollama API endpoint |
| `ENVIRONMENT` | development | Environment (development/production) |
| `LOG_LEVEL` | INFO | Logging level |
| `GENERATED_IMAGES_DIR` | ./generated_images | Directory for AI-generated images |
| `EXPORTS_DIR` | ./exports | Directory for exported files |
| `UPLOADS_DIR` | ./uploads | Directory for uploaded files |
| `SENTRY_DSN` | - | Sentry DSN for error tracking |

### Sample .env file

```env
DATABASE_URL=postgresql://user:password@localhost:5432/vr_construction
OLLAMA_URL=http://localhost:11434
ENVIRONMENT=development
LOG_LEVEL=DEBUG
GENERATED_IMAGES_DIR=./generated_images
EXPORTS_DIR=./exports
UPLOADS_DIR=./uploads
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
```

## Deployment

### Production with Docker Compose

1. **Build and deploy:**
   ```bash
   # Set environment variables
   export POSTGRES_PASSWORD=your_secure_password
   export SENTRY_DSN=your_sentry_dsn

   # Deploy production stack
   docker compose -f docker-compose.prod.yml --profile prod up -d
   ```

2. **With monitoring:**
   ```bash
   docker compose -f docker-compose.prod.yml --profile prod --profile monitoring up -d
   ```

### Kubernetes Deployment

The application includes health checks suitable for Kubernetes:

- **Liveness Probe**: `/health/live`
- **Readiness Probe**: `/health/ready`
- **Startup Probe**: Use readiness probe

### Manual Deployment

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run migrations:**
   ```bash
   alembic upgrade head
   ```

3. **Start service:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
   ```

## API Documentation

### Core Endpoints

- `GET /health` - Basic health check
- `GET /health/detailed` - Comprehensive health check
- `GET /docs` - Interactive API documentation
- `GET /openapi.json` - OpenAPI specification

### Main Resources

- **Projects**: `/api/v1/projects/` - Construction project management
- **Designs**: `/api/v1/designs/` - Architectural designs and elements
- **Materials**: `/api/v1/materials/` - Material catalog and suppliers
- **AI Image**: `/api/v1/image/` - AI-powered image generation
- **AI Planning**: `/api/v1/planning/` - Construction planning with AI

## Database

### Schema

The application uses PostgreSQL with the following main tables:
- `projects` - Construction projects
- `designs` - Design specifications
- `design_elements` - Individual design components
- `materials` - Material catalog
- `ai_generation` - AI-generated content tracking

### Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Run migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Monitoring

### Logging

Structured JSON logging with:
- Request ID tracking
- Performance timing
- Error correlation
- Service metadata

### Health Checks

- **Basic**: Service availability
- **Detailed**: Database, AI services, system metrics
- **Readiness**: Service ready to accept traffic
- **Liveness**: Service is running

### Metrics (Production)

Prometheus metrics available at `/metrics` when monitoring is enabled.

## Development

### Code Quality

```bash
# Run tests
pytest

# Check coverage
pytest --cov=app --cov-report=term-missing

# Type checking
mypy app/

# Linting
flake8 app/
black app/
```

### AI Services Setup

1. **Ollama**: Install and run Ollama, pull required models
   ```bash
   ollama pull llama3.1:8b
   ```

2. **Stable Diffusion**: Automatically downloaded on first use

### Database GUI

pgAdmin is included in development Docker Compose:
- URL: http://localhost:5050
- Email: admin@vrconstruction.local
- Password: admin

## Troubleshooting

### Common Issues

1. **Database connection failed**
   - Check DATABASE_URL environment variable
   - Ensure PostgreSQL is running
   - Verify database credentials

2. **AI services unavailable**
   - Check Ollama is running: `curl http://localhost:11434/api/tags`
   - Verify OLLAMA_URL configuration
   - Check GPU memory for Stable Diffusion

3. **Import errors**
   - Activate virtual environment
   - Install requirements: `pip install -r requirements.txt`

### Logs

Check logs for detailed error information:
```bash
# Docker logs
docker compose logs backend

# Application logs
tail -f logs/app.log
```

## Security

- Non-root container execution
- Input validation with Pydantic
- Rate limiting with slowapi
- CORS configuration
- Security headers middleware

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

[Your License Here]
