"""
AI-powered analysis routes.
"""

import logging
from typing import Any, Dict, List, Literal

import instructor
from fastapi import APIRouter, File, HTTPException, UploadFile
from google.genai.types import Content, Part
from pydantic import BaseModel, Field

from server.models.base import Parameter
from server.settings import settings

# Set up logging
logger = logging.getLogger(__name__)

# Create router
ai_router = APIRouter(prefix='/ai', tags=['AI Analysis'])


class ActionStep(BaseModel):
    title: str = Field(
        description='A short title summing up the user intent for the action, e.g. "Open settings menu"',
    )
    instruction: str = Field(
        description='Describe the action the user took to complete the task, formulated as instruction for the operator. Replace concrete values, inputs and selections with {...} placeholders based on the parameters of the API call, in particular dates, names, texts, values, etc.',
    )
    tool: Literal[
        'type',
        'press_key',
        'click',
        'scroll_up',
        'scroll_down',
        'ui_not_as_expected',
        'extract_tool',
    ] = Field(
        description='The tool to use to complete the action',
    )


class VideoAnalysisResponse(BaseModel):
    """Response model for video analysis"""

    name: str = Field(
        description='A short name for the automation',
    )
    description: str = Field(
        description='A short summary of the automation, remain high level',
    )
    actions: List[ActionStep] = Field(
        description='Describe the expected screen state, instruct the operator to get the system into the initial state. Then describe the actions the user took to complete the task in great detail, in particular which buttons or input fields are used, use the tools available to the model to describe the actions, follow the format of the HOW_TO_PROMPT.md file',
    )
    prompt_cleanup: str = Field(
        description='Instructions to return the system to its original state'
    )
    parameters: List[Parameter] = Field(
        description='Parameters and user input needed to run the automation another time with different values',
    )
    response_example: Dict[str, Any] = Field(
        description='Expected response from the automation',
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

### Using Braces (`{...}`)

You can insert dynamic values into the prompt by using single braces:

- `{documentation_type}`, `{date}`, etc.

These are **placeholders** that will be filled with arguments provided by the **parameter** of the API call during execution. Use the concrete values as default values for the parameters.
"""

    prompt = f"""
You are an expert at analyzing screen recordings and creating automation API definitions.

Analyze the provided video recording of a user interacting with a software application. Your task is to:

1. **Identify the core workflow** - What is the user trying to accomplish?
2. **Break down the steps** - What are the individual actions taken?
3. **Identify dynamic elements** - What parts of the workflow would need to be parameterized? Like text, dates, names, values, etc. the user entered, selected or modified. Make sure to replace the identified parameters with the `{...}` syntax.
4. **Original state** - Describe the original state of the application before the user started the workflow and how to get back to it, meant to be used as a cleanup prompt (not within the regular workflow, nor ui_not_as_expected).

## Analysis Guidelines

- Watch for UI state changes and transitions
- Note any user inputs (text, clicks, selections)
- Identify elements that might vary between executions (dates, names, values), and replace them with the `{...}` syntax in the prompt.
- Pay attention to error conditions or unexpected UI states
- Look for confirmation steps or validation checks

Focus on creating a robust, reusable automation that could handle variations in the workflow while maintaining reliability.

{how_to_prompt_instructions}
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

    instructions_part = Part.from_text(text=create_analysis_prompt())
    video_part = Part.from_bytes(data=video_content, mime_type='video/mp4')

    messages = [Content(role='user', parts=[instructions_part, video_part])]

    return await client.chat.completions.create(
        messages=messages,  # type: ignore
        response_model=VideoAnalysisResponse,
    )
