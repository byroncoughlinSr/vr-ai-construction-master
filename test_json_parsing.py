#!/usr/bin/env python3
"""
Test script to verify JSON parsing improvements in AI Planning Service.
Tests various malformed JSON scenarios that the LLM might generate.
"""

import sys
import json

# Simulate the cleaning and parsing functions from the service
def clean_json_string(json_str: str) -> str:
    """Fix common LLM JSON formatting issues before parsing."""
    import re
    
    # Strip markdown code fences
    json_str = re.sub(r'```(?:json)?\s*', '', json_str).strip()
    
    # Remove trailing commas before } or ]
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    
    # Replace Python-style literals
    json_str = re.sub(r'\bTrue\b', 'true', json_str)
    json_str = re.sub(r'\bFalse\b', 'false', json_str)
    json_str = re.sub(r'\bNone\b', 'null', json_str)
    
    # Fix missing commas between array elements
    json_str = re.sub(r'\]\s*\{', r'],{', json_str)
    json_str = re.sub(r'\}\s*\{', r'},{', json_str)
    json_str = re.sub(r'\}\s*"', r'},"', json_str)
    json_str = re.sub(r'\]\s*"', r'],"', json_str)
    json_str = re.sub(r'"\s*"([^"]+)":', r'","\\1":', json_str)
    json_str = re.sub(r'(\d|true|false|null)\s*"', r'\1,"', json_str)
    json_str = re.sub(r',\s*,+', ',', json_str)
    json_str = re.sub(r"'([^']+)':", r'"\1":', json_str)
    
    return json_str


def test_json_parsing():
    """Test various malformed JSON scenarios."""
    
    test_cases = [
        {
            "name": "Missing comma at line 78 column 6 (original error)",
            "json": '''{
  "phases": [
    {
      "name": "Foundation",
      "duration_weeks": 2
    }
    {
      "name": "Framing",
      "duration_weeks": 3
    }
  ],
  "total_cost": 50000
}''',
            "should_fix": True
        },
        {
            "name": "Missing comma between object properties",
            "json": '''{
  "total_cost": 50000
  "total_duration_weeks": 12
}''',
            "should_fix": True
        },
        {
            "name": "Trailing commas",
            "json": '''{
  "phases": [],
  "total_cost": 50000,
}''',
            "should_fix": True
        },
        {
            "name": "Python-style literals",
            "json": '''{
  "active": True,
  "completed": False,
  "notes": None
}''',
            "should_fix": True
        },
        {
            "name": "Missing comma between array and property",
            "json": '''{
  "phases": [
    {"name": "Phase 1"}
  ]
  "total_cost": 50000
}''',
            "should_fix": True
        },
        {
            "name": "Valid JSON (should not break)",
            "json": '''{
  "phases": [],
  "total_cost": 50000,
  "total_duration_weeks": 12
}''',
            "should_fix": False
        }
    ]
    
    print("=" * 80)
    print("JSON PARSING IMPROVEMENT TEST")
    print("=" * 80)
    print()
    
    passed = 0
    failed = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test {i}: {test_case['name']}")
        print("-" * 80)
        
        original_json = test_case['json']
        
        # Try parsing original (should fail for malformed cases)
        try:
            json.loads(original_json)
            original_valid = True
            print("✓ Original JSON is valid")
        except json.JSONDecodeError as e:
            original_valid = False
            print(f"✗ Original JSON is invalid: {e.msg}")
        
        # Try parsing after cleaning
        cleaned_json = clean_json_string(original_json)
        try:
            result = json.loads(cleaned_json)
            cleaned_valid = True
            print(f"✓ Cleaned JSON is valid! Parsed successfully.")
            if not original_valid:
                print(f"  → Successfully repaired malformed JSON")
        except json.JSONDecodeError as e:
            cleaned_valid = False
            print(f"✗ Cleaned JSON is still invalid: {e.msg}")
            print(f"  Position: {e.pos}")
        
        # Determine pass/fail
        if test_case['should_fix']:
            # For malformed JSON, success means we fixed it
            if cleaned_valid:
                print("✅ PASSED: Successfully repaired malformed JSON")
                passed += 1
            else:
                print("❌ FAILED: Could not repair malformed JSON")
                failed += 1
        else:
            # For valid JSON, success means we didn't break it
            if original_valid and cleaned_valid:
                print("✅ PASSED: Valid JSON remains valid")
                passed += 1
            else:
                print("❌ FAILED: Valid JSON was broken")
                failed += 1
        
        print()
    
    print("=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 80)
    
    return failed == 0


if __name__ == "__main__":
    success = test_json_parsing()
    sys.exit(0 if success else 1)
