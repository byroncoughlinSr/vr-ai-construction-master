"""
Common Pydantic schemas used across the API.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class TimestampModel(BaseModel):
    """Base model with timestamp fields."""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
