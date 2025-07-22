"""
Interactive mode routes for workflow recording and automation.
"""

import asyncio
import logging
import os
import tempfile
from datetime import datetime
from typing import Dict, List, Optional
import json
import base64

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
import google.generativeai as genai

from server.computer_use import sampling_loop
from server.computer_use.tools.collection import ToolCollection
from server.utils.auth import get_api_key
from server.database import db
from server.database.models import Workflow, Recording, Action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/interactive", tags=["interactive"])

# Pydantic models for request/response
class WorkflowRequest(BaseModel):
    name: str
    description: Optional[str] = None
    steps: List[Dict] = []
    sessionId: str

class ActionRequest(BaseModel):
    sessionId: str
    action: Dict
    stepContext: Optional[Dict] = None

class ProcessRecordingRequest(BaseModel):
    recordingPath: str
    sessionId: str
    workflowContext: Optional[Dict] = None

class RecordingResponse(BaseModel):
    id: str
    filename: str
    duration: Optional[int] = None
    fileSize: Optional[int] = None
    createdAt: datetime
    processed: bool = False
    processing: bool = False
    description: Optional[str] = None
    extractedActions: Optional[List[Dict]] = None

# Initialize Gemini client
def get_gemini_client():
    """Initialize Google Gemini client with API key from environment."""
    api_key = os.getenv('GOOGLE_GEMINI_API_KEY')
    if not api_key:
        raise HTTPException(status_code=500, detail="Google Gemini API key not configured")
    
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-1.5-pro')

def load_how_to_prompt():
    """Load the HOW_TO_PROMPT.md content for Gemini processing."""
    try:
        with open('HOW_TO_PROMPT.md', 'r') as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("HOW_TO_PROMPT.md not found, using default instructions")
        return """
# How to Prompt for Computer Use Actions

Analyze the screen recording and extract step-by-step actions that can be automated.

For each action, provide:
- Type: click, type, key_press, scroll, wait, extract, ui_check
- Description: What the action does
- Parameters: Specific details for the action
- Expected UI: What should be visible before this action
- Prompt: Custom instructions if needed

Focus on creating reliable, repeatable automation steps.
"""

@router.post("/start-recording/{session_id}")
async def start_recording(session_id: str, api_key: str = Depends(get_api_key)):
    """Start screen recording for a session."""
    try:
        # Check if session exists and is ready
        session = await db.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if session.state != 'ready':
            raise HTTPException(status_code=400, detail="Session is not ready for recording")
        
        # Create recording record
        recording_data = {
            'session_id': session_id,
            'filename': f"recording_{session_id}_{int(datetime.now().timestamp())}.webm",
            'started_at': datetime.now(),
            'status': 'recording'
        }
        
        recording_id = await db.create_recording(recording_data)
        
        # Start recording process (this would integrate with your VNC/desktop recording solution)
        # For now, we'll simulate the recording start
        logger.info(f"Started recording for session {session_id}, recording ID: {recording_id}")
        
        return {"recordingId": recording_id, "status": "started"}
        
    except Exception as e:
        logger.error(f"Failed to start recording: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {str(e)}")

@router.post("/stop-recording/{session_id}")
async def stop_recording(session_id: str, api_key: str = Depends(get_api_key)):
    """Stop screen recording and return recording info."""
    try:
        # Get the active recording for this session
        recording = await db.get_active_recording(session_id)
        if not recording:
            raise HTTPException(status_code=404, detail="No active recording found")
        
        # Stop recording and update record
        stopped_at = datetime.now()
        duration = int((stopped_at - recording['started_at']).total_seconds())
        
        recording_update = {
            'id': recording['id'],
            'stopped_at': stopped_at,
            'status': 'completed',
            'duration': duration,
            'file_size': 1024 * 1024 * 5  # 5MB simulated
        }
        
        await db.update_recording(recording_update)
        
        # Return recording path for processing
        recording_path = f"/recordings/{recording['filename']}"
        
        logger.info(f"Stopped recording for session {session_id}")
        
        return {"recordingPath": recording_path, "recordingId": recording['id']}
        
    except Exception as e:
        logger.error(f"Failed to stop recording: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to stop recording: {str(e)}")

@router.post("/process-recording")
async def process_recording(request: ProcessRecordingRequest, api_key: str = Depends(get_api_key)):
    """Process recording with Google Gemini to extract actions."""
    try:
        # Get recording from database
        recording = await db.get_recording_by_path(request.recordingPath)
        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found")
        
        # Mark as processing
        recording_update = {
            'id': recording['id'],
            'status': 'processing'
        }
        await db.update_recording(recording_update)
        
        # Load HOW_TO_PROMPT instructions
        how_to_prompt = load_how_to_prompt()
        
        # Initialize Gemini client
        model = get_gemini_client()
        
        # For now, we'll simulate video processing since we don't have actual video files
        # In a real implementation, you would:
        # 1. Extract frames from the video
        # 2. Send frames to Gemini Vision API
        # 3. Get action suggestions
        
        # Simulated Gemini response
        prompt = f"""
{how_to_prompt}

Analyze this screen recording and extract the following workflow steps:

Context: {json.dumps(request.workflowContext) if request.workflowContext else 'No context provided'}

Please provide a JSON response with the following structure:
{{
    "description": "Brief description of what was recorded",
    "suggestedActions": [
        {{
            "id": "unique_id",
            "type": "click|type|key_press|scroll|wait|extract|ui_check",
            "description": "What this action does",
            "parameters": {{}},
            "expectedUI": "What should be visible before this action",
            "prompt": "Custom instructions if needed"
        }}
    ]
}}
"""
        
        # Simulate Gemini API call
        # In real implementation: response = model.generate_content(prompt)
        
        # Simulated response based on common workflow actions
        simulated_response = {
            "description": "User performed login and navigation actions",
            "suggestedActions": [
                {
                    "id": f"action_{int(datetime.now().timestamp())}_1",
                    "type": "click",
                    "description": "Click on username field",
                    "parameters": {"element": "username input field"},
                    "expectedUI": "Login page with username and password fields visible",
                    "prompt": "Click on the username field to focus it"
                },
                {
                    "id": f"action_{int(datetime.now().timestamp())}_2",
                    "type": "type",
                    "description": "Enter username",
                    "parameters": {"text": "{{username}}"},
                    "expectedUI": "Username field is focused and ready for input",
                    "prompt": "Type the username into the focused field"
                },
                {
                    "id": f"action_{int(datetime.now().timestamp())}_3",
                    "type": "key_press",
                    "description": "Press Tab to move to password field",
                    "parameters": {"keys": "TAB"},
                    "expectedUI": "Username field contains entered text",
                    "prompt": "Press Tab to move focus to the password field"
                }
            ]
        }
        
        # Update recording with extracted actions
        recording_update = {
            'id': recording['id'],
            'status': 'processed',
            'description': simulated_response["description"],
            'extracted_actions': simulated_response["suggestedActions"]
        }
        await db.update_recording(recording_update)
        
        logger.info(f"Processed recording {recording['id']} with {len(simulated_response['suggestedActions'])} actions")
        
        return simulated_response
        
    except Exception as e:
        logger.error(f"Failed to process recording: {str(e)}")
        # Mark recording as failed
        if 'recording' in locals():
            recording_update = {
                'id': recording['id'],
                'status': 'failed'
            }
            await db.update_recording(recording_update)
        raise HTTPException(status_code=500, detail=f"Failed to process recording: {str(e)}")

@router.post("/execute-action")
async def execute_action(request: ActionRequest, api_key: str = Depends(get_api_key)):
    """Execute a single action using computer use tools."""
    try:
        # Get session info
        session = await db.get_session(request.sessionId)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if session.state != 'ready':
            raise HTTPException(status_code=400, detail="Session is not ready for action execution")
        
        action = request.action
        action_type = action.get('type')
        parameters = action.get('parameters', {})
        
        # For now, simulate action execution since we don't have actual computer use tools integrated
        # In a real implementation, you would integrate with the computer use tools here
        
        # Simulate action execution
        if action_type == 'click':
            result = {"success": True, "message": f"Clicked on {parameters.get('element', 'element')}"}
        elif action_type == 'type':
            result = {"success": True, "message": f"Typed: {parameters.get('text', '')}"}
        elif action_type == 'key_press':
            result = {"success": True, "message": f"Pressed keys: {parameters.get('keys', '')}"}
        elif action_type == 'scroll':
            direction = parameters.get('direction', 'down')
            result = {"success": True, "message": f"Scrolled {direction}"}
        elif action_type == 'wait':
            duration = parameters.get('duration', 1)
            await asyncio.sleep(duration)
            result = {"success": True, "message": f"Waited {duration} seconds"}
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action type: {action_type}")
        
        # Log the action execution
        logger.info(f"Executed action {action.get('id')} of type {action_type} for session {request.sessionId}")
        
        return {"success": True, "result": result, "actionId": action.get('id')}
        
    except Exception as e:
        logger.error(f"Failed to execute action: {str(e)}")
        return {"success": False, "error": str(e), "actionId": action.get('id')}

@router.post("/workflows")
async def save_workflow(request: WorkflowRequest, api_key: str = Depends(get_api_key)):
    """Save a workflow definition."""
    try:
        workflow_data = {
            'name': request.name,
            'description': request.description,
            'steps': request.steps,
            'session_id': request.sessionId,
            'created_at': datetime.now()
        }
        
        workflow_id = await db.create_workflow(workflow_data)
        
        logger.info(f"Saved workflow {workflow_id} for session {request.sessionId}")
        
        return {"workflowId": workflow_id, "status": "saved"}
        
    except Exception as e:
        logger.error(f"Failed to save workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save workflow: {str(e)}")

@router.get("/recordings/{session_id}")
async def get_recordings(session_id: str, api_key: str = Depends(get_api_key)):
    """Get all recordings for a session."""
    try:
        recordings = await db.get_recordings_by_session(session_id)
        
        recording_responses = []
        for recording in recordings:
            recording_responses.append(RecordingResponse(
                id=recording.id,
                filename=recording.filename,
                duration=recording.duration,
                fileSize=recording.file_size,
                createdAt=recording.created_at,
                processed=recording.status == 'processed',
                processing=recording.status == 'processing',
                description=recording.description,
                extractedActions=recording.extracted_actions
            ))
        
        return {"recordings": recording_responses}
        
    except Exception as e:
        logger.error(f"Failed to get recordings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get recordings: {str(e)}")

@router.post("/recordings/{session_id}/{recording_id}/play")
async def play_recording(session_id: str, recording_id: str, api_key: str = Depends(get_api_key)):
    """Get playback URL for a recording."""
    try:
        recording = await db.get_recording(recording_id)
        if not recording or recording.session_id != session_id:
            raise HTTPException(status_code=404, detail="Recording not found")
        
        # In a real implementation, generate a signed URL or serve the file
        playback_url = f"/api/recordings/{recording_id}/stream"
        
        return {"playbackUrl": playback_url}
        
    except Exception as e:
        logger.error(f"Failed to get playback URL: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get playback URL: {str(e)}")

@router.get("/recordings/{session_id}/{recording_id}/download")
async def download_recording(session_id: str, recording_id: str, api_key: str = Depends(get_api_key)):
    """Download a recording file."""
    try:
        recording = await db.get_recording(recording_id)
        if not recording or recording.session_id != session_id:
            raise HTTPException(status_code=404, detail="Recording not found")
        
        # In a real implementation, return the actual file
        # For now, return a placeholder response
        raise HTTPException(status_code=501, detail="Download not implemented yet")
        
    except Exception as e:
        logger.error(f"Failed to download recording: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to download recording: {str(e)}")

@router.delete("/recordings/{session_id}/{recording_id}")
async def delete_recording(session_id: str, recording_id: str, api_key: str = Depends(get_api_key)):
    """Delete a recording."""
    try:
        recording = await db.get_recording(recording_id)
        if not recording or recording.session_id != session_id:
            raise HTTPException(status_code=404, detail="Recording not found")
        
        await db.delete_recording(recording_id)
        
        # In a real implementation, also delete the actual file
        logger.info(f"Deleted recording {recording_id}")
        
        return {"status": "deleted"}
        
    except Exception as e:
        logger.error(f"Failed to delete recording: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete recording: {str(e)}")

@router.post("/screenshot/{session_id}")
async def take_screenshot(session_id: str, api_key: str = Depends(get_api_key)):
    """Take a screenshot of the session."""
    try:
        # Get session info
        session = await db.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if session.state != 'ready':
            raise HTTPException(status_code=400, detail="Session is not ready for screenshots")
        
        # In a real implementation, capture screenshot from VNC session
        # For now, return a placeholder
        raise HTTPException(status_code=501, detail="Screenshot not implemented yet")
        
    except Exception as e:
        logger.error(f"Failed to take screenshot: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to take screenshot: {str(e)}")

@router.post("/send-keys/{session_id}")
async def send_keys(session_id: str, keys_data: Dict, api_key: str = Depends(get_api_key)):
    """Send key combinations to the session."""
    try:
        # Get session info
        session = await db.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if session.state != 'ready':
            raise HTTPException(status_code=400, detail="Session is not ready for key input")
        
        keys = keys_data.get('keys', '')
        
        # In a real implementation, send keys to VNC session
        # For now, simulate success
        logger.info(f"Sent keys '{keys}' to session {session_id}")
        
        return {"status": "sent", "keys": keys}
        
    except Exception as e:
        logger.error(f"Failed to send keys: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to send keys: {str(e)}")

@router.get("/workflows/{session_id}")
async def get_workflows(session_id: str, api_key: str = Depends(get_api_key)):
    """Get all workflows for a session."""
    try:
        workflows = await db.get_workflows_by_session(session_id)
        return {"workflows": workflows}
        
    except Exception as e:
        logger.error(f"Failed to get workflows: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get workflows: {str(e)}")