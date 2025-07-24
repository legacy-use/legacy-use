"""
AI-powered analysis routes.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
import vertexai
from vertexai.generative_models import GenerativeModel, Part

from server.models.base import APIDefinition, Parameter
from server.settings import settings

# Set up logging
logger = logging.getLogger(__name__)

# Create router
ai_router = APIRouter(prefix='/ai', tags=['AI Analysis'])


class VideoAnalysisResponse(BaseModel):
    """Response model for video analysis"""

    api_definition: APIDefinition
    analysis_summary: str
    confidence_score: float
    prompt: str


def initialize_vertex_ai():
    """Initialize Vertex AI with project settings"""
    if not settings.VERTEX_PROJECT_ID or not settings.VERTEX_REGION:
        raise HTTPException(
            status_code=500,
            detail='Vertex AI not configured. Please set VERTEX_PROJECT_ID and VERTEX_REGION.',
        )

    try:
        vertexai.init(
            project=settings.VERTEX_PROJECT_ID, location=settings.VERTEX_REGION
        )
        return GenerativeModel('gemini-2.5-flash')
    except Exception as e:
        logger.error(f'Failed to initialize Vertex AI: {str(e)}')
        raise HTTPException(
            status_code=500, detail=f'Failed to initialize Vertex AI: {str(e)}'
        )


def create_analysis_prompt() -> str:
    """Create the analysis prompt incorporating HOW_TO_PROMPT.md instructions"""

    how_to_prompt_instructions = """
# How to Prompt

### Writing Instructions: Prompt Structure

- **Begin with a one-line summary of the process.**
- For **each step**:
    - **UI to expect**:
        - Describe what the model should see *before* continuing.
        - If views tend to be similar and easy to confuse, include instructions on how to **notice if the wrong view is visible**.
    - **Action**:
        - Describe one single action using one tool.
        - Never combine different tool types in the same step.
            - ✅ *Press the key "BACKSPACE" five times*
            - ✅ *Click the "OK" button*
            - ❌ *Press "BACKSPACE" and then type "Hello"*

### Available Tools

These are the predefined tools the model can use to interact with the interface:

- **Type**

    Enters plain text input into a field.

    Example: *Type the text: "Example text"*

- **Press key**

    Simulates pressing a key or shortcut on the keyboard.

    Example: *Press the key: "RETURN"*

    This tool also supports commands like: *Press the key "BACKSPACE" **five times***

- **Click**

    Clicks on an element with the cursor.

    Example: *Click on the "Open" button in the top left toolbar*

    Also available:

    - *Double click*
    - *Right click*
- **Scroll up / Scroll down**

    Scrolls the screen in the corresponding direction.

    Example: *Scroll down on the shopping list on the left*

- **ui_not_as_expected**

    Use this tool **if the UI does not match the expected description**—for example, if the wrong tab is visible, elements are missing, or unexpected popups appear. This prevents the model from performing incorrect or unsafe actions.

    **Example:** *If you notice a popup containing a warning message, use the `ui_not_as_expected` tool.*

- **extract_tool**

    Use this tool at the **end of a process** to return the final result once the expected outcome is confirmed. The model will try to match the format defined in the **response example** section of the API specification.

    **Example:** *Now that the data sheet is visible, return the required price information using the `extract_tool`.*

> 💡 Tip: Whenever possible, prefer using keyboard shortcuts (press key) over mouse interactions (click).  It is more reliable and less dependent on precise layout positioning.

### Using Braces (`{{...}}`)

You can insert dynamic values into the prompt by using double braces:

- `{{documentation_type}}`, `{{date}}`, etc.

These are **placeholders** that will be filled with arguments provided by the **parameter** of the API call during execution.
"""

    prompt = f"""
You are an expert at analyzing screen recordings and creating automation API definitions.

Analyze the provided video recording of a user interacting with a software application. Your task is to:

1. **Identify the core workflow** - What is the user trying to accomplish?
2. **Break down the steps** - What are the individual actions taken?
3. **Identify dynamic elements** - What parts of the workflow would need to be parameterized?
4. **Create an API definition** - Generate a complete API definition that could automate this workflow.

{how_to_prompt_instructions}

## Analysis Guidelines

- Watch for UI state changes and transitions
- Note any user inputs (text, clicks, selections)
- Identify elements that might vary between executions (dates, names, values)
- Pay attention to error conditions or unexpected UI states
- Look for confirmation steps or validation checks

## API Definition Requirements

Create an API definition with:

1. **Name**: A clear, descriptive name for the automation (use snake_case)
2. **Description**: A comprehensive description of what the API does
3. **Parameters**: List of parameters needed (with types: string, number, boolean, list)
4. **Prompt**: Detailed step-by-step instructions following the HOW_TO_PROMPT.md format
5. **Prompt Cleanup**: Instructions to return the system to its original state
6. **Response Example**: Expected JSON structure for the result

## Response Format

Return your analysis as a structured API definition that follows this exact format:

```json
{{
  "name": "descriptive_api_name",
  "description": "Comprehensive description of the automation process",
  "parameters": [
    {{
      "name": "parameter_name",
      "type": "string|number|boolean|list",
      "description": "Clear description of what this parameter does",
      "default": null
    }}
  ],
  "prompt": "Step-by-step automation instructions following HOW_TO_PROMPT.md format...",
  "prompt_cleanup": "Instructions to return system to original state...",
  "response_example": {{
    "status": "success",
    "result": "Expected result structure"
  }}
}}
```

Focus on creating a robust, reusable automation that could handle variations in the workflow while maintaining reliability.
"""

    return prompt


@ai_router.post('/analyze', response_model=VideoAnalysisResponse)
async def analyze_video(video: UploadFile = File(...)) -> VideoAnalysisResponse:
    """
    Analyze a video recording and generate an API definition for automation.

    This endpoint accepts a video file upload, analyzes it using Google Vertex Gemini Pro,
    and returns a structured API definition that can be used to automate the workflow
    shown in the video.
    """

    # Validate file type
    if not video.content_type or not video.content_type.startswith('video/'):
        raise HTTPException(
            status_code=400, detail='Invalid file type. Please upload a video file.'
        )

    # Check file size (limit to 50MB)
    max_size = 50 * 1024 * 1024  # 50MB
    video_content = await video.read()
    if len(video_content) > max_size:
        raise HTTPException(
            status_code=400, detail='Video file too large. Maximum size is 50MB.'
        )

    try:
        # Initialize Vertex AI
        model = initialize_vertex_ai()

        # Create video part for Gemini
        video_part = Part.from_data(data=video_content, mime_type=video.content_type)

        # Create analysis prompt
        analysis_prompt = create_analysis_prompt()

        # Generate analysis
        logger.info(f'Analyzing video: {video.filename} ({len(video_content)} bytes)')

        response = model.generate_content([analysis_prompt, video_part])

        if not response.text:
            raise HTTPException(
                status_code=500, detail='No response generated from video analysis'
            )

        # Parse the response to extract API definition
        response_text = response.text.strip()

        # Try to extract JSON from the response
        import json
        import re

        # Look for JSON block in the response
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if not json_match:
            # Try to find JSON without code blocks
            json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)

        if not json_match:
            raise HTTPException(
                status_code=500,
                detail='Could not extract valid API definition from analysis',
            )

        try:
            api_def_dict = json.loads(json_match.group(1))
        except json.JSONDecodeError as e:
            logger.error(f'Failed to parse JSON from response: {e}')
            raise HTTPException(
                status_code=500, detail='Generated API definition is not valid JSON'
            )

        # Validate required fields
        required_fields = [
            'name',
            'description',
            'parameters',
            'prompt',
            'response_example',
        ]
        for field in required_fields:
            if field not in api_def_dict:
                raise HTTPException(
                    status_code=500,
                    detail=f'Generated API definition missing required field: {field}',
                )

        # Convert parameters to Parameter objects
        parameters = []
        for param_dict in api_def_dict.get('parameters', []):
            if not isinstance(param_dict, dict):
                continue
            parameters.append(
                Parameter(
                    name=param_dict.get('name', ''),
                    type=param_dict.get('type', 'string'),
                    description=param_dict.get('description', ''),
                    default=param_dict.get('default'),
                )
            )

        print(api_def_dict)

        # Create APIDefinition object
        api_definition = APIDefinition(
            name=api_def_dict['name'],
            description=api_def_dict['description'],
            parameters=parameters,
            response_example=api_def_dict['response_example'],
        )

        # Calculate confidence score based on response quality
        confidence_score = calculate_confidence_score(response_text, api_def_dict)

        # Create summary
        analysis_summary = create_analysis_summary(response_text, api_def_dict)

        logger.info(
            f'Successfully analyzed video and generated API definition: {api_definition.name}'
        )

        return VideoAnalysisResponse(
            api_definition=api_definition,
            analysis_summary=analysis_summary,
            confidence_score=confidence_score,
            prompt=api_def_dict['prompt'],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Error analyzing video: {str(e)}')
        raise HTTPException(
            status_code=500, detail=f'Failed to analyze video: {str(e)}'
        )


def calculate_confidence_score(
    response_text: str, api_def_dict: Dict[str, Any]
) -> float:
    """Calculate a confidence score for the generated API definition"""
    score = 0.0

    # Check if all required fields are present and non-empty
    required_fields = ['name', 'description', 'prompt', 'response_example']
    for field in required_fields:
        if field in api_def_dict and api_def_dict[field]:
            score += 0.2

    # Check prompt quality indicators
    prompt = api_def_dict.get('prompt', '')
    if 'Step' in prompt or 'step' in prompt:
        score += 0.1
    if 'Expected UI' in prompt or 'Action' in prompt:
        score += 0.1
    if len(prompt) > 200:  # Detailed prompt
        score += 0.1

    # Check if parameters are defined
    if api_def_dict.get('parameters') and len(api_def_dict['parameters']) > 0:
        score += 0.1

    # Ensure score is between 0 and 1
    return min(1.0, max(0.0, score))


def create_analysis_summary(response_text: str, api_def_dict: Dict[str, Any]) -> str:
    """Create a human-readable summary of the analysis"""
    name = api_def_dict.get('name', 'Unknown')
    description = api_def_dict.get('description', 'No description available')
    param_count = len(api_def_dict.get('parameters', []))

    summary = f"Generated API definition '{name}' with {param_count} parameters.\n\n"
    summary += f'Description: {description}\n\n'

    if param_count > 0:
        summary += 'Parameters:\n'
        for param in api_def_dict.get('parameters', []):
            param_name = param.get('name', 'unknown')
            param_type = param.get('type', 'string')
            param_desc = param.get('description', 'No description')
            summary += f'- {param_name} ({param_type}): {param_desc}\n'

    return summary
