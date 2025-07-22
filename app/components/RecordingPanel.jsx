import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Paper,
  Typography,
  Button,
  IconButton,
  LinearProgress,
  Alert,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Chip,
  CircularProgress
} from '@mui/material';
import {
  RadioButtonChecked as RecordIcon,
  Stop as StopIcon,
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  Videocam as VideocamIcon,
  VideoLibrary as VideoLibraryIcon,
  Download as DownloadIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon
} from '@mui/icons-material';

const RecordingPanel = ({ 
  sessionId, 
  isRecording, 
  onStartRecording, 
  onStopRecording 
}) => {
  const [recordings, setRecordings] = useState([]);
  const [processingStatus, setProcessingStatus] = useState(null);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef(null);

  // Timer for recording duration
  useEffect(() => {
    if (isRecording) {
      intervalRef.current = setInterval(() => {
        setRecordingDuration(prev => prev + 1);
      }, 1000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (!isRecording) {
        setRecordingDuration(0);
      }
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [isRecording]);

  // Fetch existing recordings
  useEffect(() => {
    fetchRecordings();
  }, [sessionId]);

  const fetchRecordings = async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/interactive/recordings/${sessionId}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('apiKey')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setRecordings(data.recordings || []);
      } else {
        setError('Failed to fetch recordings');
      }
    } catch (err) {
      setError('Error fetching recordings: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleStartRecording = async () => {
    try {
      setError(null);
      await onStartRecording();
      setRecordingDuration(0);
    } catch (err) {
      setError('Failed to start recording: ' + err.message);
    }
  };

  const handleStopRecording = async () => {
    try {
      setError(null);
      setProcessingStatus('Stopping recording...');
      await onStopRecording();
      setProcessingStatus('Processing with Gemini...');
      
      // Refresh recordings list after a short delay
      setTimeout(() => {
        fetchRecordings();
        setProcessingStatus(null);
      }, 2000);
    } catch (err) {
      setError('Failed to stop recording: ' + err.message);
      setProcessingStatus(null);
    }
  };

  const handlePlayRecording = async (recordingId) => {
    try {
      const response = await fetch(`/api/interactive/recordings/${sessionId}/${recordingId}/play`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('apiKey')}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to play recording');
      }

      // Open recording in new tab or show player
      const data = await response.json();
      if (data.playbackUrl) {
        window.open(data.playbackUrl, '_blank');
      }
    } catch (err) {
      setError('Failed to play recording: ' + err.message);
    }
  };

  const handleDownloadRecording = async (recordingId, filename) => {
    try {
      const response = await fetch(`/api/interactive/recordings/${sessionId}/${recordingId}/download`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('apiKey')}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to download recording');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || `recording-${recordingId}.webm`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError('Failed to download recording: ' + err.message);
    }
  };

  const handleDeleteRecording = async (recordingId) => {
    try {
      const response = await fetch(`/api/interactive/recordings/${sessionId}/${recordingId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('apiKey')}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to delete recording');
      }

      fetchRecordings();
    } catch (err) {
      setError('Failed to delete recording: ' + err.message);
    }
  };

  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return 'Unknown size';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
  };

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', p: 2 }}>
      {/* Recording Controls */}
      <Paper sx={{ p: 3, mb: 2 }}>
        <Typography variant="h6" gutterBottom>
          Screen Recording
        </Typography>
        
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {processingStatus && (
          <Alert severity="info" sx={{ mb: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <CircularProgress size={16} />
              {processingStatus}
            </Box>
          </Alert>
        )}

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
          {!isRecording ? (
            <Button
              variant="contained"
              color="error"
              startIcon={<RecordIcon />}
              onClick={handleStartRecording}
              size="large"
              disabled={loading || processingStatus}
            >
              Start Recording
            </Button>
          ) : (
            <Button
              variant="contained"
              color="primary"
              startIcon={<StopIcon />}
              onClick={handleStopRecording}
              size="large"
            >
              Stop Recording
            </Button>
          )}

          {isRecording && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Chip
                icon={<VideocamIcon />}
                label={`Recording: ${formatDuration(recordingDuration)}`}
                color="error"
                variant="outlined"
              />
            </Box>
          )}
        </Box>

        <Typography variant="body2" color="text.secondary">
          {isRecording 
            ? 'Recording the remote desktop session. Actions will be analyzed by Google Gemini when you stop recording.'
            : 'Click "Start Recording" to begin capturing your interactions with the remote desktop. The recording will be processed by Google Gemini to extract workflow steps.'
          }
        </Typography>
      </Paper>

      {/* Recording History */}
      <Paper sx={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="h6">
            Recording History
          </Typography>
          <IconButton onClick={fetchRecordings} disabled={loading}>
            <RefreshIcon />
          </IconButton>
        </Box>

        <Box sx={{ flex: 1, overflow: 'auto' }}>
          {loading ? (
            <Box sx={{ p: 3, textAlign: 'center' }}>
              <CircularProgress />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                Loading recordings...
              </Typography>
            </Box>
          ) : recordings.length === 0 ? (
            <Box sx={{ p: 3, textAlign: 'center' }}>
              <VideoLibraryIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
              <Typography color="text.secondary">
                No recordings yet. Start recording to create your first workflow capture.
              </Typography>
            </Box>
          ) : (
            <List>
              {recordings.map((recording, index) => (
                <React.Fragment key={recording.id}>
                  <ListItem sx={{ py: 2 }}>
                    <ListItemIcon>
                      <VideoLibraryIcon />
                    </ListItemIcon>
                    <ListItemText
                      primary={
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Typography variant="subtitle2">
                            Recording #{recordings.length - index}
                          </Typography>
                          {recording.processed && (
                            <Chip size="small" label="Processed" color="success" />
                          )}
                          {recording.processing && (
                            <Chip size="small" label="Processing..." color="warning" />
                          )}
                        </Box>
                      }
                      secondary={
                        <Box>
                          <Typography variant="body2" color="text.secondary">
                            Duration: {formatDuration(recording.duration || 0)} • 
                            Size: {formatFileSize(recording.fileSize)} • 
                            Created: {new Date(recording.createdAt).toLocaleString()}
                          </Typography>
                          {recording.description && (
                            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                              {recording.description}
                            </Typography>
                          )}
                          {recording.extractedActions && recording.extractedActions.length > 0 && (
                            <Typography variant="body2" color="primary" sx={{ mt: 0.5 }}>
                              {recording.extractedActions.length} actions extracted
                            </Typography>
                          )}
                        </Box>
                      }
                    />
                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <IconButton
                        size="small"
                        onClick={() => handlePlayRecording(recording.id)}
                        title="Play recording"
                      >
                        <PlayIcon />
                      </IconButton>
                      <IconButton
                        size="small"
                        onClick={() => handleDownloadRecording(recording.id, recording.filename)}
                        title="Download recording"
                      >
                        <DownloadIcon />
                      </IconButton>
                      <IconButton
                        size="small"
                        onClick={() => handleDeleteRecording(recording.id)}
                        color="error"
                        title="Delete recording"
                      >
                        <DeleteIcon />
                      </IconButton>
                    </Box>
                  </ListItem>
                  {index < recordings.length - 1 && <Divider />}
                </React.Fragment>
              ))}
            </List>
          )}
        </Box>
      </Paper>

      {/* Recording Tips */}
      <Paper sx={{ p: 2, mt: 2, backgroundColor: 'background.default' }}>
        <Typography variant="subtitle2" gutterBottom>
          💡 Recording Tips
        </Typography>
        <Typography variant="body2" color="text.secondary">
          • Perform actions slowly and deliberately
          <br />
          • Wait for UI elements to load before interacting
          <br />
          • Keep recordings focused on specific tasks
          <br />
          • Use clear, deliberate mouse movements and clicks
        </Typography>
      </Paper>
    </Box>
  );
};

export default RecordingPanel;