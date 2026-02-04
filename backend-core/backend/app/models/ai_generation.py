from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class AIGeneration(Base):
    """Model for AI-generated content (images, plans, voice transcripts)."""

    __tablename__ = "ai_generations"

    id = Column(Integer, primary_key=True, index=True)

    # Project relationship
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    # Generation type and source
    generation_type = Column(String(50), nullable=False)  # image, plan, voice_transcript
    source = Column(String(50), default="ollama")  # ollama, gemini, stable_diffusion

    # Input data
    prompt = Column(Text)
    input_data = Column(JSON)  # Additional input parameters

    # Output data
    output_data = Column(JSON)  # Generated content, URLs, metadata
    result_url = Column(String(500))  # URL to generated file/image

    # Status and quality
    status = Column(String(50), default="pending")  # pending, processing, completed, failed
    quality_score = Column(Integer)  # 1-10 rating of generation quality

    # Processing metadata
    processing_time = Column(Integer)  # Time in seconds
    model_used = Column(String(100))  # Specific model/version used
    error_message = Column(Text)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))

    # Relationships
    project = relationship("Project", back_populates="ai_generations")

    def __repr__(self):
        return f"<AIGeneration(id={self.id}, type='{self.generation_type}', status='{self.status}')>"
