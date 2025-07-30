import { Cancel, CheckCircle, FiberManualRecord, Info, PlayArrow } from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  IconButton,
  keyframes,
  Paper,
  Typography,
} from '@mui/material';
import { useContext, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { SessionContext } from '../App';
import type { RecordingStopResponse } from '../gen/endpoints';
import {
  analyzeVideo,
  getRecordingStatus,
  importApiDefinition,
  startRecording,
  stopRecording,
} from '../services/apiService';
import { formatDuration } from '../utils/formatDuration';
import RecordingButton from './RecordingButton';
import type { RecordingHistory } from './RecordingHistory';

// Keyframes for pulsing record dot
const pulse = keyframes`
  0% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.2);
    opacity: 0.7;
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
`;

// Recording states
type RecordingState = 'initial' | 'recording' | 'recorded' | 'analyzed';

export default function InteractiveSession() {
  const { currentSession } = useContext(SessionContext);

  // Core recording state
  const [recordingState, setRecordingState] = useState<RecordingState>('initial');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recordingResult, setRecordingResult] = useState<null | RecordingStopResponse>(null);
  const [statusLoading, setStatusLoading] = useState(false);

  // Server-provided duration state
  const [recordingDuration, setRecordingDuration] = useState(0);

  // Analysis state
  const [analyzingProgress, setAnalyzingProgress] = useState(false);
  const [generatedPrompt, setGeneratedPrompt] = useState<string>('');
  const [savingApiDefinition, setSavingApiDefinition] = useState(false);
  const [apiDefinitionSaved, setApiDefinitionSaved] = useState(false);

  // Recording history
  const [recordingHistory, setRecordingHistory] = useState<RecordingHistory[]>([]);

  // Polling refs
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Function to fetch recording status from server

  // Load recording history from localStorage on mount and check server status
  useEffect(() => {
    if (!currentSession?.id) return;

    // Load recording history
    const savedHistory = localStorage.getItem(`recording-history-${currentSession.id}`);
    if (savedHistory) {
      try {
        const parsed = JSON.parse(savedHistory).map((item: any) => ({
          ...item,
          timestamp: new Date(item.timestamp),
        }));
        setRecordingHistory(parsed);
        setRecordingState(parsed[0].status);
        setRecordingDuration(parsed[0].duration || 0);
        setRecordingResult(parsed[0].recordingResult);
        setGeneratedPrompt(parsed[0].prompt || '');
        setApiDefinitionSaved(parsed[0].apiDefinitionSaved || false);
        setSavingApiDefinition(parsed[0].savingApiDefinition || false);
        setAnalyzingProgress(parsed[0].analyzingProgress || false);
        setError(parsed[0].error || null);
      } catch (e) {
        console.error('Error loading recording history:', e);
      }
    }
  }, [currentSession?.id]);

  // Save recording history to localStorage
  const saveRecordingHistory = (history: RecordingHistory[]) => {
    if (currentSession?.id) {
      localStorage.setItem(`recording-history-${currentSession.id}`, JSON.stringify(history));
    }
  };

  const handleStartRecording = async () => {
    if (!currentSession?.id) {
      setError('No active session available');
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const result = await startRecording(currentSession.id, {
        framerate: 30,
        quality: 'fast',
        format: 'mp4',
        capture_vnc_input: true,
      });

      setRecordingState('recording');
      setRecordingDuration(0);
      console.log('Recording started:', result);
    } catch (err) {
      console.error('Error starting recording:', err);
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(`Failed to start recording: ${errorMessage}`);
    } finally {
      setLoading(false);
    }
  };

  const handleStopRecording = async () => {
    if (!currentSession?.id) {
      setError('No active session available');
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const result = await stopRecording(currentSession.id);
      setRecordingResult(result);
      setRecordingState('recorded');

      // Create recording history entry
      const newRecording: RecordingHistory = {
        id: result.recording_id || Date.now().toString(),
        timestamp: new Date(),
        duration: recordingDuration,
        status: 'recorded',
        recordingResult: result,
      };

      const updatedHistory = [newRecording, ...recordingHistory];
      setRecordingHistory(updatedHistory);
      saveRecordingHistory(updatedHistory);

      // Automatically start analysis
      setTimeout(() => {
        handleAnalyzeRecording(newRecording);
      }, 100);

      console.log('Recording stopped:', result);
    } catch (err) {
      console.error('Error stopping recording:', err);
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(`Failed to stop recording: ${errorMessage}`);
      setRecordingState('initial');
    } finally {
      setLoading(false);
    }
  };

  const handleAnalyzeRecording = async (recording: RecordingHistory) => {
    setAnalyzingProgress(true);
    setError(null);

    try {
      // Check if we have base64 video data
      if (!recording.recordingResult?.base64_video) {
        throw new Error('No video data available for analysis');
      }

      // Convert base64 video to File object
      const base64Data = recording.recordingResult.base64_video;
      const binaryData = atob(base64Data);
      const arrayBuffer = new ArrayBuffer(binaryData.length);
      const uint8Array = new Uint8Array(arrayBuffer);

      for (let i = 0; i < binaryData.length; i++) {
        uint8Array[i] = binaryData.charCodeAt(i);
      }

      const videoFile = new File([arrayBuffer], `recording_${recording.id}.mp4`, {
        type: 'video/mp4',
      });

      console.log('Analyzing video with AI...', {
        recordingId: recording.id,
        fileSize: videoFile.size,
        duration: recording.duration,
      });

      // Call the AI analyze endpoint
      const analysisResult = await analyzeVideo(videoFile);

      console.log('AI analysis completed:', analysisResult);

      // Extract the API definition from the analysis result
      const apiDefinition = analysisResult.api_definition;

      // Create a formatted prompt from the API definition
      const formattedPrompt = `# Generated API Definition: ${apiDefinition.name}

**Description:** ${apiDefinition.description}

## Parameters
${
  apiDefinition.parameters.length > 0
    ? apiDefinition.parameters
        .map((param: any) => `- **${param.name}** (${param.type}): ${param.description}`)
        .join('\n')
    : 'No parameters required'
}

## Automation Instructions
${apiDefinition.prompt || 'No specific instructions provided'}

## Response Format
\`\`\`json
${JSON.stringify(apiDefinition.response_example, null, 2)}
\`\`\`

---
**Analysis Summary:** ${analysisResult.analysis_summary}
**Confidence Score:** ${Math.round(analysisResult.confidence_score * 100)}%

*This API definition was automatically generated from your screen recording using AI analysis.*`;

      setGeneratedPrompt(formattedPrompt);
      setRecordingState('analyzed');

      // Update recording history with the analysis results
      const updatedRecording = {
        ...recording,
        status: 'analyzed' as RecordingState,
        prompt: formattedPrompt,
        apiDefinition: apiDefinition,
        analysisResult: analysisResult,
      };

      const updatedHistory = recordingHistory.map(r =>
        r.id === recording.id ? updatedRecording : r,
      );
      setRecordingHistory(updatedHistory);
      saveRecordingHistory(updatedHistory);

      setAnalyzingProgress(false);
    } catch (err) {
      console.error('Error analyzing recording:', err);
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(`Failed to analyze recording: ${errorMessage}`);
      setAnalyzingProgress(false);
      setRecordingState('recorded'); // Go back to recorded state on error
    }
  };

  const handleCancelAnalysis = () => {
    setAnalyzingProgress(false);
    setRecordingState('recorded');
  };

  const handleStartNewRecording = () => {
    setRecordingState('initial');
    setRecordingResult(null);
    setGeneratedPrompt('');
    setError(null);
    setApiDefinitionSaved(false);
  };

  const handleSaveApiDefinition = async (recording: RecordingHistory) => {
    if (!recording.apiDefinition) {
      setError('No API definition available to save');
      return;
    }

    setSavingApiDefinition(true);
    setError(null);

    try {
      // Prepare the API definition for import
      const apiDefinitionToSave = {
        name: recording.apiDefinition.name,
        description: recording.apiDefinition.description,
        parameters: recording.apiDefinition.parameters || [],
        prompt: recording.apiDefinition.prompt || '',
        prompt_cleanup: recording.apiDefinition.prompt_cleanup || '',
        response_example: recording.apiDefinition.response_example || {},
      };

      console.log('Saving API definition:', apiDefinitionToSave);

      // Import the API definition
      const result = await importApiDefinition(apiDefinitionToSave);

      console.log('API definition saved successfully:', result);
      setApiDefinitionSaved(true);

      // Update the recording history to mark it as saved
      const updatedHistory = recordingHistory.map(r =>
        r.id === recording.id
          ? { ...r, apiDefinitionSaved: true, apiDefinitionName: result.name }
          : r,
      );
      setRecordingHistory(updatedHistory);
      saveRecordingHistory(updatedHistory);
    } catch (err) {
      console.error('Error saving API definition:', err);
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(`Failed to save API definition: ${errorMessage}`);
    } finally {
      setSavingApiDefinition(false);
    }
  };

  const handleShowRecordingDetails = (
    event: React.MouseEvent<HTMLElement>,
    recording: RecordingHistory,
  ) => {
    setPopoverAnchor(event.currentTarget);
    setCurrentRecordingForPopover(recording);
  };

  const handleClosePopover = () => {
    setPopoverAnchor(null);
    setCurrentRecordingForPopover(null);
  };

  // Format file size
  const formatFileSize = (bytes: number) => {
    if (!bytes) return 'Unknown';
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${Math.round((bytes / 1024 ** i) * 100) / 100} ${sizes[i]}`;
  };

  if (!currentSession) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">
          No active session selected. Please select a session to use recording features.
        </Alert>
      </Box>
    );
  }

  if (currentSession.is_archived) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="info">
          This session is archived. Recording is not available for archived sessions.
        </Alert>
      </Box>
    );
  }

  if (currentSession.state !== 'ready') {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">
          Session is not ready. Current state: {currentSession.state}. Recording is only available
          when the session is in 'ready' state.
        </Alert>
      </Box>
    );
  }

  const renderRecordingButton = () => {
    // Show loading state while checking initial status
    if (statusLoading && recordingState === 'initial') {
      return (
        <Button
          variant="contained"
          color="primary"
          size="large"
          startIcon={<CircularProgress size={20} color="inherit" />}
          disabled
          sx={{ minWidth: 160 }}
        >
          Checking Status...
        </Button>
      );
    }

    switch (recordingState) {
      case 'initial':
        return (
          <Button
            variant="contained"
            color="error"
            size="large"
            startIcon={
              loading ? <CircularProgress size={20} color="inherit" /> : <FiberManualRecord />
            }
            onClick={handleStartRecording}
            disabled={loading}
            sx={{ minWidth: 160 }}
          >
            {loading ? 'Starting...' : 'Start Recording'}
          </Button>
        );

      case 'recording':
        return (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Button
              variant="contained"
              color="error"
              size="large"
              startIcon={
                loading ? (
                  <CircularProgress size={20} color="inherit" />
                ) : (
                  <FiberManualRecord
                    sx={{
                      animation: `${pulse} 1.5s ease-in-out infinite`,
                      color: '#ff0000',
                    }}
                  />
                )
              }
              onClick={handleStopRecording}
              disabled={loading}
              sx={{ minWidth: 160 }}
            >
              {loading ? 'Stopping...' : 'Stop Recording'}
            </Button>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <FiberManualRecord
                sx={{
                  fontSize: 12,
                  color: '#ff0000',
                  animation: `${pulse} 1.5s ease-in-out infinite`,
                }}
              />
              <Typography variant="body2" color="text.secondary">
                {formatDuration(recordingDuration)}
              </Typography>
            </Box>
          </Box>
        );

      case 'recorded':
        if (analyzingProgress) {
          return (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Button
                variant="contained"
                color="primary"
                size="large"
                startIcon={<CircularProgress size={20} color="inherit" />}
                disabled
                sx={{ minWidth: 160 }}
              >
                Analyzing...
              </Button>
              <Button
                variant="outlined"
                color="secondary"
                onClick={handleCancelAnalysis}
                startIcon={<Cancel />}
              >
                Cancel
              </Button>
              {recordingResult && (
                <IconButton
                  color="primary"
                  onClick={e =>
                    handleShowRecordingDetails(e, {
                      id: recordingResult.recording_id || 'current',
                      timestamp: new Date(),
                      duration: recordingDuration,
                      status: 'recorded',
                      recordingResult,
                    })
                  }
                >
                  <Info />
                </IconButton>
              )}
            </Box>
          );
        }
        return (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="body1">
              Recording completed. Analysis will start automatically...
              <Button
                variant="contained"
                color="primary"
                onClick={() => {
                  const newRecording: RecordingHistory = {
                    id: recordingResult.recording_id || Date.now().toString(),
                    timestamp: recordingResult.timestamp,
                    duration: recordingDuration,
                    status: 'recorded',
                    recordingResult: recordingResult,
                  };
                  handleAnalyzeRecording(newRecording);
                }}
              >
                Analyze again
              </Button>
              <Button
                variant="contained"
                color="error"
                onClick={() => {
                  handleStartNewRecording();
                }}
              >
                Discard
              </Button>
            </Typography>
            {recordingResult && (
              <IconButton
                color="primary"
                onClick={e =>
                  handleShowRecordingDetails(e, {
                    id: recordingResult.recording_id || 'current',
                    timestamp: new Date(),
                    duration: recordingDuration,
                    status: 'recorded',
                    recordingResult,
                  })
                }
              >
                <Info />
              </IconButton>
            )}
          </Box>
        );

      case 'analyzed':
        return (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Button
              variant="contained"
              color="success"
              size="large"
              startIcon={<PlayArrow />}
              onClick={handleStartNewRecording}
              sx={{ minWidth: 160 }}
            >
              New Recording
            </Button>
            {recordingResult && (
              <IconButton
                color="primary"
                onClick={e =>
                  handleShowRecordingDetails(e, {
                    id: recordingResult.recording_id || 'current',
                    timestamp: new Date(),
                    duration: recordingDuration,
                    status: 'recorded',
                    recordingResult,
                  })
                }
              >
                <Info />
              </IconButton>
            )}
          </Box>
        );

      default:
        return null;
    }
  };

  const renderContent = () => {
    if (recordingState === 'analyzed' && generatedPrompt) {
      // Find the current recording to get the API definition
      const currentRecording = recordingHistory.find(r => r.status === 'analyzed');

      return (
        <Box sx={{ mt: 3 }}>
          <Box
            sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}
          >
            <Typography variant="h6">Generated Automation API</Typography>
            {currentRecording?.apiDefinition && (
              <Box sx={{ display: 'flex', gap: 1 }}>
                {currentRecording.apiDefinitionSaved ? (
                  <Link to={`/apis/${currentRecording.apiDefinitionName}/edit`}>
                    <Button variant="outlined" color="success" disabled startIcon={<CheckCircle />}>
                      API Saved
                    </Button>
                  </Link>
                ) : (
                  <Button
                    variant="contained"
                    color="primary"
                    onClick={() => handleSaveApiDefinition(currentRecording)}
                    disabled={savingApiDefinition}
                    startIcon={savingApiDefinition ? <CircularProgress size={20} /> : undefined}
                  >
                    {savingApiDefinition ? 'Saving...' : 'Save as API'}
                  </Button>
                )}
              </Box>
            )}
          </Box>

          <Paper sx={{ p: 3, bgcolor: 'background.default' }}>
            <Typography
              component="div"
              variant="body2"
              sx={{
                whiteSpace: 'pre-wrap',
                '& h1, & h2, & h3': { mt: 2, mb: 1 },
                '& p': { mb: 1 },
                '& pre': {
                  bgcolor: 'rgba(0,0,0,0.3)',
                  p: 2,
                  borderRadius: 1,
                  overflow: 'auto',
                },
                '& code': {
                  bgcolor: 'rgba(0,0,0,0.2)',
                  px: 0.5,
                  borderRadius: 0.5,
                  fontFamily: 'monospace',
                },
              }}
            >
              {generatedPrompt}
            </Typography>
          </Paper>
        </Box>
      );
    }
    return null;
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Interactive Session
      </Typography>

      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Record your interactions to generate automation workflows and teach legacy-use your use
        cases.
      </Typography>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 2 }}>
            <RecordingButton sessionId={currentSession.id} />
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
