from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class Document(Base):
    """Document management for project files."""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)

    # Project relationship
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    # Document classification
    document_type = Column(String(50), nullable=False)  # photo, blueprint, receipt, contract, report, etc.
    category = Column(String(100))  # site_photos, floor_plans, receipts, permits, etc.

    # File information
    file_path = Column(String(500), nullable=False)
    file_url = Column(String(500), nullable=False)
    file_size = Column(Integer)  # Size in bytes
    mime_type = Column(String(100))
    file_hash = Column(String(128))  # For integrity checking

    # Document metadata
    title = Column(String(255))
    description = Column(Text)
    tags = Column(JSON)  # List of tags for searching

    # Location/context information
    location_in_project = Column(String(255))  # room name, phase, etc.
    coordinates = Column(JSON)  # GPS coordinates if applicable

    # Version control
    version = Column(String(20), default="1.0")
    previous_version_id = Column(Integer, ForeignKey("documents.id"))

    # Approval and review
    uploaded_by = Column(String(255))
    approved_by = Column(String(255))
    approval_date = Column(DateTime(timezone=True))
    is_approved = Column(Boolean, default=False)

    # Status
    status = Column(String(50), default="active")  # active, archived, deleted

    # Additional metadata
    exif_data = Column(JSON)  # Camera/photo metadata
    custom_metadata = Column(JSON)  # Flexible metadata storage

    # Dates
    taken_at = Column(DateTime(timezone=True))  # When photo was taken
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="documents")
    previous_version = relationship("Document", remote_side=[id])

    @property
    def file_size_mb(self) -> float:
        """Return file size in MB."""
        if self.file_size:
            return self.file_size / (1024 * 1024)
        return 0.0

    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}', type='{self.document_type}')>"


class DocumentComment(Base):
    """Comments and annotations on documents."""

    __tablename__ = "document_comments"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)

    # Comment details
    author = Column(String(255), nullable=False)
    comment_text = Column(Text, nullable=False)

    # Position information (for annotations)
    x_coordinate = Column(Float)  # X position on document (0-1)
    y_coordinate = Column(Float)  # Y position on document (0-1)
    page_number = Column(Integer, default=1)

    # Status
    is_resolved = Column(Boolean, default=False)
    resolved_by = Column(String(255))
    resolved_at = Column(DateTime(timezone=True))

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    document = relationship("Document", back_populates="comments")

    def __repr__(self):
        return f"<DocumentComment(id={self.id}, document={self.document_id}, author='{self.author}')>"


# Add relationships to existing models
# Note: These would need to be added to the respective model files
Document.comments = relationship("DocumentComment", back_populates="document", cascade="all, delete-orphan")
