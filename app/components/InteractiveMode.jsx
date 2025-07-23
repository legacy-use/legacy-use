import { PlaylistPlay as PlayAllIcon, Save as SaveIcon } from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Grid,
  Paper,
  Tab,
  Tabs,
  Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getSession } from '../services/apiService';
import RecordingPanel from './RecordingPanel';
import RemoteDesktopPanel from './RemoteDesktopPanel';
import WorkflowEditor from './WorkflowEditor';

const baseApiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8088';

const InteractiveMode = () => {
  const { sessionId } = useParams();
  const [activeTab, setActiveTab] = useState(0);
  const [workflow, setWorkflow] = useState({
    name: 'New Workflow',
    steps: [],
  });
  const [isRecording, setIsRecording] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionResults, setExecutionResults] = useState([]);
  const [currentSession, setCurrentSession] = useState(null);
  const [error, setError] = useState(null);

  // Construct the VNC URL using our proxy endpoint
  // Remove leading slash to avoid double slash when concatenating with baseApiUrl
  const proxyPath = `sessions/${sessionId}/vnc`;

  // VNC parameters with the correct WebSocket path
  // The path parameter tells the VNC client where to find the WebSocket endpoint
  // Make sure to use a path that starts with a single slash
  const websocketPath = `${proxyPath}/websockify`;

  const vncParams = `resize=scale&autoconnect=1&view_only=1&reconnect=1&reconnect_delay=2000&path=${websocketPath}`;

  const vncUrl = `${baseApiUrl}/${proxyPath}/vnc.html?${vncParams}`;

  // Fetch session details
  useEffect(() => {
    if (sessionId) {
      fetchSessionDetails();
    }
  }, [sessionId]);

  const fetchSessionDetails = async () => {
    const session = await getSession(sessionId);
    setCurrentSession(session);
  };

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const handleWorkflowChange = updatedWorkflow => {
    setWorkflow(updatedWorkflow);
  };

  const handleStartRecording = async () => {
    try {
      setIsRecording(true);
      const response = await fetch(`/api/interactive/start-recording/${sessionId}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('apiKey')}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error('Failed to start recording');
      }
    } catch (err) {
      setError('Failed to start recording: ' + err.message);
      setIsRecording(false);
    }
  };

  const handleStopRecording = async () => {
    try {
      const response = await fetch(`/api/interactive/stop-recording/${sessionId}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('apiKey')}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error('Failed to stop recording');
      }

      const result = await response.json();
      setIsRecording(false);

      // Process recording with Gemini
      await processRecordingWithGemini(result.recordingPath);
    } catch (err) {
      setError('Failed to stop recording: ' + err.message);
      setIsRecording(false);
    }
  };

  const processRecordingWithGemini = async recordingPath => {
    try {
      const response = await fetch('/api/interactive/process-recording', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('apiKey')}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          recordingPath,
          sessionId,
          workflowContext: workflow,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to process recording with Gemini');
      }

      const result = await response.json();

      // Add suggested actions to workflow
      if (result.suggestedActions && result.suggestedActions.length > 0) {
        const newStep = {
          id: Date.now(),
          name: 'Recorded Actions',
          description: result.description || 'Actions extracted from recording',
          actions: result.suggestedActions,
          prompt: result.prompt || '',
        };

        setWorkflow(prev => ({
          ...prev,
          steps: [...prev.steps, newStep],
        }));
      }
    } catch (err) {
      setError('Failed to process recording: ' + err.message);
    }
  };

  const executeAction = async (stepId, actionId) => {
    try {
      setIsExecuting(true);
      const step = workflow.steps.find(s => s.id === stepId);
      const action = step?.actions.find(a => a.id === actionId);

      if (!action) {
        throw new Error('Action not found');
      }

      const response = await fetch('/api/interactive/execute-action', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('apiKey')}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          sessionId,
          action,
          stepContext: step,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to execute action');
      }

      const result = await response.json();
      setExecutionResults(prev => [
        ...prev,
        {
          stepId,
          actionId,
          result,
          timestamp: new Date(),
        },
      ]);
    } catch (err) {
      setError('Failed to execute action: ' + err.message);
    } finally {
      setIsExecuting(false);
    }
  };

  const executeAllActions = async () => {
    try {
      setIsExecuting(true);

      for (const step of workflow.steps) {
        for (const action of step.actions) {
          await executeAction(step.id, action.id);
          // Add delay between actions
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
      }
    } catch (err) {
      setError('Failed to execute workflow: ' + err.message);
    } finally {
      setIsExecuting(false);
    }
  };

  const saveWorkflow = async () => {
    try {
      const response = await fetch('/api/interactive/workflows', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('apiKey')}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ...workflow,
          sessionId,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to save workflow');
      }

      // Show success message
      setError(null);
    } catch (err) {
      setError('Failed to save workflow: ' + err.message);
    }
  };

  if (!sessionId) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">
          No session selected. Please select a session to use Interactive Mode.
        </Alert>
      </Box>
    );
  }

  if (!currentSession) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <CircularProgress />
        <Typography variant="h6" sx={{ mt: 2 }}>
          Loading session...
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <Paper sx={{ p: 2, mb: 1 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="h5">Interactive Mode - {currentSession.name}</Typography>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Chip
              label={currentSession.state}
              color={currentSession.state === 'ready' ? 'success' : 'warning'}
              size="small"
            />
            <Button
              variant="contained"
              startIcon={<SaveIcon />}
              onClick={saveWorkflow}
              disabled={isExecuting}
            >
              Save Workflow
            </Button>
            <Button
              variant="contained"
              color="success"
              startIcon={<PlayAllIcon />}
              onClick={executeAllActions}
              disabled={isExecuting || workflow.steps.length === 0}
            >
              {isExecuting ? 'Executing...' : 'Run All'}
            </Button>
          </Box>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mt: 1 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
      </Paper>

      {/* Main Content */}
      <Box sx={{ flex: 1, overflow: 'hidden' }}>
        <Grid container sx={{ height: '100%' }}>
          {/* Left Panel - Workflow Editor and Recording */}
          <Grid
            item
            xs={12}
            md={6}
            sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}
          >
            <Paper sx={{ flex: 1, display: 'flex', flexDirection: 'column', m: 1 }}>
              {/* Tabs */}
              <Tabs
                value={activeTab}
                onChange={handleTabChange}
                sx={{ borderBottom: 1, borderColor: 'divider' }}
              >
                <Tab label="Workflow Editor" />
                <Tab label="Recording" />
              </Tabs>

              {/* Tab Content */}
              <Box sx={{ flex: 1, overflow: 'hidden' }}>
                {activeTab === 0 && (
                  <WorkflowEditor
                    workflow={workflow}
                    onChange={handleWorkflowChange}
                    onExecuteAction={executeAction}
                    executionResults={executionResults}
                    isExecuting={isExecuting}
                  />
                )}
                {activeTab === 1 && (
                  <RecordingPanel
                    sessionId={sessionId}
                    isRecording={isRecording}
                    onStartRecording={handleStartRecording}
                    onStopRecording={handleStopRecording}
                  />
                )}
              </Box>
            </Paper>
          </Grid>

          {/* Right Panel - Remote Desktop */}
          <Grid item xs={12} md={6} sx={{ height: '100%' }}>
            <Paper sx={{ height: '100%', m: 1, display: 'flex', flexDirection: 'column' }}>
              <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
                <Typography variant="h6">Remote Desktop</Typography>
              </Box>
              <Box sx={{ flex: 1, overflow: 'hidden' }}>
                <RemoteDesktopPanel sessionId={sessionId} session={currentSession} />
              </Box>
            </Paper>
          </Grid>
        </Grid>
      </Box>
    </Box>
  );
};

export default InteractiveMode;
