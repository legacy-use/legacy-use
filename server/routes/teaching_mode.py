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
from server.utils.teaching_mode import create_analysis_prompt

# Set up logging
logger = logging.getLogger(__name__)

# Create router
teaching_mode_router = APIRouter(prefix='/teaching-mode', tags=['Teaching Mode'])


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
