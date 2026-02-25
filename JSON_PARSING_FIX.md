# JSON Parsing Fix for AI Planning Service

## Problem
The AI Planning Service was experiencing JSON parsing failures when processing responses from the Ollama LLM. The error message indicated:
```
Failed to parse JSON from AI response: Expecting ',' delimiter: line 78 column 6 (char 3402)
```

This occurred because LLMs sometimes generate malformed JSON with missing commas, trailing commas, or other formatting issues.

## Solution
Implemented a comprehensive multi-strategy JSON parsing solution in `ai_planning_service.py`:

### 1. Enhanced JSON Cleaning (`_clean_json_string`)
Added robust regex patterns to fix common JSON issues:
- **Missing commas between array elements**: `]` followed by `{` → `],[`
- **Missing commas between objects**: `}` followed by `{` → `},{`
- **Missing commas after objects/arrays**: `}` or `]` followed by `"` → add comma
- **Missing commas after values**: numbers/booleans/null followed by `"` → add comma
- **Trailing commas**: Removed before `}` or `]`
- **Python-style literals**: `True`/`False`/`None` → `true`/`false`/`null`
- **Duplicate commas**: Cleaned up
- **Single quotes**: Converted to double quotes for property names

### 2. Smart JSON Extraction (`_extract_and_repair_json`)
Intelligently extracts JSON objects from mixed content:
- Finds the outermost JSON object
- Properly handles string escaping
- Tracks brace matching outside of strings
- Auto-closes unclosed braces if needed

### 3. Multi-Strategy Parsing (`_parse_structured_plan`)
Implements 4 fallback strategies:

**Strategy 1**: Normal extraction and cleaning
- Extract JSON boundaries
- Apply standard cleaning rules
- Attempt to parse

**Strategy 2**: Aggressive whitespace normalization
- Remove problematic newlines within strings
- Normalize all whitespace
- Apply cleaning and parse

**Strategy 3**: Targeted error repair (`_repair_json_at_error`)
- Parse the JSON to identify exact error location
- Insert missing comma if that's the issue
- Remove unexpected characters if needed
- Retry parsing

**Strategy 4**: Regex-based reconstruction (`_rebuild_json_from_content`)
- Extract key fields using regex patterns
- Rebuild minimal valid JSON structure
- Use as last resort fallback

### 4. Field Validation (`_validate_and_fill_plan`)
Ensures all required fields exist with sensible defaults:
- `phases`: Empty array if missing
- `total_cost`: Calculated from phases or 0
- `total_duration_weeks`: Calculated from phases or 0
- `material_list`: Empty array if missing
- `project_structure`: Empty object if missing

## Benefits
1. ✅ **Resilient**: Handles multiple types of JSON formatting errors
2. ✅ **Graceful Degradation**: Falls back through multiple strategies
3. ✅ **Detailed Logging**: Each strategy logs its attempts for debugging
4. ✅ **Non-Breaking**: Valid JSON is not modified or broken
5. ✅ **Comprehensive**: Covers the most common LLM JSON generation issues

## Testing
Created `test_json_parsing.py` to verify the improvements:
- ✅ 6/6 test cases passed
- Tests include the exact error scenario from the logs
- Verifies both malformed JSON repair and valid JSON preservation

## Usage
The fix is automatic and transparent. When the AI Planning Service receives a response from Ollama or Gemini:
1. The response is automatically processed through the multi-strategy parser
2. If the first strategy succeeds, it returns immediately
3. If it fails, the next strategy is tried automatically
4. All attempts are logged for debugging purposes
5. If all strategies fail, a detailed error is returned with diagnostic information

## Files Modified
- `backend-core/backend/app/services/ai_planning_service.py` - Enhanced JSON parsing logic
- `test_json_parsing.py` - Test suite for verification

## Impact
This fix should eliminate the `Expecting ',' delimiter` errors and significantly improve the reliability of AI-generated construction plans.
