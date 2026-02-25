import asyncio
import logging
import json
import re
from typing import Optional, Dict, Any, List
import ollama
import google.generativeai as genai

from ..config import settings

logger = logging.getLogger(__name__)


class AIPlanningService:
    """Service for construction planning using LLM models."""

    def __init__(self):
        self.ollama_available = False
        self.gemini_available = False
        
        # Initialize Ollama client with custom host
        self.ollama_client = ollama.Client(host=settings.ollama_url)

        # Initialize Gemini if API key is available
        if settings.gemini_api_key:
            try:
                genai.configure(api_key=settings.gemini_api_key)
                self.gemini_model = genai.GenerativeModel('gemini-pro')
                self.gemini_available = True
                logger.info("Gemini API initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini API: {e}")

        # Check Ollama availability
        try:
            self.ollama_client.list()
            self.ollama_available = True
            logger.info(f"Ollama service is available at {settings.ollama_url}")
        except Exception as e:
            logger.warning(f"Ollama service not available at {settings.ollama_url}: {e}")

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
        prompt = self._build_planning_prompt(
            project_description, budget, timeline_weeks, constraints
        )

        ollama_error = None
        
        # Try Ollama first, fallback to Gemini
        if self.ollama_available:
            try:
                return await self._generate_with_ollama(prompt)
            except Exception as e:
                ollama_error = e
                logger.warning(f"Ollama planning failed, trying Gemini: {e}")
        
        # Try Gemini if Ollama failed or wasn't available
        if self.gemini_available:
            try:
                return await self._generate_with_gemini(prompt)
            except Exception as gemini_error:
                logger.error(f"Gemini planning also failed: {gemini_error}")
                # If both failed, raise the most recent error
                raise gemini_error
        
        # If no service is available or both failed
        if ollama_error:
            raise ollama_error
        else:
            raise Exception("No AI services available for planning")

    async def _generate_with_ollama(self, prompt: str) -> Dict[str, Any]:
        """Generate construction plan using Ollama with reduced memory footprint."""
        try:
            logger.info("Generating construction plan with Ollama...")

            # Run Ollama in executor to avoid blocking and add timeout
            loop = asyncio.get_event_loop()
            
            def _ollama_generate():
                return self.ollama_client.chat(
                    model='llama3.1:8b',  # Using 8B model instead of latest (70B)
                    messages=[{
                        'role': 'user',
                        'content': prompt
                    }],
                    options={
                        'temperature': 0.7,
                        'top_p': 0.9,
                        'num_predict': 4096,  # Enough for full JSON response
                        'num_ctx': 6144,      # Context window: prompt (~500t) + response (~4096t)
                        'num_thread': 4       # Limit CPU threads
                    }
                )
            
            # Add 1200 second timeout
            response = await asyncio.wait_for(
                loop.run_in_executor(None, _ollama_generate),
                timeout=1200.0
            )

            content = response['message']['content']
            logger.info("Ollama response received successfully")

            # Parse the structured response
            return self._parse_structured_plan(content, "ollama")

        except asyncio.TimeoutError:
            logger.error("Ollama generation timed out after 600 seconds")
            raise Exception("Ollama generation timed out")
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise

    async def _generate_with_gemini(self, prompt: str) -> Dict[str, Any]:
        """Generate construction plan using Gemini API."""
        try:
            logger.info("Generating construction plan with Gemini...")

            response = self.gemini_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    top_p=0.9,
                    max_output_tokens=2048,
                )
            )

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
            # Generate project name from description
            project_name = await self._generate_project_name(project_description)
            
            # Generate construction plan
            plan_result = await self.generate_construction_plan(
                project_description, budget, timeline_weeks, constraints
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
            if self.ollama_available:
                try:
                    loop = asyncio.get_event_loop()
                    response = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: self.ollama_client.chat(
                                model='llama3.1:8b',  # Using 8B model
                                messages=[{'role': 'user', 'content': prompt}],
                                options={'temperature': 0.8, 'num_predict': 50, 'num_ctx': 1024}
                            )
                        ),
                        timeout=15.0
                    )
                    name = response['message']['content'].strip().strip('"\'')
                except Exception as ollama_err:
                    logger.warning(f"Ollama name generation failed: {ollama_err}")
                    if self.gemini_available:
                        response = self.gemini_model.generate_content(prompt)
                        name = response.text.strip().strip('"\'')
                    else:
                        raise ollama_err
            elif self.gemini_available:
                response = self.gemini_model.generate_content(prompt)
                name = response.text.strip().strip('"\'')
            else:
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

        prompt = f"""You are an expert construction project manager. Generate a detailed construction plan for the following project:

PROJECT DESCRIPTION: {project_description}

"""

        if budget:
            prompt += f"BUDGET: ${budget:,.2f}\n"

        if timeline_weeks:
            prompt += f"DESIRED TIMELINE: {timeline_weeks} weeks\n"

        if constraints:
            prompt += f"CONSTRAINTS: {', '.join(constraints)}\n"

        prompt += """

Reply with ONLY a JSON object (no markdown, no explanation). Use this exact structure with 4-5 phases, 2 tasks per phase, and 6-8 materials:

{"project_structure":{"total_area_sqft":0,"rooms":[{"name":"Room","dimensions":{"length":0,"width":0,"height":9},"floor_material":"carpet","wall_material":"drywall"}]},"phases":[{"name":"Phase","duration_weeks":2,"description":"desc","tasks":[{"name":"Task","duration_days":5,"description":"desc","estimated_cost":0}],"estimated_cost":0}],"total_cost":0,"total_duration_weeks":0,"material_list":[{"name":"Material","material_type":"wood","quantity":0,"unit":"sqft","unit_cost":0,"total_cost":0,"supplier_type":"local"}]}

Fill in realistic values based on the project description above. Include room dimensions for VR."""

        return prompt

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
            # Strategy 1: Extract and clean JSON normally
            try:
                json_str = self._extract_and_repair_json(content)
                json_str = self._clean_json_string(json_str)
                plan_data = json.loads(json_str)
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
