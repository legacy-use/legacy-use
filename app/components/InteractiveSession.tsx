import { PlayArrow, Stop, VideoCall } from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Paper,
  Typography,
} from '@mui/material';
import { useContext, useEffect, useRef, useState } from 'react';
import { SessionContext } from '../App';
import { getRecordingStatus, startRecording, stopRecording } from '../services/apiService';

export default function InteractiveSession() {
  const { currentSession } = useContext(SessionContext);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingStatus, setRecordingStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [recordingResult, setRecordingResult] = useState(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const pollingIntervalRef = useRef(null);

  // Function to fetch recording status
  const fetchRecordingStatus = async (showLoading = true) => {
    if (!currentSession?.id) return;

    try {
      if (showLoading) {
        setStatusLoading(true);
      }

      const status = await getRecordingStatus(currentSession.id);
      setRecordingStatus(status);
      setIsRecording(status.recording);

      // Clear any previous errors when status is fetched successfully
      setError(null);
    } catch (err) {
      console.error('Error fetching recording status:', err);
      if (showLoading) {
        setError(`Failed to get recording status: ${err.message || 'Unknown error'}`);
      }
    } finally {
      if (showLoading) {
        setStatusLoading(false);
      }
    }
  };

  // Set up polling for recording status (same interval as other components)
  useEffect(() => {
    if (!currentSession?.id) return;

    // Initial fetch
    fetchRecordingStatus(true);

    // Set up polling every 2 seconds (same as JobDetails component)
    pollingIntervalRef.current = setInterval(() => {
      fetchRecordingStatus(false); // Don't show loading during polling
    }, 2000);

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, [currentSession?.id]);

  const handleStartRecording = async () => {
    if (!currentSession?.id) {
      setError('No active session available');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setRecordingResult(null);

      const result = await startRecording(currentSession.id, {
        framerate: 30,
        quality: 'fast',
        format: 'mp4',
        capture_vnc_input: true,
      });

      setIsRecording(true);
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
      setIsRecording(false);
      setRecordingResult(result);
      console.log('Recording stopped:', result);
    } catch (err) {
      console.error('Error stopping recording:', err);
      setError(`Failed to stop recording: ${err.message || 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  // Format file size
  const formatFileSize = bytes => {
    if (!bytes) return 'Unknown';
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round((bytes / 1024 ** i) * 100) / 100 + ' ' + sizes[i];
  };

  // Format duration
  const formatDuration = seconds => {
    if (!seconds) return 'Unknown';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
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

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Interactive Session Recording
      </Typography>

      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Record your interactions with the session. The recording will capture screen activity and
        VNC inputs.
      </Typography>

      {/* Recording Status Card */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box
            sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}
          >
            <Typography variant="h6">Recording Status</Typography>
            {statusLoading ? (
              <CircularProgress size={20} />
            ) : (
              <Chip
                icon={isRecording ? <VideoCall /> : <VideoCall />}
                label={isRecording ? 'Recording' : 'Not Recording'}
                color={isRecording ? 'error' : 'default'}
                variant={isRecording ? 'filled' : 'outlined'}
              />
            )}
          </Box>

          {recordingStatus && (
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Session ID: {recordingStatus.session_id || currentSession.id}
              </Typography>
              {recordingStatus.file_path && (
                <Typography variant="body2" color="text.secondary">
                  Recording Path: {recordingStatus.file_path}
                </Typography>
              )}
            </Box>
          )}

          {/* Recording Controls */}
          <Box sx={{ display: 'flex', gap: 2 }}>
            <Button
              variant="contained"
              color={isRecording ? 'error' : 'primary'}
              startIcon={
                loading ? (
                  <CircularProgress size={20} color="inherit" />
                ) : isRecording ? (
                  <Stop />
                ) : (
                  <PlayArrow />
                )
              }
              onClick={isRecording ? handleStopRecording : handleStartRecording}
              disabled={loading || statusLoading}
            >
              {loading
                ? isRecording
                  ? 'Stopping...'
                  : 'Starting...'
                : isRecording
                  ? 'Stop Recording'
                  : 'Start Recording'}
            </Button>
          </Box>
        </CardContent>
      </Card>

      {/* Error Display */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Recording Results */}
      {recordingResult && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Recording Results
            </Typography>

            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Status: {recordingResult.status}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Message: {recordingResult.message}
              </Typography>
              {recordingResult.recording_id && (
                <Typography variant="body2" color="text.secondary">
                  Recording ID: {recordingResult.recording_id}
                </Typography>
              )}
            </Box>

            {recordingResult.file_size_bytes && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  File Size: {formatFileSize(recordingResult.file_size_bytes)}
                </Typography>
              </Box>
            )}

            {recordingResult.duration_seconds && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  Duration: {formatDuration(recordingResult.duration_seconds)}
                </Typography>
              </Box>
            )}

            {recordingResult.base64_video && (
              <Box sx={{ mt: 3 }}>
                <Divider sx={{ mb: 2 }} />
                <Typography variant="h6" gutterBottom>
                  Recorded Video
                </Typography>
                <Paper sx={{ p: 2, textAlign: 'center' }}>
                  <video
                    controls
                    style={{ maxWidth: '100%', maxHeight: '400px' }}
                    src={`data:video/mp4;base64,${recordingResult.base64_video}`}
                  >
                    Your browser does not support the video tag.
                  </video>
                </Paper>
              </Box>
            )}

            {recordingResult.input_logs && recordingResult.input_logs.length > 0 && (
              <Box sx={{ mt: 3 }}>
                <Divider sx={{ mb: 2 }} />
                <Typography variant="h6" gutterBottom>
                  Input Logs ({recordingResult.input_logs.length} entries)
                </Typography>
                <Paper sx={{ p: 2, maxHeight: '300px', overflow: 'auto' }}>
                  {recordingResult.input_logs.map((log, index) => (
                    <Box
                      key={index}
                      sx={{ mb: 1, p: 1, bgcolor: 'background.default', borderRadius: 1 }}
                    >
                      <Typography variant="caption" color="text.secondary">
                        {log.timestamp} - {log.source} - {log.action_type}
                      </Typography>
                      <Typography variant="body2" sx={{ mt: 0.5 }}>
                        {JSON.stringify(log.details, null, 2)}
                      </Typography>
                    </Box>
                  ))}
                </Paper>
              </Box>
            )}

            {recordingResult.input_log_summary && (
              <Box sx={{ mt: 3 }}>
                <Divider sx={{ mb: 2 }} />
                <Typography variant="h6" gutterBottom>
                  Input Summary
                </Typography>
                <Paper sx={{ p: 2 }}>
                  <pre style={{ margin: 0, fontSize: '0.875rem' }}>
                    {JSON.stringify(recordingResult.input_log_summary, null, 2)}
                  </pre>
                </Paper>
              </Box>
            )}
          </CardContent>
        </Card>
      )}
    </Box>
  );
}
