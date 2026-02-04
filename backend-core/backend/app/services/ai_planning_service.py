import asyncio
import logging
import json
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
            ollama.list()
            self.ollama_available = True
            logger.info("Ollama service is available")
        except Exception as e:
            logger.warning(f"Ollama service not available: {e}")

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

        # Try Ollama first, fallback to Gemini
        if self.ollama_available:
            try:
                return await self._generate_with_ollama(prompt)
            except Exception as e:
                logger.warning(f"Ollama planning failed, trying Gemini: {e}")
                if self.gemini_available:
                    return await self._generate_with_gemini(prompt)
                else:
                    raise e
        elif self.gemini_available:
            return await self._generate_with_gemini(prompt)
        else:
            raise Exception("No AI services available for planning")

    async def _generate_with_ollama(self, prompt: str) -> Dict[str, Any]:
        """Generate construction plan using Ollama."""
        try:
            logger.info("Generating construction plan with Ollama...")

            response = ollama.chat(
                model='llama3.1:8b',
                messages=[{
                    'role': 'user',
                    'content': prompt
                }],
                options={
                    'temperature': 0.7,
                    'top_p': 0.9,
                    'num_predict': 2048
                }
            )

            content = response['message']['content']
            logger.info("Ollama response received")

            # Parse the structured response
            return self._parse_structured_plan(content, "ollama")

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

Please provide a comprehensive construction plan in the following JSON format:

{
  "phases": [
    {
      "name": "Phase name",
      "duration_weeks": number,
      "description": "Brief description",
      "tasks": [
        {
          "name": "Task name",
          "duration_days": number,
          "description": "Task details",
          "materials_needed": ["material1", "material2"],
          "labor_required": "labor description",
          "estimated_cost": number
        }
      ],
      "estimated_cost": number
    }
  ],
  "total_cost": number,
  "total_duration_weeks": number,
  "risks": ["risk1", "risk2"],
  "recommendations": ["rec1", "rec2"],
  "material_list": [
    {
      "name": "Material name",
      "quantity": "quantity with units",
      "estimated_cost": number,
      "supplier_type": "local/distributor/manufacturer"
    }
  ]
}

Ensure the plan is realistic, safe, and follows construction best practices. Include all major phases from site preparation to completion."""

        return prompt

    def _parse_structured_plan(self, content: str, source: str) -> Dict[str, Any]:
        """Parse the AI response into structured plan data."""
        try:
            # Try to extract JSON from the response
            # Look for JSON block in the response
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1

            if start_idx != -1 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
                plan_data = json.loads(json_str)

                # Validate required fields
                required_fields = ['phases', 'total_cost', 'total_duration_weeks']
                for field in required_fields:
                    if field not in plan_data:
                        plan_data[field] = "Not specified"

                return {
                    "success": True,
                    "plan": plan_data,
                    "source": source,
                    "raw_response": content
                }
            else:
                # Fallback: return structured response with raw content
                return {
                    "success": True,
                    "plan": {
                        "phases": [],
                        "total_cost": "Not specified",
                        "total_duration_weeks": "Not specified",
                        "description": content
                    },
                    "source": source,
                    "raw_response": content
                }

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from AI response: {e}")
            return {
                "success": False,
                "error": "Failed to parse structured plan",
                "raw_response": content,
                "source": source
            }
        except Exception as e:
            logger.error(f"Error parsing plan: {e}")
            return {
                "success": False,
                "error": str(e),
                "raw_response": content,
                "source": source
            }
