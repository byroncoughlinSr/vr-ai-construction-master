"""Plan parsing and provider fallback in AIPlanningService (no network calls)."""

import asyncio
import json

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


def test_refine_asks_again_when_the_room_list_is_missing():
    service = _service()
    replies = [
        {"scope": "floor_plan", "project_structure": {"layout": {"room": "Studio"}}},
        {"scope": "floor_plan", "project_structure": {"layout": {"room": "Studio"}, "rooms": [{"name": "Studio"}]}},
    ]

    async def groq(prompt):
        return {"success": True, "plan": replies.pop(0), "source": "groq"}

    service._generate_with_groq = groq
    structure = {"layout": {"length": 20, "width": 10, "room": "Studio"}, "rooms": [{"name": "Studio"}]}
    result = asyncio.run(service.refine_floor_plan(structure, "no door to the hall"))
    assert result["plan"]["project_structure"]["rooms"] == [{"name": "Studio"}]
    assert replies == []


def test_refine_prompt_lists_every_doorway_and_how_to_remove_one():
    site = {"doorways": [["Kitchen", "Hallway"]]}
    prompt = _service()._build_refine_prompt({"layout": None, "rooms": []}, "wall it off", site)
    assert '"doorways":[["Kitchen","Hallway"]]' in prompt
    for field in ('"no_door_to"', '"solid_walls"', '"open_to"', '"renames"', '"window": false'):
        assert field in prompt


# What Groq's JSON mode rejected (json_validate_failed), shapes seen in the log.
_LAYOUT = '"layout":{"length":20,"width":10,"split":"x","parts":[{"size":10,"room":"Kitchen"},{"size":10,"room":"Den"}]'
_ROOMS = '"rooms":[{"name":"Kitchen","outside_doors":[{"side":"back","style":"sliding_glass"}]},{"name":"Den"}]'


def test_groq_rooms_written_inside_the_layout_are_moved_back():
    rejected = '{"scope":"floor_plan","project_structure":{' + _LAYOUT + ',' + _ROOMS + '"}}'
    plan = json.loads(AIPlanningService._salvage_groq_json(rejected))
    structure = plan["project_structure"]
    assert [r["name"] for r in structure["rooms"]] == ["Kitchen", "Den"]
    assert "rooms" not in structure["layout"]
    assert structure["rooms"][0]["outside_doors"][0]["style"] == "sliding_glass"


def test_groq_rooms_written_after_the_structure_closed_are_moved_back():
    rejected = '{"scope":"floor_plan","project_structure":{' + _LAYOUT + '}},' + _ROOMS + '"}}}'
    plan = json.loads(AIPlanningService._salvage_groq_json(rejected))
    assert [r["name"] for r in plan["project_structure"]["rooms"]] == ["Kitchen", "Den"]
    assert "rooms" not in plan


def test_groq_salvage_leaves_other_text_to_the_repair_pipeline():
    assert AIPlanningService._salvage_groq_json("not json at all") == "not json at all"


def test_groq_answer_rejected_by_json_mode_is_repaired_or_asked_again():
    import httpx
    from groq import BadRequestError

    def rejected(text):
        response = httpx.Response(400, request=httpx.Request("POST", "https://groq.test"))
        return BadRequestError("json_validate_failed", response=response,
                               body={"error": {"code": "json_validate_failed", "failed_generation": text}})

    good = '{"scope":"floor_plan","project_structure":{' + _LAYOUT + '},' + _ROOMS + '}}'
    answers = [rejected("{ beyond repair"), rejected(good[:-1] + '"}')]
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            raise answers[len(calls) - 1]

    service = _service()
    service.groq_client = type("Client", (), {"chat": type("Chat", (), {"completions": Completions()})()})()
    result = asyncio.run(service._generate_with_groq("prompt"))
    assert len(calls) == 2
    assert result["success"] is True
    assert [r["name"] for r in result["plan"]["project_structure"]["rooms"]] == ["Kitchen", "Den"]


def test_groq_request_over_the_token_limit_is_retried_with_a_smaller_answer():
    import httpx
    from groq import APIStatusError

    over_limit = APIStatusError(
        "Error code: 413 - Request too large ... tokens per minute (TPM): Limit 8000, Requested 8258",
        response=httpx.Response(413, request=httpx.Request("POST", "https://groq.test")), body=None,
    )
    good = '{"scope":"floor_plan","project_structure":{' + _LAYOUT + '},' + _ROOMS + '}}'
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs["max_tokens"])
            if len(calls) == 1:
                raise over_limit
            message = type("Message", (), {"content": good})()
            return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

    service = _service()
    service.groq_client = type("Client", (), {"chat": type("Chat", (), {"completions": Completions()})()})()
    result = asyncio.run(service._generate_with_groq("prompt"))
    assert calls == [4096, 4096 - 258 - 256]
    assert result["success"] is True


def test_both_prompts_describe_furniture():
    service = _service()
    planning = service._build_planning_prompt("a furnished cottage", None, None, None)
    assert '"furniture" inside "project_structure"' in planning
    furniture = {"rooms": {"Den": [{"type": "sofa"}]}}
    refine = service._build_refine_prompt({"layout": None, "rooms": [], "furniture": furniture}, "add a piano", {})
    assert 'CURRENT FURNITURE (JSON by room; null means none yet):\n{"rooms":{"Den":[{"type":"sofa"}]}}' in refine
    assert '{"scope": "furniture", "furniture":' in refine
    assert '"kitchen island"' in refine
