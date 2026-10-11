"""Plan parsing and provider fallback in AIPlanningService (no network calls)."""

import asyncio

from app.services.ai_planning_service import AIPlanningService


def _service() -> AIPlanningService:
    # Skip __init__: it builds API clients and probes Ollama.
    service = AIPlanningService.__new__(AIPlanningService)
    service.groq_available = True
    service.gemini_available = True
    service._ollama_up = False
    service._ollama_checked_at = float("inf")  # never re-probe
    return service


def test_valid_json_is_not_rewritten():
    """The regex repairs must not touch valid JSON: they used to turn
    "Bedroom 2" into "Bedroom 2," and "True" into "true" inside strings."""
    content = (
        '{"project_structure": {"rooms": [{"name": "Bedroom 2", '
        '"connects_to": ["Hall 1"], "floor_material": "True oak"}]}}'
    )
    plan = _service()._parse_structured_plan(content, "test")["plan"]
    room = plan["project_structure"]["rooms"][0]
    assert room["name"] == "Bedroom 2"
    assert room["connects_to"] == ["Hall 1"]
    assert room["floor_material"] == "True oak"


def test_broken_json_is_still_repaired():
    result = _service()._parse_structured_plan('```json\n{"total_cost": 5,}\n```', "test")
    assert result["success"] is True
    assert result["plan"]["total_cost"] == 5


def test_truncated_json_is_closed():
    result = _service()._parse_structured_plan('{"phases": [{"name": "Framing"}', "test")
    assert result["success"] is True
    assert result["plan"]["phases"] == [{"name": "Framing"}]


def test_unparseable_plan_falls_back_to_next_provider():
    service = _service()
    calls = []

    async def groq(prompt):
        calls.append("groq")
        return {"success": False, "error": "Failed to parse structured plan"}

    async def gemini(prompt):
        calls.append("gemini")
        return {"success": True, "plan": {"phases": []}, "source": "gemini"}

    service._generate_with_groq = groq
    service._generate_with_gemini = gemini

    result = asyncio.run(service.generate_construction_plan("a small cabin"))
    assert calls == ["groq", "gemini"]
    assert result["source"] == "gemini"


def test_refine_sends_current_plan_and_change_through_the_chain():
    service = _service()
    prompts = []

    async def groq(prompt):
        prompts.append(prompt)
        return {"success": True, "plan": {"project_structure": {"rooms": []}}, "source": "groq"}

    service._generate_with_groq = groq
    structure = {"layout": {"length": 20, "width": 10, "room": "Studio"}, "rooms": [{"name": "Studio"}]}
    result = asyncio.run(service.refine_floor_plan(structure, "add a bathroom"))
    assert result["source"] == "groq"
    assert "REQUESTED CHANGE: add a bathroom" in prompts[0]
    assert '"room":"Studio"' in prompts[0]
