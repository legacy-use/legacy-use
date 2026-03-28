# `analyze_video` LLM Call Reconstruction

This document captures the current `analyze_video` LLM call as implemented in the codebase, including:

- the exact backend entrypoint
- the exact request assembly
- the exact rendered prompt text
- the exact response model the model output is parsed into
- the transport/input contract
- implementation quirks that matter for faithful reproduction


## Exact Backend Call Path

The current implementation is:

```python
@teaching_mode_router.post('/analyze-video', response_model=VideoAnalysisResponse)
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

    # Check file size
    video_content = await video.read()
    if len(video_content) > 120 * 1024 * 1024:  # 120MB
        raise HTTPException(
            status_code=400,
            detail='Video file too large. Maximum size is 120MB.',
        )

    client = instructor.from_provider(
        'google/gemini-3-flash-preview',
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
```

## LLM Request Parameters

These values are hard-coded by the current implementation:

- Provider wrapper: `instructor`
- Provider string: `google/gemini-3-flash-preview`
- Async mode: `True`
- API key source: `settings.GOOGLE_GENAI_API_KEY`
- Message count: `1`
- Message role: `user`
- Message parts:
  - text instructions from `create_analysis_prompt()`
  - binary video bytes from the uploaded file

## Exact Message Shape

The message assembled for the model is logically:

```python
messages = [
    Content(
        role='user',
        parts=[
            Part.from_text(text=create_analysis_prompt()),
            Part.from_bytes(data=video_content, mime_type='video/mp4'),
        ],
    )
]
```

Notes:

- The uploaded bytes are forwarded as `mime_type='video/mp4'` regardless of the original upload MIME type.
- The entire uploaded video is read into memory before the model call.

## Exact Rendered Prompt

This is the exact string currently produced by `create_analysis_prompt()` at runtime.

Important: this is the rendered prompt as sent to the model, not a cleaned-up interpretation. It includes the current `Ellipsis` bug caused by f-string interpolation of `{...}` in two places.

```text

You are an expert at analyzing screen recordings and creating automation API definitions.

Analyze the provided video recording of a user interacting with a software application. Your task is to:

1. **Identify the core workflow** - What is the user trying to accomplish?
2. **Break down the steps** - What are the individual actions taken?
3. **Identify dynamic elements** - What parts of the workflow would need to be parameterized? Like text, dates, names, values, etc. the user entered, selected or modified. Make sure to replace the identified parameters with the `Ellipsis` syntax.
4. **Original state** - Describe the original state of the application before the user started the workflow and how to get back to it, meant to be used as a cleanup prompt (not within the regular workflow, nor ui_not_as_expected).

## Analysis Guidelines

- Watch for UI state changes and transitions
- Note any user inputs (text, clicks, selections)
- Identify elements that might vary between executions (dates, names, values), and replace them with the `Ellipsis` syntax in the prompt.
- Pay attention to error conditions or unexpected UI states
- Look for confirmation steps or validation checks

Focus on creating a robust, reusable automation that could handle variations in the workflow while maintaining reliability.


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
```

## Prompt Source Template

The prompt above is built from this function:

```python
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
```

## Exact Response Model

The model output is parsed into these Pydantic models:

```python
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


class Parameter(BaseModel):
    name: str
    type: str
    description: str
    default: Optional[Union[str, List[Any]]] = None


class VideoAnalysisResponse(BaseModel):
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
```

## Equivalent JSON Shape

This is the effective JSON shape expected back from the model:

```json
{
  "name": "string",
  "description": "string",
  "actions": [
    {
      "title": "string",
      "instruction": "string",
      "tool": "type"
    }
  ],
  "prompt_cleanup": "string",
  "parameters": [
    {
      "name": "string",
      "type": "string",
      "description": "string",
      "default": "string | array | null"
    }
  ],
  "response_example": {}
}
```

Valid `actions[].tool` values are:

- `type`
- `press_key`
- `click`
- `scroll_up`
- `scroll_down`
- `ui_not_as_expected`
- `extract_tool`

## What the Frontend Sends

The frontend sends the upload as `multipart/form-data`:

```typescript
export const analyzeVideoTeachingModeAnalyzeVideoPost = (
  bodyAnalyzeVideoTeachingModeAnalyzeVideoPost: BodyAnalyzeVideoTeachingModeAnalyzeVideoPost,
) => {
  const formData = new FormData();
  formData.append(`video`, bodyAnalyzeVideoTeachingModeAnalyzeVideoPost.video);

  return customInstance<VideoAnalysisResponse>({
    url: `/teaching-mode/analyze-video`,
    method: 'POST',
    headers: { 'Content-Type': 'multipart/form-data' },
    data: formData,
  });
};
```

The frontend wrapper used by the app is:

```typescript
export const analyzeVideo = async (videoFile: Blob) => {
  return analyzeVideoTeachingModeAnalyzeVideoPost({ video: videoFile });
};
```

## Reconstruction Script

This Python snippet reproduces the current backend LLM call shape:

```python
import instructor
from google.genai.types import Content, Part

from server.routes.teaching_mode import VideoAnalysisResponse
from server.settings import settings
from server.utils.teaching_mode import create_analysis_prompt


def build_messages(video_content: bytes):
    instructions_part = Part.from_text(text=create_analysis_prompt())
    video_part = Part.from_bytes(data=video_content, mime_type='video/mp4')
    return [Content(role='user', parts=[instructions_part, video_part])]


async def analyze_video_bytes(video_content: bytes):
    client = instructor.from_provider(
        'google/gemini-3-flash-preview',
        async_client=True,
        api_key=settings.GOOGLE_GENAI_API_KEY,
    )

    return await client.chat.completions.create(
        messages=build_messages(video_content),  # type: ignore
        response_model=VideoAnalysisResponse,
    )
```

## What Happens After This Call

The LLM response is not executed directly. The frontend later converts `actions` into a plain prompt string:

```typescript
const prompt = analyzeResult.actions
  .map((action, index) => `Step ${index + 1}: ${action.title}\n${action.instruction}`)
  .join('\n---\n\n');
```

It then imports that as an API definition together with:

- `prompt_cleanup`
- `response_example`
- `parameters`

## Reproduction-Critical Quirks

These details matter if you want to reproduce the current behavior exactly rather than approximately:

1. The route accepts any `video/*` upload, but the LLM call always labels the bytes as `video/mp4`.
2. The prompt text currently contains `Ellipsis` in two places where the source code intended to mention `{...}` syntax.
3. The entire file is buffered into memory before the LLM call.
4. The model output is constrained through `response_model=VideoAnalysisResponse`, so malformed output is expected to fail parsing rather than pass through as free text.
