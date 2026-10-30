import asyncio
import logging
import json
import re
import time
from typing import Optional, Dict, Any, List
import anthropic
import ollama
import google.generativeai as genai
from groq import APIStatusError, BadRequestError, Groq

from ..config import settings
from .layout_check import layout_problems
from .vr_furniture import shown_furniture
from .vr_geometry_service import LayoutError, layout_as_rects

logger = logging.getLogger(__name__)


# The outside of the house, as both planning prompts describe it to the AI. The
# backend cleans the result with vr_exterior.exterior_spec — keep them in step.
EXTERIOR_FORMAT = """{"roof": {"style": "gable"|"hip"|"flat"|"shed", "material": "clay_tile"|"concrete_tile"|"asphalt_shingle"|"metal"|"slate"|"wood_shake", "color": "#rrggbb", "pitch": 5, "overhang": 1.5},
 "walls": {"material": "stucco"|"siding"|"brick"|"stone"|"wood"|"paint", "color": "#rrggbb"},
 "trim": {"color": "#rrggbb"},
 "ground": {"material": "grass"|"gravel"|"dirt"|"sand"},
 "landscape": [items]}
- Colors are hex (beige stucco is about #e3d4b6, terracotta tile #b5562f). Leave out a part nobody asked for.
- "pitch" is the roof's rise per 12 of run (Spanish/Mediterranean tile roofs are low, 3-5; most roofs 4-8). "overhang" is in feet.
- Positions are in feet in the floor plan's coordinates: x runs left to right from the footprint's left edge (0) to its "length"; z runs from the street side (0) to the back ("width"). The front yard is negative z (up to about -30), the back yard is beyond "width", the side yards are x < 0 and x > "length". Open parts of the footprint are yard too. Never put an item inside the house's rooms.
- Items:
  - plants and rocks at a point: {"type": "tree"|"pine"|"palm"|"shrub"|"rock", "plant": "what it is, in the person's words: 'coral rose', 'Japanese maple', 'hydrangea', 'boxwood', 'lavender', 'agave', ...", "x": n, "z": n, "height": ft, "width": ft, "flower_color": "#rrggbb"} (all but type, x, z optional; "color" is the leaves'). Name the plant whenever the request does; SITE "plant_models" are plants with a 3D model: use that exact name.
  - areas: {"type": "lawn"|"path"|"driveway"|"patio"|"deck"|"flower_bed"|"pool", "x": center x, "z": center z, "width": size along x, "depth": size along z, "material": "concrete"|"pavers"|"brick"|"stone"|"tile"|"gravel"|"asphalt"|"wood"} (material optional; a flower bed may name its "plant" ("tulips") and "color" is its flowers' color). A path or driveway may instead run in a line: {"type": "path", "from": {"x": n, "z": n}, "to": {"x": n, "z": n}, "width": ft}.
  - lines: {"type": "hedge"|"fence"|"garden_wall", "from": {"x": n, "z": n}, "to": {"x": n, "z": n}, "height": ft, "style": "picket"|"privacy"}.
  - Keep plants and rocks outside every room's rectangle (when the SITE lists them): "by" or "on each side of the front door" means the SITE's front_door "beside_it" spots (4 ft out from the door's wall, 5 ft to either side). A walkway to the front door runs from the street (z about -25) to the door. Space plants sensibly (trees 10+ ft apart, shrubs 3-4 ft apart); for "a row of" or "both sides of", list each plant."""


# The floor plan's "layout", as every planning prompt describes it: one rectangle per
# room. vr_geometry_service builds it (is_rect_layout) and layout_check.layout_problems
# checks it — keep them in step.
RECT_LAYOUT_FORMAT = """{"entry": "Room Name", "rects": [{"room": "Room Name", "x": 0, "z": 0, "length": 0, "width": 0}], "notes": ["..."]}
- One rectangle per room, in feet, on the plan seen from above: "x" is its left edge, "z" its front edge, "length" its size left to right, "width" its size front to back. x runs left to right; z runs from the street side (z = 0, the front-most edge of the house) toward the back yard.
- Directions: "to the left" means smaller x, "to the right" larger x; "behind", "past", "down the hall", "at the back" and "toward the backyard" mean larger z; "in front of", "toward the street" and "sticks out" (past the front of the house) mean smaller z.
- Use the sizes the description gives. "10 x 13" names both sides but not their direction: turn the room whichever way lines it up with its neighbours.
- Rooms never overlap. Rooms that touch share an edge exactly: one room's x + length is the next room's x (or its z + width is the next room's z). Rooms are only adjacent where their edges meet, and a doorway needs at least 4 ft of shared edge.
- Work it out in order: the entry on the street side first, then its neighbours, then theirs, getting each corner by adding up the sizes before it. Then check every pair of rooms for overlaps and every doorway for a shared edge.
- Whatever of the house's bounding box no room covers is outdoors: that is how the house gets an L, U or T shape, a courtyard or an inset porch. Inside the house leave no gap by accident: make the hallway or a room bigger, or add a closet.
- A room that is not a rectangle (an L-shaped hallway) is two rooms, e.g. "Hallway" and "Hallway 2", each listing the other in "open_to" so no wall is drawn between them.
- If the description can't fit as given (sizes that don't add up, a room that can't touch the one it should), make the smallest change that works and say so in "notes" ("Hallway narrowed to 3.5 ft to fit between the office and the kitchen"); leave "notes" out when nothing was changed.
- "entry" names the room the front door opens into; no room may be in front of it (between it and the street). It is usually at z = 0, but another room, such as a garage, may stick out toward the street beside it: then that room starts at z = 0 and the entry further back.
- More than one storey: give each upstairs rectangle "level": 1 (2 for a third floor; the ground floor is 0 and needs no "level"). Each floor is planned on its own (no overlaps on the same level) within the floor below's outline, in the same x/z. The stairs are a room named "Stairs" (about 4 x 12 ft, more is fine) on the lower floor with a room on the floor above over it, such as a "Landing" or hall, which the upstairs rooms open off. Rooms on different levels may sit over each other; doorways only join rooms on the same level."""


# Furniture, as both planning prompts describe it. The backend cleans the result with
# vr_furniture.furniture_spec and places the pieces itself — keep them in step.
FURNITURE_FORMAT = """{"auto": true|false, "rooms": {"<exact room name>": [items]}}
- "auto": true furnishes every room NOT in "rooms" as that kind of room usually is (bedroom: bed, nightstands, dresser; living: sofa, coffee table, armchair, TV; dining: table and chairs; kitchen: counters, fridge, stove, island; bathroom: toilet, vanity, tub). Use it for "furnish the house". A room in "rooms" gets exactly its items ([] = empty).
- Item: {"type": "sofa"|"loveseat"|"sectional"|"armchair"|"recliner"|"dining chair"|"office chair"|"bar stool"|"bench"|"dining table"|"round table"|"coffee table"|"side table"|"console table"|"desk"|"bed"|"crib"|"nightstand"|"dresser"|"wardrobe"|"bookshelf"|"tv stand"|"sideboard"|"piano"|"counter"|"kitchen island"|"refrigerator"|"stove"|"toilet"|"vanity"|"bathtub"|"shower"|"washer"|"dryer"|"rug"|"floor lamp"|"potted plant", "name": "the person's words ('navy velvet sofa')", "color": "#rrggbb", "material": "oak"|"walnut"|..., "seats": n, "size": "king"|"queen"|"full"|"twin", "count": n, "place": "front"|"back"|"left"|"right"|"center"|"corner", "corner": "front-left"|"front-right"|"back-left"|"back-right", "between": [type, type], "style": "kitchen style name", "sink"/"range"/"uppers": true|false, "x": ft, "rotation": degrees, "z": ft, "facing": side, "width"/"depth"/"height": ft}; only "type" is required. "seats" = chairs round a table or stools at an island (don't list them separately); "size" is a bed's.
- Pieces are placed automatically (against free walls, clear of doorways and windows; nightstands by the bed, coffee table before the sofa). "place" picks the wall ("front" = street side; an island backs onto that side, even one open to the next room, seats facing in) or center/corner; "facing" = the side its front (an island's seats) faces, so "turn it around" flips it; an island with "place" and "facing" both the open side has its stools in the next room ("stools on the family room side"); a counter run has the sink, and the range unless a "stove" is listed; a stove with "corner" sits diagonally across it; a counter with "between": ["stove", "refrigerator"] runs from one to the other ("width" sets that gap: the fridge moves; another counter, no "place", fills the wall past it); give "x"/"z" (feet from the room's front-left corner to the piece's centre) only for an exact spot, with "rotation" to turn it any way (degrees its front faces: 0 the back, 90 the left, 180 the street, 270 the right). To remove one stool or chair lower "seats"; "sink": false / "range": false / "uppers": false take those out of a counter ("sink": true on an island puts the sink there); to move a piece change its "place"/"corner" or give "x"/"z"; a removed piece is simply left out of the list. SITE "furniture_models" have a 3D model from a photo: use that exact "name". SITE "kitchen_styles" are saved kitchen looks: when the request names one ("in Farmhouse kitchen style"), put "style": "<that exact name>" on the kitchen's counters, island, stove and refrigerator."""


class AIPlanningService:
    """Service for construction planning using LLM models."""

    def __init__(self):
        self.claude_available = False
        self.groq_available = False
        self._ollama_up = False
        self._ollama_checked_at = 0.0
        self.gemini_available = False

        # Claude (primary planner) if an API key is set
        self.claude_client = None
        if settings.anthropic_api_key:
            try:
                self.claude_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
                self.claude_available = True
                logger.info(f"Claude API initialized (model: {settings.anthropic_model})")
            except Exception as e:
                logger.warning(f"Failed to initialize Claude API: {e}")

        # Groq client (first fallback) if API key is available
        self.groq_client = None
        if settings.groq_api_key:
            try:
                self.groq_client = Groq(api_key=settings.groq_api_key)
                self.groq_available = True
                logger.info(f"Groq API initialized (model: {settings.groq_model})")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq API: {e}")

        # Initialize Ollama client with custom host. Generation can take minutes, so
        # only the availability probe (which runs on the event loop) gets a timeout.
        self.ollama_client = ollama.Client(host=settings.ollama_url)
        self._ollama_probe_client = ollama.Client(host=settings.ollama_url, timeout=3.0)

        # Initialize Gemini if API key is available
        if settings.gemini_api_key:
            try:
                genai.configure(api_key=settings.gemini_api_key)
                self.gemini_model = genai.GenerativeModel(settings.gemini_model)
                self.gemini_available = True
                logger.info(f"Gemini API initialized (model: {settings.gemini_model})")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini API: {e}")

        self._probe_ollama()

    # Seconds between re-checks while Ollama is down.
    OLLAMA_REPROBE_S = 30.0

    def _probe_ollama(self) -> None:
        self._ollama_checked_at = time.monotonic()
        try:
            self._ollama_probe_client.list()
            self._ollama_up = True
            logger.info(f"Ollama service is available at {settings.ollama_url} (model: {settings.ollama_model})")
        except Exception as e:
            self._ollama_up = False
            logger.warning(f"Ollama service not available at {settings.ollama_url}: {e}")

    @property
    def ollama_available(self) -> bool:
        # Re-probe while down, so an Ollama started after uvicorn is picked up
        # without restarting the backend.
        if not self._ollama_up and time.monotonic() - self._ollama_checked_at > self.OLLAMA_REPROBE_S:
            self._probe_ollama()
        return self._ollama_up

    async def generate_construction_plan(
        self,
        project_description: str,
        budget: Optional[float] = None,
        timeline_weeks: Optional[int] = None,
        constraints: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive construction plan using AI.

        Args:
            project_description: Description of the construction project
            budget: Project budget in dollars
            timeline_weeks: Desired timeline in weeks
            constraints: List of project constraints

        Returns:
            Dict containing structured construction plan
        """
        started = time.monotonic()
        prompt = self._build_planning_prompt(
            project_description, budget, timeline_weeks, constraints
        )
        result = await self._run_provider_chain(prompt, "Plan")
        result = await self._check_floor_plan(
            result,
            self._project_brief(project_description, budget, timeline_weeks, constraints),
            settings.planning_timeout_seconds - (time.monotonic() - started),
        )
        # Groq sometimes answers a small building (a one-room shed) with the floor
        # plan alone: plan its construction for that layout in a second call.
        plan = result.get("plan") or {}
        structure = plan.get("project_structure") or {}
        if result.get("success") and not plan.get("phases") and structure:
            logger.warning("Plan came back without construction phases — planning them for its floor plan")
            remaining = settings.planning_timeout_seconds - (time.monotonic() - started)
            try:
                construction = await asyncio.wait_for(
                    self.plan_construction(
                        project_description, structure, budget, timeline_weeks, constraints
                    ),
                    timeout=max(remaining, 1),
                )
                self._merge_construction(plan, construction.get("plan") or {})
            except Exception as e:
                logger.warning(f"Plan saved without construction phases: {e}")
        return result

    async def plan_construction(
        self,
        project_description: str,
        structure: Dict[str, Any],
        budget: Optional[float] = None,
        timeline_weeks: Optional[int] = None,
        constraints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Phases, tasks, materials, cost and duration for an existing floor plan
        (``project_structure``, feet), without designing the house again."""
        prompt = self._build_construction_prompt(
            project_description, structure, budget, timeline_weeks, constraints
        )
        return await self._run_provider_chain(prompt, "Construction plan")

    @staticmethod
    def _merge_construction(plan: Dict[str, Any], construction: Dict[str, Any]) -> None:
        """Copy a ``plan_construction`` answer into ``plan``, if it has phases."""
        if not construction.get("phases"):
            logger.warning("Construction plan came back without phases too")
            return
        plan["phases"] = construction["phases"]
        for key in ("total_cost", "total_duration_weeks"):
            if construction.get(key):
                plan[key] = construction[key]
        if construction.get("material_list") and not plan.get("material_list"):
            plan["material_list"] = construction["material_list"]

    async def refine_floor_plan(
        self, structure: Dict[str, Any], instruction: str, site: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Apply a spoken/typed change ("make the kitchen bigger", "tile roof") to a house.

        ``structure`` is a ``project_structure`` (``layout`` + ``rooms`` + ``exterior``,
        feet); ``site`` is ``floor_plan_service.site_summary``. Returns the provider
        result; on success ``plan["scope"]`` says what changed: ``"exterior"`` or
        ``"furniture"`` (only ``plan["exterior"]`` / ``plan["furniture"]``, the rooms
        that change), else ``plan["project_structure"]`` is the whole revised plan.
        """
        started = time.monotonic()
        prompt = self._build_refine_prompt(structure, instruction, site)
        result = await self._run_provider_chain(prompt, "Floor plan refinement", edit=True)
        # Groq sometimes answers a floor-plan change with only the "layout" (the
        # room list lost to its miscounted braces): unusable, so ask once more.
        plan = result.get("plan") or {}
        revised = plan.get("project_structure")
        if (
            str(plan.get("scope") or "").strip().lower() not in ("exterior", "furniture")
            and isinstance(revised, dict) and revised.get("layout") is not None
            and not isinstance(revised.get("rooms"), list)
        ):
            logger.warning("Refined floor plan came back without its room list — asking again")
            result = await self._run_provider_chain(prompt, "Floor plan refinement", edit=True)
        if str((result.get("plan") or {}).get("scope") or "").strip().lower() not in ("exterior", "furniture"):
            result = await self._check_floor_plan(
                result,
                f"REQUESTED CHANGE (already applied below): {instruction}\n",
                settings.planning_timeout_seconds - (time.monotonic() - started),
                edit=True,
            )
        return result

    # Below this many seconds of the planning budget, a floor plan's problems are
    # shown with the house rather than sent back to the planner.
    FIX_MIN_SECONDS = 20.0

    async def _check_floor_plan(
        self, result: Dict[str, Any], brief: str, budget_s: float, edit: bool = False,
    ) -> Dict[str, Any]:
        """Send a floor plan with problems (``layout_check.layout_problems``: overlaps,
        sizes that don't add up, rooms left out, doorways between rooms that don't
        touch) back to the planner once, and keep whichever version has fewer.
        What is still wrong is shown with the house (``geometry.notes``)."""
        plan = result.get("plan") or {}
        structure = plan.get("project_structure")
        if not result.get("success") or not isinstance(structure, dict):
            return result
        problems = layout_problems(structure)
        if not problems:
            return result
        if budget_s < self.FIX_MIN_SECONDS:
            logger.warning(f"📐 Floor plan has {len(problems)} problem(s) and no time is left to fix them")
            return result
        logger.warning(
            f"📐 Floor plan has {len(problems)} problem(s) — asking for a fix: " + "; ".join(problems[:3])
        )
        prompt = self._build_fix_prompt(brief, structure, problems)
        try:
            fixed = await asyncio.wait_for(self._run_provider_chain(prompt, "Floor plan fix", edit=edit), timeout=budget_s)
        except Exception as e:
            logger.warning(f"📐 Floor plan fix failed, keeping the first answer: {e}")
            return result
        answer = fixed.get("plan") or {}
        revised = answer.get("project_structure")
        if not (isinstance(revised, dict) and revised.get("layout")) and isinstance(answer.get("layout"), dict):
            revised = answer  # the layout without the "project_structure" wrapper
        if not (isinstance(revised, dict) and isinstance(revised.get("layout"), dict)):
            logger.warning(
                "📐 Floor plan fix came back without a layout — keeping the first answer: "
                + str(fixed.get("raw_response") or fixed.get("error") or "")[:300]
            )
            return result
        candidate = {**structure, "layout": revised["layout"], "rooms": self._merge_rooms(
            structure.get("rooms"), revised.get("rooms"))}
        left = layout_problems(candidate)
        if len(left) < len(problems):
            plan["project_structure"] = candidate
            logger.info(f"📐 Floor plan fixed: {len(problems)} → {len(left)} problem(s)")
        else:
            logger.warning(f"📐 Floor plan fix no better ({len(left)} problem(s)) — keeping the first answer")
        return result

    @staticmethod
    def _merge_rooms(old: Any, new: Any) -> List[Any]:
        """The fixed room list: the fix's rooms by name, in place of the old ones; rooms
        the fix leaves out are kept as they were (a fix often sends only the layout)."""
        old = [r for r in old or [] if isinstance(r, dict)]
        new = [r for r in new or [] if isinstance(r, dict) and r.get("name")] if isinstance(new, list) else []
        if not new:
            return old
        by_name = {str(r["name"]).strip().lower(): r for r in new}
        merged = [by_name.pop(str(r.get("name", "")).strip().lower(), r) for r in old]
        return merged + list(by_name.values())

    def _build_fix_prompt(self, brief: str, structure: Dict[str, Any], problems: List[str]) -> str:
        """Prompt for correcting a floor plan's ``problems`` (``layout_problems``)."""
        layout = structure.get("layout")
        try:
            layout = layout_as_rects(layout)
        except LayoutError:
            pass
        current = json.dumps({"layout": layout, "rooms": structure.get("rooms", [])}, separators=(",", ":"))
        listed = "\n".join(f"- {p}" for p in problems)
        return f"""You are a residential architect. The floor plan below was drawn for this house but has problems; fix them.

{brief}
FLOOR PLAN (JSON, all sizes in feet):
{current}

PROBLEMS:
{listed}

Layout format:
{RECT_LAYOUT_FORMAT}

Fix every problem with the smallest change that still follows the description; keep everything else (room names, materials, "connects_to", "open_to", "no_door_to", "solid_walls", windows, bay windows, outside doors) as it is. Each room's "dimensions" must match its rectangle. If a size from the description can't be kept, change it and say so in "notes".

Reply with ONLY a JSON object (no markdown, no explanation): {{"project_structure": {{"layout": {{...}}, "rooms": [...]}}}} with the whole layout; "rooms" needs only the rooms you change (the rest are kept as they are)."""

    # Provider order: a new house goes to Claude first; a change to an existing one
    # (refine, and its floor-plan fix) to Groq first, Claude last.
    PLAN_ORDER = ("Claude", "Groq", "Ollama", "Gemini")
    EDIT_ORDER = ("Groq", "Ollama", "Gemini", "Claude")

    async def _run_provider_chain(self, prompt: str, what: str, edit: bool = False) -> Dict[str, Any]:
        """Send ``prompt`` to each provider in ``PLAN_ORDER`` (``EDIT_ORDER`` for a
        change to an existing house) until one returns output that parses into a plan."""
        # One time budget for the whole chain, so falling back from a slow Groq
        # to a slower Ollama can't outlast the client waiting for the plan.
        deadline = time.monotonic() + settings.planning_timeout_seconds
        # Availability is read lazily: checking Ollama is a network probe, wasted
        # whenever an earlier provider answers first.
        known = {
            "Claude": (lambda: self.claude_available, self._generate_with_claude),
            "Groq": (lambda: self.groq_available, self._generate_with_groq),
            "Ollama": (lambda: self.ollama_available, self._generate_with_ollama),
            "Gemini": (lambda: self.gemini_available, self._generate_with_gemini),
        }
        providers = [(name, *known[name]) for name in (self.EDIT_ORDER if edit else self.PLAN_ORDER)]
        last_error: Optional[Exception] = None
        failures: List[str] = []
        for name, available, generate in providers:
            if not available():
                continue
            remaining = deadline - time.monotonic()
            if remaining < 5:
                logger.warning(f"Planning time budget used up before trying {name}")
                break
            try:
                result = await asyncio.wait_for(generate(prompt), timeout=remaining)
                if result.get("success"):
                    logger.info(f"🧠 {what} generated by {name}")
                    return result
                # Unparseable output: another model may do better.
                last_error = Exception(f"{name}: {result.get('error', 'invalid plan')}")
                logger.warning(f"{last_error}; trying next provider")
            except asyncio.TimeoutError:
                last_error = Exception(f"{name} planning timed out after {remaining:.0f}s")
                logger.warning(f"{last_error}; trying next provider")
            except Exception as e:
                last_error = Exception(f"{name}: {e}")
                logger.warning(f"{name} planning failed, trying next provider: {e}")
            failures.append(str(last_error).split("\n")[0][:200])

        if failures:
            # Name every provider's failure: the last one alone (often a fallback's
            # bad key) hides why the primary planner failed.
            raise Exception("All planners failed — " + "; ".join(failures))
        raise Exception("No AI services available for planning")

    async def _generate_with_claude(self, prompt: str) -> Dict[str, Any]:
        """Generate a construction plan with Claude (primary planner)."""
        logger.info(f"Generating construction plan with Claude ({settings.anthropic_model})...")
        try:
            # Streamed: a big house with thinking runs long, and streaming keeps
            # the SDK from refusing a large max_tokens. A safety-classifier decline
            # is re-run server-side on Anthropic's recommended model ("default").
            async def _stream():
                async with self.claude_client.beta.messages.stream(
                    model=settings.anthropic_model,
                    max_tokens=32000,
                    output_config={"effort": settings.anthropic_effort},
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    return await stream.get_final_message()

            message = await asyncio.wait_for(_stream(), timeout=settings.anthropic_timeout_seconds)
        except asyncio.TimeoutError:
            logger.error(f"Claude generation timed out after {settings.anthropic_timeout_seconds:.0f}s")
            raise Exception("Claude generation timed out")
        except anthropic.AuthenticationError as e:
            # Loud, not a quiet fallback: an expired or revoked key otherwise only
            # shows up as Groq's worse layouts.
            logger.error(f"❌ Claude API key rejected (expired or revoked?): {e}")
            raise
        except anthropic.APIError as e:
            logger.error(f"Claude generation failed: {e}")
            raise

        if message.stop_reason == "refusal":
            raise Exception(f"Claude declined the request ({getattr(message.stop_details, 'category', None)})")
        if message.stop_reason == "max_tokens":
            logger.warning("Claude hit max_tokens — the plan may be cut off; repairing what came back")

        content = "".join(b.text for b in message.content if b.type == "text")
        usage = message.usage
        logger.info(
            f"Claude response received ({message.model}, {usage.input_tokens} in / "
            f"{usage.output_tokens} out tokens, {message.id})"
        )
        return self._parse_structured_plan(content, "claude")

    async def _generate_with_groq(self, prompt: str) -> Dict[str, Any]:
        """Generate construction plan using the Groq cloud API (first fallback)."""
        try:
            logger.info(f"Generating construction plan with Groq ({settings.groq_model})...")

            loop = asyncio.get_running_loop()

            max_tokens = 4096
            extra: Dict[str, Any] = {}

            def _groq_generate():
                return self.groq_client.chat.completions.create(
                    model=settings.groq_model,
                    messages=[{'role': 'user', 'content': prompt}],
                    temperature=0.7,
                    top_p=0.9,
                    max_tokens=max_tokens,
                    response_format={'type': 'json_object'},
                    **extra,
                )

            # Groq is fast; a short timeout is plenty. JSON mode rejects a whole
            # answer over one bad character but sends the rejected text back with the
            # error: repair that like any other, and if it is beyond repair ask once more.
            for attempt in (1, 2):
                try:
                    response = await asyncio.wait_for(
                        loop.run_in_executor(None, _groq_generate),
                        timeout=120.0
                    )
                    break
                except BadRequestError as e:
                    failed = ((getattr(e, "body", None) or {}).get("error") or {}).get("failed_generation")
                    if not failed:
                        # Nothing written at all: a reasoning model (gpt-oss) can spend
                        # the whole max_tokens thinking about a big house. Ask again
                        # with less thinking so the answer fits.
                        if attempt == 2:
                            raise
                        if "gpt-oss" in settings.groq_model:
                            extra["reasoning_effort"] = "low"
                        logger.warning("Groq's JSON check failed on an empty answer — asking Groq again")
                        continue
                    logger.warning("Groq's JSON check failed — repairing its output instead")
                    result = self._parse_structured_plan(self._salvage_groq_json(failed), "groq")
                    if result.get("success") or attempt == 2:
                        return result
                    logger.warning("Groq's output was beyond repair — asking Groq again")
                except APIStatusError as e:
                    # The per-minute token limit counts max_tokens as well as the
                    # prompt, so a long house can be refused outright (413): ask
                    # again with room for a shorter answer if one would still fit.
                    # Groq's count is an estimate (a retry cut by exactly the
                    # overrun was still ~90 over), hence the margin.
                    over = self._groq_tokens_over(e)
                    if attempt == 2 or over is None or max_tokens - over - 256 < 2048:
                        raise
                    max_tokens -= over + 256
                    logger.warning(f"Groq token limit exceeded by {over} — retrying with max_tokens={max_tokens}")
                    continue

            content = response.choices[0].message.content
            logger.info("Groq response received successfully")

            # Reuse the shared repair pipeline as a safety net (JSON mode should be clean)
            return self._parse_structured_plan(content, "groq")

        except asyncio.TimeoutError:
            logger.error("Groq generation timed out after 120 seconds")
            raise Exception("Groq generation timed out")
        except Exception as e:
            logger.error(f"Groq generation failed: {e}")
            raise

    @staticmethod
    def _groq_tokens_over(error: Exception) -> Optional[int]:
        """By how many tokens a request went over Groq's per-minute limit, from the
        413 "Limit 8000, Requested 8258" message; None for any other error."""
        if getattr(error, "status_code", None) != 413:
            return None
        match = re.search(r"Limit (\d+), Requested (\d+)", str(error))
        return int(match.group(2)) - int(match.group(1)) if match else None

    @staticmethod
    def _salvage_groq_json(text: str) -> str:
        """Repair the JSON Groq's JSON mode rejected. Seen on long floor plans: the
        model miscounts its braces around "rooms" — leaving "layout" open so "rooms"
        lands inside it, or closing "project_structure" early so "rooms" lands at the
        top — then ends with a stray quote ('...]"}}}' or '...]"}}'). Drop the quote,
        close what is still open, and put "rooms" back beside "layout". Anything
        else goes to the usual repair pipeline unchanged."""
        fixed = re.sub(r'([\]}])"(\s*\}+\s*)$', r'\1\2', text.strip())
        obj = None
        for closing in ("", "}", "}}", "}}}"):
            try:
                obj, _ = json.JSONDecoder().raw_decode(fixed + closing)
                break
            except ValueError:
                continue
        if not isinstance(obj, dict):
            return text
        structure = obj.get("project_structure")
        if isinstance(structure, dict) and "rooms" not in structure:
            layout = structure.get("layout")
            if isinstance(layout, dict) and isinstance(layout.get("rooms"), list):
                structure["rooms"] = layout.pop("rooms")
            elif isinstance(obj.get("rooms"), list):
                structure["rooms"] = obj.pop("rooms")
        return json.dumps(obj)

    async def _generate_with_ollama(self, prompt: str) -> Dict[str, Any]:
        """Generate construction plan using Ollama with reduced memory footprint."""
        try:
            logger.info("Generating construction plan with Ollama...")

            # Run Ollama in executor to avoid blocking; the caller's deadline bounds it
            loop = asyncio.get_running_loop()
            
            def _ollama_generate():
                return self.ollama_client.chat(
                    model=settings.ollama_model,
                    messages=[{
                        'role': 'user',
                        'content': prompt
                    }],
                    format='json',  # constrain output to JSON, like Groq's json_object mode
                    options={
                        'temperature': 0.7,
                        'top_p': 0.9,
                        'num_predict': 4096,  # Enough for full JSON response
                        'num_ctx': 6144,      # Context window: prompt (~500t) + response (~4096t)
                        'num_thread': 4       # Limit CPU threads
                    }
                )
            
            response = await loop.run_in_executor(None, _ollama_generate)

            content = response['message']['content']
            logger.info("Ollama response received successfully")

            # Parse the structured response
            return self._parse_structured_plan(content, "ollama")

        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise

    async def _generate_with_gemini(self, prompt: str) -> Dict[str, Any]:
        """Generate construction plan using Gemini API."""
        try:
            logger.info("Generating construction plan with Gemini...")

            # The SDK call is blocking; keep it off the event loop.
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: self.gemini_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    top_p=0.9,
                    # The plan (phases, materials, layout tree) needs room; 2048 truncated it.
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                )
            ))

            content = response.text
            logger.info("Gemini response received")

            # Parse the structured response
            return self._parse_structured_plan(content, "gemini")

        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            raise

    async def generate_complete_project(
        self,
        project_description: str,
        budget: Optional[float] = None,
        timeline_weeks: Optional[int] = None,
        constraints: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generate a complete project including name, structure, plan, materials, and timeline.
        This is the main entry point for creating a full project from a single prompt.
        """
        try:
            # Name and plan are independent; ask for both at once.
            project_name, plan_result = await asyncio.gather(
                self._generate_project_name(project_description),
                self.generate_construction_plan(
                    project_description, budget, timeline_weeks, constraints
                ),
            )
            
            if not plan_result.get("success"):
                return plan_result
            
            # Extract structured data
            plan = plan_result.get("plan", {})
            
            return {
                "success": True,
                "project_name": project_name,
                "description": project_description,
                "plan": plan,
                "source": plan_result.get("source"),
                "metadata": {
                    "total_cost": plan.get("total_cost", 0),
                    "total_duration_weeks": plan.get("total_duration_weeks", 0),
                    "phases_count": len(plan.get("phases", [])),
                    "materials_count": len(plan.get("material_list", []))
                }
            }
            
        except Exception as e:
            logger.error(f"Complete project generation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _generate_project_name(self, description: str) -> str:
        """Generate a creative, professional project name from the description."""
        prompt = f"""Generate a creative, professional project name for this construction project:

"{description}"

Requirements:
- Short and memorable (2-4 words)
- Professional and marketable
- Reflects the key features or style
- No generic names like "Project 1" or "New House"

Return ONLY the project name, nothing else."""

        try:
            name = None

            # Priority chain: Groq (primary) -> Ollama -> Gemini
            if self.groq_available:
                try:
                    loop = asyncio.get_running_loop()
                    response = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: self.groq_client.chat.completions.create(
                                model=settings.groq_model,
                                messages=[{'role': 'user', 'content': prompt}],
                                temperature=0.8,
                                # Reasoning models (gpt-oss) spend tokens before answering.
                                max_tokens=512,
                            )
                        ),
                        timeout=15.0
                    )
                    name = (response.choices[0].message.content or "").strip().strip('"\'') or None
                except Exception as groq_err:
                    logger.warning(f"Groq name generation failed: {groq_err}")

            if name is None and self.ollama_available:
                try:
                    loop = asyncio.get_running_loop()
                    response = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: self.ollama_client.chat(
                                model=settings.ollama_model,
                                messages=[{'role': 'user', 'content': prompt}],
                                options={'temperature': 0.8, 'num_predict': 50, 'num_ctx': 1024}
                            )
                        ),
                        timeout=15.0
                    )
                    name = response['message']['content'].strip().strip('"\'') or None
                except Exception as ollama_err:
                    logger.warning(f"Ollama name generation failed: {ollama_err}")

            if name is None and self.gemini_available:
                loop = asyncio.get_running_loop()
                response = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: self.gemini_model.generate_content(prompt)),
                    timeout=15.0
                )
                name = response.text.strip().strip('"\'') or None

            if name is None:
                # Fallback: extract key words
                words = description.split()[:3]
                name = " ".join(words).title() + " Project"
            
            logger.info(f"Generated project name: {name}")
            return name
            
        except Exception as e:
            logger.warning(f"Name generation failed, using fallback: {e}")
            return "Construction Project"
    
    def _build_planning_prompt(
        self,
        project_description: str,
        budget: Optional[float],
        timeline_weeks: Optional[int],
        constraints: Optional[List[str]]
    ) -> str:
        """Build a structured prompt for construction planning."""

        prompt = f"""You are an experienced residential architectural designer and construction project manager. First design the house as a real, livable floor plan, then plan its construction.

{self._project_brief(project_description, budget, timeline_weeks, constraints)}"""

        prompt += """

Reply with ONLY a JSON object (no markdown, no explanation). Use this exact structure with 4-5 phases, 2 tasks per phase, and 6-8 materials:

{"project_structure":{"total_area_sqft":0,"layout":{"entry":"Room","rects":[{"room":"Room","x":0,"z":0,"length":0,"width":0},{"room":"Other Room","x":0,"z":0,"length":0,"width":0}]},"rooms":[{"name":"Room","dimensions":{"length":0,"width":0,"height":9},"floor_material":"carpet","wall_material":"drywall","connects_to":["Other Room"]}]},"phases":[{"name":"Phase","duration_weeks":2,"description":"desc","tasks":[{"name":"Task","duration_days":5,"description":"desc","estimated_cost":0}],"estimated_cost":0}],"total_cost":0,"total_duration_weeks":0,"material_list":[{"name":"Material","material_type":"wood","quantity":0,"unit":"sqft","unit_cost":0,"total_cost":0,"supplier_type":"local"}]}

Fill in realistic values based on the project description above. Include room dimensions for VR. Always fill in "phases", "total_cost" and "material_list", also for a small building such as a shed or a single room.

FLOOR PLAN DESIGN (all sizes in feet):
- Design it the way an architect would: a coherent house with a natural flow, not a random collection of rooms.
- Include every space a real home of this kind needs: an entry, circulation (hallway) where rooms would otherwise be cut off, and kitchen/bathroom/storage as appropriate.
- Zone the house: public spaces (entry, living, dining, kitchen) together; private spaces (bedrooms, bathrooms) grouped away from the entry; kitchen next to dining; bathrooms reachable from bedrooms and from the hallway.
- Use realistic residential sizes (e.g. bedroom 10-14 ft, living room 14-20 ft, bathroom 5-9 ft, hallway 4-5 ft wide).
- "layout" is the floor plan:
""" + RECT_LAYOUT_FORMAT + """
- The house is a plain rectangle unless the description asks for another shape.
- "rooms" lists every room in the layout with the same names, its "dimensions" (the size its rectangle has, and the height), materials, and "connects_to".
- DOORWAYS: "connects_to" lists the exact names of the rooms this room opens into through a doorway. Only connect rooms whose rectangles share a wall. Design the circulation: guests walk from the entry into the living area, bedrooms open off a hallway or the living area (never through another bedroom), and a bathroom opens off a hallway or the bedroom it serves. Every room must be reachable from the entry. Each connection only needs listing once.
- OPEN PLAN: when the description asks for rooms open to each other (an open kitchen, living and dining), list them in "open_to" instead of "connects_to": the wall between them is left out. They must share a wall.
- WALLS FOR COUNTERS AND FURNITURE: windows and doors are placed automatically. A room may list "solid_walls": ["back", ...] (sides "front"|"back"|"left"|"right") that must stay free of any window, door or doorway; a kitchen keeps one long wall for counters, stove and cabinets, so give the kitchen one solid wall that doesn't face its entry or the dining area.
- BAY WINDOWS: only when the description asks for one, give that room "bay_window": {"side": "front"|"back"|"left"|"right", "width": 8, "depth": 2.5, "style": "angled"|"box"} (feet; "angled" is the classic three-sided bay). The side must be one where the room has an outside wall: the edge of the footprint or of an open area. Leave the key out of every other room.
- OUTSIDE DOORS: the front door is automatic (on the "entry" room). Only when the description asks for another door to the outside (a back door, a sliding glass door or French doors to the yard, patio or deck), give that room "outside_doors": [{"side": "front"|"back"|"left"|"right", "style": "sliding_glass"|"french"|"hinged", "width": 6}] (feet; a double sliding door is about 6-8 ft, French doors 5-6 ft, a single door 3 ft). The side must be one where the room has an outside wall. Leave the key out of every other room.
- Use descriptive room names (e.g. "Entry Foyer", "Primary Bedroom", "Hall Bathroom").
- OUTSIDE OF THE HOUSE: only when the description mentions the roof, the outside walls, colors, or the yard (trees, plants, paths, driveway, patio, fence, pool), add "exterior" inside "project_structure":
""" + EXTERIOR_FORMAT + """
- FURNITURE: only when the description mentions furniture or asks for a furnished house, add "furniture" inside "project_structure" (room names exactly as in "rooms"):
""" + FURNITURE_FORMAT

        return prompt

    @staticmethod
    def _project_brief(
        project_description: str,
        budget: Optional[float],
        timeline_weeks: Optional[int],
        constraints: Optional[List[str]],
    ) -> str:
        brief = f"PROJECT DESCRIPTION: {project_description}\n\n"
        if budget:
            brief += f"BUDGET: ${budget:,.2f}\n"
        if timeline_weeks:
            brief += f"DESIRED TIMELINE: {timeline_weeks} weeks\n"
        if constraints:
            brief += f"CONSTRAINTS: {', '.join(constraints)}\n"
        return brief

    def _build_construction_prompt(
        self,
        project_description: str,
        structure: Dict[str, Any],
        budget: Optional[float],
        timeline_weeks: Optional[int],
        constraints: Optional[List[str]],
    ) -> str:
        """Prompt for planning the construction of a floor plan that already exists.
        Asks for the same phase and material format as ``_build_planning_prompt``."""
        current = json.dumps(
            {k: structure.get(k) for k in ("layout", "rooms", "exterior") if structure.get(k)},
            separators=(",", ":"),
        )
        return f"""You are an experienced construction project manager. The building below is already designed; plan its construction.

{self._project_brief(project_description, budget, timeline_weeks, constraints)}
FLOOR PLAN (JSON, all sizes in feet):
{current}

Reply with ONLY a JSON object (no markdown, no explanation). Size the plan to the building — a shed or a single room needs fewer, shorter phases and cheaper materials than a house. Use this exact structure with 3-5 phases, 2 tasks per phase, and 6-8 materials:

{{"phases":[{{"name":"Phase","duration_weeks":2,"description":"desc","tasks":[{{"name":"Task","duration_days":5,"description":"desc","estimated_cost":0}}],"estimated_cost":0}}],"total_cost":0,"total_duration_weeks":0,"material_list":[{{"name":"Material","material_type":"wood","quantity":0,"unit":"sqft","unit_cost":0,"total_cost":0,"supplier_type":"local"}}]}}

Fill in realistic values for this building: quantities from its sizes, costs in US dollars, "total_cost" the sum of the phases' costs."""

    def _build_refine_prompt(
        self, structure: Dict[str, Any], instruction: str, site: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Prompt for changing an existing house. Uses the same layout and exterior
        formats as ``_build_planning_prompt`` — change both together."""
        layout = structure.get("layout")
        if isinstance(layout, dict):
            # Older plans are nested-split trees: show them as the rectangles they draw,
            # the one format the AI is asked to answer in.
            try:
                layout = layout_as_rects(layout)
            except LayoutError:
                pass
        current = json.dumps(
            {"layout": layout, "rooms": structure.get("rooms", [])},
            separators=(",", ":"),
        )
        exterior = json.dumps(structure.get("exterior"), separators=(",", ":"))
        furniture = json.dumps(shown_furniture(structure.get("furniture"), structure.get("rooms")), separators=(",", ":"))
        site_json = json.dumps(site or {}, separators=(",", ":"))
        return f"""You are a residential architect and landscape designer revising an existing house.

CURRENT FLOOR PLAN (JSON, all sizes in feet):
{current}

CURRENT EXTERIOR (JSON, feet; null means none yet):
{exterior}

CURRENT FURNITURE (JSON by room; null means none yet):
{furniture}

SITE (feet: the footprint, the front door and which way it faces, every room's rectangle and its four "walls" (front/back/left/right, each "<what is on the other side: outside or room names>: <what is in it: doorways, windows, doors, open walls>", "(solid)" when kept clear), the other doors to the yard (put a deck or patio "outside the sliding door" against the wall there), the open outdoor parts of the footprint, and "doorways": every doorway between two rooms the house has now, including ones added automatically so every room is reachable):
{site_json}

REQUESTED CHANGE: {instruction}

First decide what the change is about:
- "exterior": only the outside — roof, outside wall finish or colors, trim, the ground, or the yard (trees, palms, shrubs, flowers, lawn, paths, driveway, patio, deck, fence, hedge, pool, rocks).
- "furniture": only what is in the rooms — sofas, chairs, beds, tables, desks, dressers, shelves, TVs, kitchen counters, islands and appliances, toilets, tubs, showers, vanities, rugs, lamps, indoor plants.
- "floor_plan": the rooms — sizes, adding or removing rooms, doorways, the house's shape, bay windows, and doors to the outside (back door, sliding glass door, French doors), even when they lead to the yard, a patio or a deck.
- "both": it asks for the rooms and the outside.

Apply the requested change and nothing else: keep everything the change does not affect.

FLOOR PLAN format (for "floor_plan" or "both"):
- "layout" (always in this format):
{RECT_LAYOUT_FORMAT}
- To make a room bigger or smaller, change its rectangle and move the rooms beside it so nothing overlaps and no gap opens up; keep every room the change doesn't need to move where it is. "notes" lists only what this change had to adjust.
- "rooms" lists every room in the layout with the same names, its "dimensions" (its rectangle's length and width, height 8-10), "floor_material", "wall_material" and "connects_to" (names of rooms it opens into through a doorway; only rooms that share a wall). Keep the plan livable — every room reachable from the entry, bedrooms never only reachable through another bedroom.
- To remove a doorway (or make a wall solid), drop each room from the other's "connects_to" AND add it to the room's "no_door_to" list (e.g. "no_door_to": ["Hallway"]); a doorway in SITE "doorways" that no "connects_to" lists was added automatically and only "no_door_to" removes it. If that leaves rooms unreachable, connect them another way through "connects_to" (e.g. the hallway to a room beside it). Keep existing "no_door_to" entries unless the change asks for that doorway back; to add a doorway, remove the pair from "no_door_to".
- WALLS: to make a wall clean (no window, door or doorway in it, e.g. for kitchen counters or a bed), add its side to the room's "solid_walls" list (["back", "left"]; "front" is the street side, left/right along the layout's length; SITE rooms' "walls" show which side has what). A solid wall overrides doors, doorways and windows on it; if a doorway in it is the only way into a room, connect that room another way through "connects_to". To allow openings in it again, remove the side from "solid_walls".
- WINDOWS are placed automatically, one per room (none in hallways and closets): "window": false removes the room's window, "window": {{"side": "left"}} puts it on that side. To remove a room's windows, ALWAYS set "window": false — also when its window is a bay window (then leave "bay_window" out too); without it the ordinary window comes back. To move or remove only one particular opening, "solid_walls" on its side is usually what is meant.
- To REMOVE A WALL between two rooms (open them to each other), list the other room in "open_to" (e.g. the kitchen's "open_to": ["Dining Room"]); the rooms must share a wall. They are then joined without a doorway, so drop them from each other's "connects_to". To put the wall back, remove the name from "open_to".
- To RENAME a room, also return "renames": {{"Old Name": "New Name"}} beside "project_structure", and use the new name everywhere (layout, rooms, "connects_to", "no_door_to", "open_to", "entry").
- A room may have a bay window: "bay_window": {{"side": "front"|"back"|"left"|"right", "width": 8, "depth": 2.5, "style": "angled"|"box"}} (feet; front is the street side, left/right along the layout's length). It must be on a side where the room has an outside wall (the edge of the footprint or of an open area). A bay window takes the place of the room's ordinary window. Keep existing bay windows unless the change is about them; to remove one, leave the key out.
- A room may have doors to the outside besides the front door: "outside_doors": [{{"side": "front"|"back"|"left"|"right", "style": "sliding_glass"|"french"|"hinged", "width": 6}}] (feet; a double sliding glass door is about 6-8 ft, French doors 5-6 ft, a back door 3 ft). Use a side where the room has an outside wall (the SITE's rooms show which edges are on the footprint or an open area); "to the backyard" means "back". Keep existing outside doors unless the change is about them; to remove one, drop it from the list.

EXTERIOR format (for "exterior" or "both"; return the WHOLE exterior: the current one with the change applied, keeping every item the change does not affect):
{EXTERIOR_FORMAT}

FURNITURE format (for "furniture", or beside any other scope when the change also moves furniture): return only the rooms whose furniture changes, each with its whole new list (its current items with the change applied); rooms left out keep theirs. Give "auto" only when the change asks to furnish (true) or clear (false) the whole house. When a room is renamed or removed, its furniture follows automatically.
{FURNITURE_FORMAT}

Reply with ONLY a JSON object (no markdown, no explanation):
- for "exterior": {{"scope": "exterior", "exterior": {{...}}}}
- for "furniture": {{"scope": "furniture", "furniture": {{"rooms": {{"Room Name": [...]}}}}}}
- for "floor_plan": {{"scope": "floor_plan", "project_structure": {{"layout": {{...}}, "rooms": [...]}}}} (plus "renames" when a room is renamed)
- for "both": {{"scope": "both", "project_structure": {{"layout": {{...}}, "rooms": [...]}}, "exterior": {{...}}}}
Add "furniture": {{...}} beside "exterior" or "project_structure" when the change is about furniture too."""

    def _clean_json_string(self, json_str: str) -> str:
        """Fix common LLM JSON formatting issues before parsing."""
        # Strip markdown code fences
        json_str = re.sub(r'```(?:json)?\s*', '', json_str).strip()

        # Remove trailing commas before } or ]
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
        
        # Replace Python-style literals
        json_str = re.sub(r'\bTrue\b', 'true', json_str)
        json_str = re.sub(r'\bFalse\b', 'false', json_str)
        json_str = re.sub(r'\bNone\b', 'null', json_str)
        
        # Fix missing commas between array elements
        # Pattern: ] followed by { without comma
        json_str = re.sub(r'\]\s*\{', r'],{', json_str)
        
        # Pattern: } followed by { without comma
        json_str = re.sub(r'\}\s*\{', r'},{', json_str)
        
        # Pattern: } followed by " without comma (property after object)
        json_str = re.sub(r'\}\s*"', r'},"', json_str)
        
        # Pattern: ] followed by " without comma (property after array)
        json_str = re.sub(r'\]\s*"', r'],"', json_str)
        
        # Pattern: string followed by " without comma (consecutive properties)
        json_str = re.sub(r'"\s*"([^"]+)":', r'","\\1":', json_str)
        
        # Fix missing commas after numbers/booleans/null before next property
        json_str = re.sub(r'(\d|true|false|null)\s*"', r'\1,"', json_str)
        
        # Remove any duplicate commas
        json_str = re.sub(r',\s*,+', ',', json_str)
        
        # Fix single quotes (if any) to double quotes for property names
        json_str = re.sub(r"'([^']+)':", r'"\1":', json_str)
        
        return json_str

    def _extract_and_repair_json(self, content: str) -> str:
        """Extract and repair JSON from potentially malformed content."""
        # Find the outermost JSON object
        start_idx = content.find('{')
        if start_idx == -1:
            raise ValueError("No JSON object found in response")

        # Walk the content tracking string/escape/nesting state
        in_string = False
        escape_next = False
        stack = []   # 'o' for object '{', 'a' for array '['
        end_idx = -1

        for i in range(start_idx, len(content)):
            char = content[i]

            if escape_next:
                escape_next = False
                continue

            if char == '\\' and in_string:
                escape_next = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == '{':
                stack.append('o')
            elif char == '[':
                stack.append('a')
            elif char == '}':
                if stack and stack[-1] == 'o':
                    stack.pop()
                if not stack:
                    end_idx = i + 1
                    break
            elif char == ']':
                if stack and stack[-1] == 'a':
                    stack.pop()

        if end_idx != -1:
            return content[start_idx:end_idx]

        # JSON is truncated — repair it
        json_str = content[start_idx:].strip()

        # Strip back to the last safe boundary (last complete value followed by , or ])
        # so we don't leave a dangling key like "estimated_cost" with no value.
        json_str = self._strip_to_last_safe_boundary(json_str)

        # Re-walk the stripped string to get the correct open-container stack
        stack2 = []
        in_string2 = False
        escape_next2 = False
        for ch in json_str:
            if escape_next2:
                escape_next2 = False
                continue
            if ch == '\\' and in_string2:
                escape_next2 = True
                continue
            if ch == '"':
                in_string2 = not in_string2
                continue
            if in_string2:
                continue
            if ch == '{':
                stack2.append('o')
            elif ch == '[':
                stack2.append('a')
            elif ch == '}' and stack2 and stack2[-1] == 'o':
                stack2.pop()
            elif ch == ']' and stack2 and stack2[-1] == 'a':
                stack2.pop()

        # Close open containers in reverse order (LIFO)
        for item in reversed(stack2):
            json_str += '}' if item == 'o' else ']'

        return json_str

    def _strip_to_last_safe_boundary(self, json_str: str) -> str:
        """Trim truncated JSON back to the last position where a complete value ended
        (i.e. after a closing } ] or a quoted string), so open incomplete keys/values
        are removed before we attempt to close the remaining structure."""
        in_string = False
        escape_next = False
        last_safe = 0  # index just after the last safely-complete token

        i = 0
        while i < len(json_str):
            ch = json_str[i]

            if escape_next:
                escape_next = False
                i += 1
                continue

            if ch == '\\' and in_string:
                escape_next = True
                i += 1
                continue

            if ch == '"':
                in_string = not in_string
                if not in_string:
                    # Just closed a string — safe only if a value (not a key)
                    # Peek ahead for ':' to detect key vs value
                    j = i + 1
                    while j < len(json_str) and json_str[j] in ' \t\n\r':
                        j += 1
                    if j >= len(json_str) or json_str[j] != ':':
                        last_safe = i + 1
                i += 1
                continue

            if in_string:
                i += 1
                continue

            if ch in '}]':
                last_safe = i + 1

            i += 1

        return json_str[:last_safe] if last_safe > 0 else json_str

    def _parse_structured_plan(self, content: str, source: str) -> Dict[str, Any]:
        """Parse the AI response into structured plan data with robust error handling."""
        parse_attempts = []
        
        try:
            # Strategy 1: the JSON as returned (JSON mode usually gets it right), else
            # with the regex repairs. Never clean valid JSON: the repairs work on raw
            # text and corrupt strings ("Bedroom 2" -> "Bedroom 2,", "True" -> "true").
            try:
                json_str = self._extract_and_repair_json(content)
                try:
                    plan_data = json.loads(json_str)
                except json.JSONDecodeError:
                    plan_data = json.loads(self._clean_json_string(json_str))
                if not isinstance(plan_data, dict):
                    raise json.JSONDecodeError("plan is not a JSON object", json_str, 0)
                logger.info(f"Successfully parsed JSON on first attempt (Strategy 1)")
                
                # Validate and fill required fields
                plan_data = self._validate_and_fill_plan(plan_data)
                
                return {
                    "success": True,
                    "plan": plan_data,
                    "source": source,
                    "raw_response": content
                }
            except json.JSONDecodeError as e:
                parse_attempts.append(f"Strategy 1 failed: {str(e)}")
                logger.debug(f"Strategy 1 parsing failed: {e}")
            
            # Strategy 2: More aggressive cleaning - fix line breaks and whitespace
            try:
                json_str = self._extract_and_repair_json(content)
                # Remove problematic newlines within strings
                json_str = json_str.replace('\n', ' ').replace('\r', ' ')
                # Normalize whitespace
                json_str = re.sub(r'\s+', ' ', json_str)
                json_str = self._clean_json_string(json_str)
                plan_data = json.loads(json_str)
                logger.info(f"Successfully parsed JSON on second attempt (Strategy 2)")
                
                plan_data = self._validate_and_fill_plan(plan_data)
                
                return {
                    "success": True,
                    "plan": plan_data,
                    "source": source,
                    "raw_response": content
                }
            except json.JSONDecodeError as e:
                parse_attempts.append(f"Strategy 2 failed: {str(e)}")
                logger.debug(f"Strategy 2 parsing failed: {e}")
            
            # Strategy 3: Try to fix specific JSON error location
            try:
                json_str = self._extract_and_repair_json(content)
                json_str = self._clean_json_string(json_str)
                plan_data = self._repair_json_at_error(json_str)
                logger.info(f"Successfully parsed JSON on third attempt (Strategy 3)")
                
                plan_data = self._validate_and_fill_plan(plan_data)
                
                return {
                    "success": True,
                    "plan": plan_data,
                    "source": source,
                    "raw_response": content
                }
            except (json.JSONDecodeError, ValueError) as e:
                parse_attempts.append(f"Strategy 3 failed: {str(e)}")
                logger.debug(f"Strategy 3 parsing failed: {e}")
            
            # Strategy 4: Use regex to extract key-value pairs and rebuild JSON
            try:
                plan_data = self._rebuild_json_from_content(content)
                if plan_data and isinstance(plan_data, dict):
                    logger.info(f"Successfully rebuilt JSON from content (Strategy 4)")
                    
                    plan_data = self._validate_and_fill_plan(plan_data)
                    
                    return {
                        "success": True,
                        "plan": plan_data,
                        "source": source,
                        "raw_response": content,
                        "note": "JSON was reconstructed from partially valid content"
                    }
            except Exception as e:
                parse_attempts.append(f"Strategy 4 failed: {str(e)}")
                logger.debug(f"Strategy 4 parsing failed: {e}")
            
            # All strategies failed - log details and return error
            logger.warning(f"All JSON parsing strategies failed. Attempts: {'; '.join(parse_attempts)}")
            logger.warning(f"Raw content preview (first 800 chars): {content[:800]}")
            logger.warning(f"Raw content preview (last 300 chars): ...{content[-300:]}")
            
            return {
                "success": False,
                "error": "Failed to parse structured plan after multiple attempts",
                "parse_attempts": parse_attempts,
                "raw_response": content,
                "source": source
            }

        except Exception as e:
            logger.error(f"Unexpected error parsing plan: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "raw_response": content,
                "source": source
            }

    def _repair_json_at_error(self, json_str: str) -> Dict[str, Any]:
        """Attempt to repair JSON by identifying and fixing the specific error location."""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            # Get error position
            error_pos = e.pos
            logger.debug(f"JSON error at position {error_pos}: {e.msg}")
            
            # Try to fix the error at the specific location
            if error_pos < len(json_str):
                # Check what's around the error
                context_start = max(0, error_pos - 20)
                context_end = min(len(json_str), error_pos + 20)
                context = json_str[context_start:context_end]
                logger.debug(f"Error context: ...{context}...")
                
                # Try inserting a comma if it's missing
                if "Expecting ',' delimiter" in e.msg:
                    fixed = json_str[:error_pos] + ',' + json_str[error_pos:]
                    return json.loads(fixed)
                
                # Try removing character if it's unexpected
                if "Expecting" in e.msg and error_pos > 0:
                    fixed = json_str[:error_pos-1] + json_str[error_pos:]
                    return json.loads(fixed)
            
            raise

    def _rebuild_json_from_content(self, content: str) -> Optional[Dict[str, Any]]:
        """Rebuild a basic JSON structure by extracting recognizable patterns."""
        try:
            # Try to find key sections in the content
            result = {
                "phases": [],
                "total_cost": 0,
                "total_duration_weeks": 0,
                "material_list": [],
                "project_structure": {}
            }
            
            # Extract total_cost
            cost_match = re.search(r'"total_cost"\s*:\s*(\d+(?:\.\d+)?)', content)
            if cost_match:
                result["total_cost"] = float(cost_match.group(1))
            
            # Extract total_duration_weeks
            duration_match = re.search(r'"total_duration_weeks"\s*:\s*(\d+)', content)
            if duration_match:
                result["total_duration_weeks"] = int(duration_match.group(1))
            
            # This is a minimal reconstruction - return None if we couldn't find anything useful
            if result["total_cost"] == 0 and result["total_duration_weeks"] == 0:
                return None
            
            return result
            
        except Exception as e:
            logger.debug(f"Failed to rebuild JSON from content: {e}")
            return None

    def _validate_and_fill_plan(self, plan_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate plan data and fill in missing required fields with defaults."""
        # Ensure required top-level fields exist
        if 'phases' not in plan_data:
            plan_data['phases'] = []
        
        if 'total_cost' not in plan_data:
            # Try to calculate from phases
            total = sum(phase.get('estimated_cost', 0) for phase in plan_data.get('phases', []))
            plan_data['total_cost'] = total if total > 0 else 0
        
        if 'total_duration_weeks' not in plan_data:
            # Try to calculate from phases
            total = sum(phase.get('duration_weeks', 0) for phase in plan_data.get('phases', []))
            plan_data['total_duration_weeks'] = total if total > 0 else 0
        
        if 'material_list' not in plan_data:
            plan_data['material_list'] = []
        
        if 'project_structure' not in plan_data:
            plan_data['project_structure'] = {}
        
        return plan_data
