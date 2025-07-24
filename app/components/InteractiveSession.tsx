import { Analytics, Cancel, FiberManualRecord, Info, PlayArrow, Stop } from '@mui/icons-material';
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
  Popover,
  Typography,
} from '@mui/material';
import { useContext, useEffect, useRef, useState } from 'react';
import { SessionContext } from '../App';
import { getRecordingStatus, startRecording, stopRecording } from '../services/apiService';
import { formatDuration } from '../utils/formatDuration';

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

interface RecordingHistory {
  id: string;
  timestamp: Date;
  duration?: number;
  status: RecordingState;
  prompt?: string;
  recordingResult?: any;
}

export default function InteractiveSession() {
  const { currentSession } = useContext(SessionContext);

  // Core recording state
  const [recordingState, setRecordingState] = useState<RecordingState>('initial');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recordingResult, setRecordingResult] = useState(null);

  // Timer state
  const [recordingStartTime, setRecordingStartTime] = useState<Date | null>(null);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const timerIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Analysis state
  const [analyzingProgress, setAnalyzingProgress] = useState(false);
  const [generatedPrompt, setGeneratedPrompt] = useState<string>('');

  // Recording history
  const [recordingHistory, setRecordingHistory] = useState<RecordingHistory[]>([]);

  // Popover state
  const [popoverAnchor, setPopoverAnchor] = useState<HTMLElement | null>(null);
  const [currentRecordingForPopover, setCurrentRecordingForPopover] =
    useState<RecordingHistory | null>(null);

  // Polling refs
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Load recording history from localStorage on mount
  useEffect(() => {
    const savedHistory = localStorage.getItem(`recording-history-${currentSession?.id}`);
    if (savedHistory) {
      try {
        const parsed = JSON.parse(savedHistory).map((item: any) => ({
          ...item,
          timestamp: new Date(item.timestamp),
        }));
        setRecordingHistory(parsed);
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

  // Timer effect for recording duration
  useEffect(() => {
    if (recordingState === 'recording' && recordingStartTime) {
      timerIntervalRef.current = setInterval(() => {
        const now = new Date();
        const duration = Math.floor((now.getTime() - recordingStartTime.getTime()) / 1000);
        setRecordingDuration(duration);
      }, 1000);
    } else {
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
        timerIntervalRef.current = null;
      }
    }

    return () => {
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
      }
    };
  }, [recordingState, recordingStartTime]);

  // Polling for recording status (only when recording)
  useEffect(() => {
    if (recordingState === 'recording' && currentSession?.id) {
      pollingIntervalRef.current = setInterval(async () => {
        try {
          const status = await getRecordingStatus(currentSession.id);
          if (!status.recording) {
            // Recording stopped externally
            setRecordingState('initial');
            setRecordingStartTime(null);
            setRecordingDuration(0);
          }
        } catch (err) {
          console.error('Error polling recording status:', err);
        }
      }, 2000);
    } else {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    }

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, [recordingState, currentSession?.id]);

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
      setRecordingStartTime(new Date());
      setRecordingDuration(0);
      console.log('Recording started:', result);
    } catch (err) {
      console.error('Error starting recording:', err);
      setError(`Failed to start recording: ${err.message || 'Unknown error'}`);
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
      setError(`Failed to stop recording: ${err.message || 'Unknown error'}`);
      setRecordingState('initial');
    } finally {
      setLoading(false);
      setRecordingStartTime(null);
    }
  };

  const handleAnalyzeRecording = async (recording: RecordingHistory) => {
    setAnalyzingProgress(true);

    // Mock analysis with 2-second delay
    setTimeout(() => {
      const mockPrompt = `# Generated Prompt from Recording

Based on the recorded session activity, here's a suggested automation prompt:

## Task Description
Automate the workflow captured in the ${formatDuration(recording.duration || 0)} recording session.

## Steps Identified
1. **Initial Setup**: Prepare the workspace environment
2. **User Interactions**: Execute the sequence of clicks and inputs
3. **Data Processing**: Handle any form submissions or data entry
4. **Completion**: Verify the final state and results

## Suggested Automation Code
\`\`\`python
# TODO: Implement actual video analysis
# This is a mock prompt generated for demonstration
def automate_recorded_workflow():
    """
    Automate the workflow from the recorded session
    """
    pass
\`\`\`

*Note: This is a mock analysis. Actual implementation would analyze the video frames and input logs to generate specific automation instructions.*`;

      setGeneratedPrompt(mockPrompt);
      setRecordingState('analyzed');

      // Update recording history
      const updatedRecording = {
        ...recording,
        status: 'analyzed' as RecordingState,
        prompt: mockPrompt,
      };

      const updatedHistory = recordingHistory.map(r =>
        r.id === recording.id ? updatedRecording : r,
      );
      setRecordingHistory(updatedHistory);
      saveRecordingHistory(updatedHistory);

      setAnalyzingProgress(false);
    }, 2000);
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
        );

      default:
        return null;
    }
  };

  const renderContent = () => {
    if (recordingState === 'analyzed' && generatedPrompt) {
      return (
        <Box sx={{ mt: 3 }}>
          <Typography variant="h6" gutterBottom>
            Generated Automation Prompt
          </Typography>
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
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Interactive Session Recording
      </Typography>

      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Record your interactions with the session to generate automation prompts.
      </Typography>

      {/* Simplified Recording Status Card */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
            {renderRecordingButton()}
          </Box>
        </CardContent>
      </Card>

      {/* Error Display */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Content based on state */}
      {renderContent()}

      {/* Recording Details Popover */}
      <Popover
        open={Boolean(popoverAnchor)}
        anchorEl={popoverAnchor}
        onClose={handleClosePopover}
        anchorOrigin={{
          vertical: 'bottom',
          horizontal: 'center',
        }}
        transformOrigin={{
          vertical: 'top',
          horizontal: 'center',
        }}
      >
        <Box sx={{ p: 3, maxWidth: 400 }}>
          {currentRecordingForPopover?.recordingResult && (
            <Box>
              <Typography variant="h6" gutterBottom>
                Recording Details
              </Typography>

              <Typography variant="body2" color="text.secondary" gutterBottom>
                Status: {currentRecordingForPopover.recordingResult.status}
              </Typography>

              <Typography variant="body2" color="text.secondary" gutterBottom>
                Duration: {formatDuration(currentRecordingForPopover.duration || 0)}
              </Typography>

              {currentRecordingForPopover.recordingResult.file_size_bytes && (
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  File Size:{' '}
                  {formatFileSize(currentRecordingForPopover.recordingResult.file_size_bytes)}
                </Typography>
              )}

              {currentRecordingForPopover.recordingResult.base64_video && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="body2" gutterBottom>
                    Recorded Video:
                  </Typography>
                  <video
                    controls
                    style={{ maxWidth: '100%', maxHeight: '200px' }}
                    src={`data:video/mp4;base64,${currentRecordingForPopover.recordingResult.base64_video}`}
                  >
                    Your browser does not support the video tag.
                  </video>
                </Box>
              )}
            </Box>
          )}
        </Box>
      </Popover>
    </Box>
  );
}
