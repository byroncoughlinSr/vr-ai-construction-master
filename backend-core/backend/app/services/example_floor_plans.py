"""Hand-drawn example floor plan, for a fresh database and for tests.

``python -m scripts.seed_example_floor_plan`` (from backend-core/backend) saves
it as a project. Sizes are in feet, in the planner's ``project_structure`` format.
"""

from __future__ import annotations

import copy

from sqlalchemy.orm import Session

from ..models import Project
from . import floor_plan_service

EXAMPLE_NAME = "Maple Hollow Cottage"

EXAMPLE_DESCRIPTION = (
    "Single-storey three-bedroom cottage, 50 x 36 ft. The front door opens into an "
    "entry foyer beside the living room; dining room and kitchen sit behind them. "
    "A hallway down the middle leads to the bedroom wing: a second bedroom at the "
    "front, a hall bathroom, and a primary suite with its own bathroom at the back."
)

# Public wing on the left, hallway down the middle, bedrooms on the right.
EXAMPLE_STRUCTURE = {
    "total_area_sqft": 1800,
    "layout": {
        "length": 50,
        "width": 36,
        "entry": "Entry Foyer",
        "split": "x",
        "parts": [
            {"size": 26, "split": "z", "parts": [
                {"size": 16, "split": "x", "parts": [
                    {"size": 8, "room": "Entry Foyer"},
                    {"size": 18, "room": "Living Room"},
                ]},
                {"size": 20, "split": "x", "parts": [
                    {"size": 14, "room": "Dining Room"},
                    {"size": 12, "room": "Kitchen"},
                ]},
            ]},
            {"size": 4, "room": "Hallway"},
            {"size": 20, "split": "z", "parts": [
                {"size": 12, "room": "Bedroom 2"},
                {"size": 8, "room": "Hall Bathroom"},
                {"size": 16, "split": "x", "parts": [
                    {"size": 13, "room": "Primary Bedroom"},
                    {"size": 7, "room": "Primary Bathroom"},
                ]},
            ]},
        ],
    },
    "rooms": [
        {"name": "Entry Foyer", "dimensions": {"height": 9}, "floor_material": "tile",
         "wall_material": "drywall", "connects_to": ["Living Room"]},
        {"name": "Living Room", "dimensions": {"height": 10}, "floor_material": "wood",
         "wall_material": "drywall", "connects_to": ["Entry Foyer", "Dining Room", "Hallway"]},
        {"name": "Dining Room", "dimensions": {"height": 9}, "floor_material": "wood",
         "wall_material": "drywall", "connects_to": ["Living Room", "Kitchen"]},
        {"name": "Kitchen", "dimensions": {"height": 9}, "floor_material": "tile",
         "wall_material": "drywall", "connects_to": ["Dining Room", "Hallway"]},
        {"name": "Hallway", "dimensions": {"height": 9}, "floor_material": "wood",
         "wall_material": "drywall",
         "connects_to": ["Living Room", "Kitchen", "Bedroom 2", "Hall Bathroom", "Primary Bedroom"]},
        {"name": "Bedroom 2", "dimensions": {"height": 9}, "floor_material": "carpet",
         "wall_material": "drywall", "connects_to": ["Hallway"]},
        {"name": "Hall Bathroom", "dimensions": {"height": 9}, "floor_material": "tile",
         "wall_material": "drywall", "connects_to": ["Hallway"]},
        {"name": "Primary Bedroom", "dimensions": {"height": 9}, "floor_material": "carpet",
         "wall_material": "drywall", "connects_to": ["Hallway", "Primary Bathroom"]},
        {"name": "Primary Bathroom", "dimensions": {"height": 9}, "floor_material": "tile",
         "wall_material": "drywall", "connects_to": ["Primary Bedroom"]},
    ],
}


def seed_example(db: Session) -> Project:
    """Save the example as a project with floor plan v1 (committed). Returns it;
    an existing project of the same name is returned unchanged."""
    existing = db.query(Project).filter(Project.name == EXAMPLE_NAME).first()
    if existing:
        return existing
    project = Project(
        name=EXAMPLE_NAME,
        description=EXAMPLE_DESCRIPTION,
        status="planning",
        budget=420000,
        estimated_cost=385000,
    )
    db.add(project)
    db.flush()
    floor_plan_service.add_floor_plan_version(
        db, project.id, EXAMPLE_NAME, copy.deepcopy(EXAMPLE_STRUCTURE),
        change_type="example", change_note="Hand-drawn example floor plan", source="example",
    )
    db.commit()
    db.refresh(project)
    return project
