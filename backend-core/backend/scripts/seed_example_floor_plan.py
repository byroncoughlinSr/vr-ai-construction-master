"""Create the example project "Maple Hollow Cottage" with its floor plan.

Run from backend-core/backend with the venv active:
    python -m scripts.seed_example_floor_plan
Applies migrations first, so it also works on a freshly created database.
"""

from app.database import SessionLocal, run_migrations
from app.services.example_floor_plans import seed_example
from app.services.floor_plan_service import geometry_for_project


def main() -> None:
    run_migrations()
    with SessionLocal() as db:
        project = seed_example(db)
        geometry = geometry_for_project(db, project)
        print(
            f"Project {project.id}: '{project.name}' — floor plan v{geometry['floor_plan']['version']}, "
            f"{len(geometry['rooms'])} rooms, {len(geometry['doors'])} doors, "
            f"{len(geometry['windows'])} windows ({geometry['metadata']['layout']} layout)"
        )


if __name__ == "__main__":
    main()
