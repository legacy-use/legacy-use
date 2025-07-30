"""
AI-powered analysis routes.
"""

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
import vertexai
from vertexai.generative_models import GenerativeModel
import instructor

from server.settings import settings

# Set up logging
logger = logging.getLogger(__name__)

# Create router
ai_router = APIRouter(prefix='/ai', tags=['AI Analysis'])


class VideoAnalysisResponse(BaseModel):
    """Response model for video analysis"""

    text: str


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
            status_code=400,
            detail='Invalid file type. Please upload a video file.',
        )

    # Check file size (limit to 50MB)
    video_content = await video.read()
    if len(video_content) > 50 * 1024 * 1024:  # 50MB
        raise HTTPException(
            status_code=400,
            detail='Video file too large. Maximum size is 50MB.',
        )

    client = instructor.from_provider(
        'google/gemini-2.5-flash',
        async_client=True,
        api_key=settings.GOOGLE_GENAI_API_KEY,
    )

    return await client.chat.completions.create(
        messages=[
            {'role': 'user', 'content': 'Tell me a joke!'},
        ],
        response_model=VideoAnalysisResponse,
    )
