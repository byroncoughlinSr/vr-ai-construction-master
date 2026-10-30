# Import all models to ensure they are registered with SQLAlchemy
from .project import Project
from .design import Design, DesignElement
from .material import Material, MaterialCategory
from .ai_generation import AIGeneration
from .floor_plan import FloorPlan
from .plant_model import PlantModel
from .kitchen_style import KitchenStyle
from .resources import LaborResource, Equipment, LaborAssignment, EquipmentAssignment
from .documents import Document, DocumentComment
from .crm import Client, ClientActivity
from .punch_list import PunchItem

__all__ = [
    "Project", "Design", "DesignElement", "Material", "MaterialCategory", "AIGeneration", "FloorPlan", "PlantModel", "KitchenStyle",
    "LaborResource", "Equipment", "LaborAssignment", "EquipmentAssignment", "Document", "DocumentComment",
    "Client", "ClientActivity", "PunchItem",
]
