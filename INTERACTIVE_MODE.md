# Interactive Mode Documentation

## Overview

The Interactive Mode is a new feature that provides a comprehensive workflow recording and automation system. It combines remote desktop access with intelligent workflow capture and execution capabilities powered by Google Gemini AI.

## Features

### 🎬 Screen Recording
- **Real-time Recording**: Record your interactions with the remote desktop session
- **Automatic Processing**: Recordings are automatically analyzed by Google Gemini
- **Action Extraction**: AI extracts actionable workflow steps from recordings
- **Recording Management**: View, play, download, and delete recordings

### 🔧 Workflow Editor
- **Drag & Drop Interface**: Intuitive workflow step management
- **Action Types**: Support for multiple action types:
  - **Click**: Click on UI elements
  - **Type**: Enter text into fields
  - **Key Press**: Send keyboard shortcuts
  - **Scroll**: Scroll up or down
  - **Wait**: Add delays between actions
  - **Extract**: Extract data from the UI
  - **UI Check**: Verify UI state before proceeding

### 🖥️ Enhanced Remote Desktop
- **Full-Screen Support**: Immersive remote desktop experience
- **Zoom Controls**: Zoom in/out and fit to screen
- **Screenshot Capture**: Take screenshots of the remote session
- **Key Shortcuts**: Send common key combinations (Ctrl+Alt+Del, Alt+Tab, etc.)
- **Connection Status**: Real-time connection monitoring

### 🤖 AI-Powered Automation
- **Google Gemini Integration**: Uses HOW_TO_PROMPT.md instructions for intelligent action extraction
- **Context-Aware**: Understands workflow context and suggests appropriate actions
- **Customizable Prompts**: Add custom instructions for specific steps and actions

## Getting Started

### Prerequisites

1. **Google Gemini API Key**: Set up your Google Gemini API key in environment variables:
   ```bash
   export GOOGLE_GEMINI_API_KEY="your-api-key-here"
   ```

2. **Active Session**: You need a session in "ready" state to use Interactive Mode

### Accessing Interactive Mode

1. Navigate to **Sessions** in the main navigation
2. Select a session that is in "ready" state
3. Click the **"Interactive Mode"** button in the session details

### Using the Interface

The Interactive Mode interface is split into two main panels:

#### Left Panel: Workflow Management
- **Workflow Editor Tab**: Create and manage workflow steps and actions
- **Recording Tab**: Control screen recording and view recording history

#### Right Panel: Remote Desktop
- Enhanced VNC viewer with additional controls and features

## Workflow Creation

### Method 1: Recording-Based (Recommended)

1. **Start Recording**:
   - Switch to the "Recording" tab
   - Click "Start Recording"
   - Perform your desired actions on the remote desktop
   - Click "Stop Recording"

2. **AI Processing**:
   - The recording is automatically sent to Google Gemini
   - AI analyzes the recording using HOW_TO_PROMPT.md instructions
   - Extracted actions are automatically added to your workflow

3. **Review and Edit**:
   - Switch to the "Workflow Editor" tab
   - Review the extracted actions
   - Edit descriptions, parameters, and prompts as needed
   - Reorder or modify steps using the drag-and-drop interface

### Method 2: Manual Creation

1. **Add Workflow Step**:
   - Click "Add Step" in the Workflow Editor
   - Enter step name and description
   - Add custom prompt instructions (optional)

2. **Add Actions**:
   - Click "Add Action" within a step
   - Select action type (Click, Type, Key Press, etc.)
   - Configure action parameters
   - Set expected UI state
   - Add custom prompt (optional)

3. **Configure Parameters**:
   - **Click Actions**: Describe the element to click
   - **Type Actions**: Specify the text to enter
   - **Key Press Actions**: Define key combinations (e.g., "RETURN", "CTRL+C")
   - **Scroll Actions**: Choose direction (up/down)
   - **Wait Actions**: Set duration in seconds

## Workflow Execution

### Individual Action Execution
- Click the play button (▶️) next to any action to execute it individually
- View execution results and success/failure status
- Use for testing and debugging workflows

### Batch Execution
- Click "Run All" to execute the entire workflow
- Actions are executed sequentially with 1-second delays
- Monitor progress and results in real-time

## Recording Management

### Recording History
- View all recordings for the current session
- See recording duration, file size, and processing status
- Access recordings that have been processed by Gemini

### Recording Actions
- **Play**: View the recording in a new tab
- **Download**: Download the recording file
- **Delete**: Remove the recording and associated data

### Recording Tips
- Perform actions slowly and deliberately
- Wait for UI elements to load before interacting
- Keep recordings focused on specific tasks
- Use clear, deliberate mouse movements and clicks

## Advanced Features

### Custom Prompts
- Add custom instructions at the step level for complex workflows
- Override default action prompts for specific use cases
- Use placeholder variables like `{{username}}` for dynamic content

### Expected UI States
- Define what the UI should look like before each action
- Helps with workflow reliability and debugging
- Used by AI for better action extraction

### Execution Logging
- All action executions are logged with timestamps
- View success/failure status and error messages
- Track execution times for performance analysis

## API Integration

The Interactive Mode exposes several API endpoints:

### Recording Endpoints
- `POST /api/interactive/start-recording/{session_id}` - Start recording
- `POST /api/interactive/stop-recording/{session_id}` - Stop recording
- `POST /api/interactive/process-recording` - Process with Gemini
- `GET /api/interactive/recordings/{session_id}` - List recordings

### Workflow Endpoints
- `POST /api/interactive/workflows` - Save workflow
- `GET /api/interactive/workflows/{session_id}` - List workflows
- `POST /api/interactive/execute-action` - Execute single action

### Utility Endpoints
- `POST /api/interactive/screenshot/{session_id}` - Take screenshot
- `POST /api/interactive/send-keys/{session_id}` - Send key combinations

## Configuration

### Environment Variables
- `GOOGLE_GEMINI_API_KEY` - Required for AI processing
- `DATABASE_URL` - Database connection string (default: SQLite)

### HOW_TO_PROMPT.md
The system uses the `HOW_TO_PROMPT.md` file to instruct Google Gemini on how to analyze recordings and extract actions. You can customize this file to improve AI performance for your specific use cases.

## Database Schema

The Interactive Mode adds four new database tables:

- **workflows** - Workflow definitions and metadata
- **recordings** - Screen recording information and status
- **actions** - Individual workflow actions and parameters
- **execution_logs** - Action execution history and results

## Troubleshooting

### Common Issues

1. **"Interactive Mode" button not visible**
   - Ensure the session is in "ready" state
   - Check that the session is not archived

2. **Recording fails to start**
   - Verify session connectivity
   - Check browser permissions for media recording

3. **AI processing fails**
   - Verify Google Gemini API key is set correctly
   - Check network connectivity
   - Review API quotas and limits

4. **Action execution fails**
   - Verify session is still active and ready
   - Check action parameters are correctly configured
   - Review execution logs for error details

### Debug Mode
Enable debug logging by setting the log level to DEBUG in your environment to get detailed information about workflow execution and API calls.

## Future Enhancements

Planned improvements for Interactive Mode include:

- **Real-time Action Suggestions**: Live AI suggestions during recording
- **Workflow Templates**: Pre-built workflows for common tasks
- **Conditional Logic**: Support for if/else conditions in workflows
- **Variable Management**: Better support for dynamic values and parameters
- **Integration Testing**: Automated workflow validation and testing
- **Performance Analytics**: Detailed metrics and performance insights

## Support

For issues and questions related to Interactive Mode:

1. Check the troubleshooting section above
2. Review the execution logs for error details
3. Verify your Google Gemini API configuration
4. Check the browser console for frontend errors

---

*Interactive Mode is designed to make workflow automation accessible and intelligent, combining the power of AI with intuitive user interfaces for maximum productivity.*