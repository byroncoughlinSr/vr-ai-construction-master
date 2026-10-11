"""AI services.

Imported lazily so that light modules such as ``vr_geometry_service`` can be
used (and tested) without loading torch/diffusers, which ``ai_image_service``
pulls in at import time.
"""

__all__ = ["AIImageService", "AIPlanningService", "get_image_service"]


def __getattr__(name):
    if name in ("AIImageService", "get_image_service"):
        from . import ai_image_service
        return getattr(ai_image_service, name)
    if name == "AIPlanningService":
        from .ai_planning_service import AIPlanningService
        return AIPlanningService
    raise AttributeError(name)
