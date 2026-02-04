from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class BudgetCategory(Base):
    """Budget categories for organizing expenses."""

    __tablename__ = "budget_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)

    # Category type
    category_type = Column(String(50), nullable=False)  # labor, materials, equipment, permits, etc.

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    budget_items = relationship("BudgetItem", back_populates="category", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<BudgetCategory(id={self.id}, name='{self.name}', type='{self.category_type}')>"


class BudgetItem(Base):
    """Individual budget items for expense tracking."""

    __tablename__ = "budget_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Project relationship
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    # Category relationship
    category_id = Column(Integer, ForeignKey("budget_categories.id"), nullable=False)

    # Budget details
    budgeted_amount = Column(Float, nullable=False)
    actual_amount = Column(Float, default=0.0)
    quantity = Column(Float)  # For items with measurable quantities
    unit = Column(String(50))  # sq_ft, linear_ft, each, etc.
    unit_cost = Column(Float)  # Cost per unit

    # Status and approval
    status = Column(String(50), default="planned")  # planned, approved, ordered, received, paid
    approved_by = Column(String(255))
    approved_date = Column(DateTime(timezone=True))

    # Vendor information
    vendor_name = Column(String(255))
    vendor_contact = Column(String(255))
    purchase_order_number = Column(String(100))

    # Dates
    planned_date = Column(DateTime(timezone=True))
    actual_date = Column(DateTime(timezone=True))

    # Additional tracking
    notes = Column(Text)
    receipt_url = Column(String(500))  # Link to receipt document

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="budget_items")
    category = relationship("BudgetCategory", back_populates="budget_items")

    @property
    def variance(self) -> float:
        """Calculate budget variance (actual - budgeted)."""
        return self.actual_amount - self.budgeted_amount

    @property
    def variance_percentage(self) -> float:
        """Calculate budget variance as percentage."""
        if self.budgeted_amount > 0:
            return (self.variance / self.budgeted_amount) * 100
        return 0.0

    def __repr__(self):
        return f"<BudgetItem(id={self.id}, name='{self.name}', budgeted=${self.budgeted_amount}, actual=${self.actual_amount})>"
