# Import all models to ensure they are registered with SQLAlchemy
from .project import Project
from .design import Design, DesignElement
from .material import Material, MaterialCategory
from .ai_generation import AIGeneration
from .floor_plan import FloorPlan
from .plant_model import PlantModel
from .construction_phase import ConstructionPhase, Task
from .resources import LaborResource, Equipment, LaborAssignment, EquipmentAssignment
from .budget import BudgetCategory, BudgetItem, ChangeOrder
from .compliance import Permit, Inspection
from .documents import Document, DocumentComment
from .crm import Client, ClientActivity

__all__ = [
    "Project", "Design", "DesignElement", "Material", "MaterialCategory", "AIGeneration", "FloorPlan", "PlantModel",
    "ConstructionPhase", "Task", "LaborResource", "Equipment", "LaborAssignment", "EquipmentAssignment",
    "BudgetCategory", "BudgetItem", "ChangeOrder", "Permit", "Inspection", "Document", "DocumentComment",
    "Client", "ClientActivity",
]
