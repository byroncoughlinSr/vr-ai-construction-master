# Import all models to ensure they are registered with SQLAlchemy
from .project import Project
from .design import Design, DesignElement
from .material import Material, MaterialCategory
from .ai_generation import AIGeneration
from .construction_phase import ConstructionPhase, Task
from .resources import LaborResource, Equipment, LaborAssignment, EquipmentAssignment
from .budget import BudgetCategory, BudgetItem
from .compliance import Permit, Inspection
from .documents import Document, DocumentComment

__all__ = [
    "Project", "Design", "DesignElement", "Material", "MaterialCategory", "AIGeneration",
    "ConstructionPhase", "Task", "LaborResource", "Equipment", "LaborAssignment", "EquipmentAssignment",
    "BudgetCategory", "BudgetItem", "Permit", "Inspection", "Document", "DocumentComment"
]
