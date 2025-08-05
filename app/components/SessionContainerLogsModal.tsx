import CloseIcon from '@mui/icons-material/Close';
import RefreshIcon from '@mui/icons-material/Refresh';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Paper,
  Slider,
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getSessionContainerLogs } from '../services/apiService';

interface ContainerLog {
  timestamp: string;
  content: string;
  stream: 'stdout' | 'stderr';
}

interface SessionContainerLogsModalProps {
  open: boolean;
  onClose: () => void;
  sessionId: string;
  sessionName?: string;
}

const SessionContainerLogsModal = ({
  open,
  onClose,
  sessionId,
  sessionName,
}: SessionContainerLogsModalProps) => {
  const [logs, setLogs] = useState<ContainerLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lines, setLines] = useState(100);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  const autoRefreshInterval = useRef<NodeJS.Timeout | null>(null);

  const fetchLogs = useCallback(async () => {
    if (!sessionId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await getSessionContainerLogs(sessionId, lines);

      if (response.error) {
        setError(response.error);
        setLogs([]);
      } else {
        setLogs(response.logs || []);
      }
    } catch (err) {
      console.error('Error fetching container logs:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch container logs');
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }, [sessionId, lines]);

  // Auto-scroll to bottom when new logs are added
  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // Initial fetch when modal opens
  useEffect(() => {
    if (open) {
      fetchLogs();
    }
  }, [open, fetchLogs]);

  // Auto-refresh functionality
  useEffect(() => {
    if (autoRefresh && open) {
      autoRefreshInterval.current = setInterval(fetchLogs, 5000); // Refresh every 5 seconds
    } else if (autoRefreshInterval.current) {
      clearInterval(autoRefreshInterval.current);
      autoRefreshInterval.current = null;
    }

    return () => {
      if (autoRefreshInterval.current) {
        clearInterval(autoRefreshInterval.current);
      }
    };
  }, [autoRefresh, open, fetchLogs]);

  const handleLinesChange = (_event: Event, newValue: number | number[]) => {
    setLines(newValue as number);
  };

  const formatTimestamp = (timestamp: string) => {
    if (!timestamp) return '';
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString();
    } catch {
      return timestamp;
    }
  };

  const getLogColor = (stream: string) => {
    switch (stream) {
      case 'stderr':
        return '#ff6b6b';
      case 'stdout':
      default:
        return '#ffffff';
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h6">Container Logs {sessionName && `- ${sessionName}`}</Typography>
        <IconButton onClick={onClose} size="small">
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent sx={{ height: '70vh', display: 'flex', flexDirection: 'column' }}>
        {/* Controls */}
        <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          <Button
            variant="outlined"
            startIcon={loading ? <CircularProgress size={16} /> : <RefreshIcon />}
            onClick={fetchLogs}
            disabled={loading}
          >
            Refresh
          </Button>

          <Button
            variant={autoRefresh ? 'contained' : 'outlined'}
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            Auto Refresh
          </Button>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 200 }}>
            <Typography variant="body2">Lines:</Typography>
            <Slider
              value={lines}
              onChange={handleLinesChange}
              min={50}
              max={1000}
              step={50}
              valueLabelDisplay="auto"
              sx={{ flexGrow: 1 }}
            />
            <Typography variant="body2" sx={{ minWidth: 40 }}>
              {lines}
            </Typography>
          </Box>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {/* Logs Display */}
        <Paper
          sx={{
            flex: 1,
            p: 2,
            backgroundColor: '#1e1e1e',
            color: '#ffffff',
            fontFamily: 'monospace',
            fontSize: '0.875rem',
            overflow: 'auto',
          }}
        >
          {loading && logs.length === 0 ? (
            <Box
              sx={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                height: '100%',
              }}
            >
              <CircularProgress />
            </Box>
          ) : logs.length === 0 ? (
            <Typography color="textSecondary">No logs available</Typography>
          ) : (
            <>
              {logs.map((log, index) => (
                <Box
                  key={`${log.timestamp}-${index}`}
                  sx={{
                    py: 0.25,
                    borderBottom: '1px solid #333',
                    display: 'flex',
                    alignItems: 'flex-start',
                  }}
                >
                  <Typography
                    component="span"
                    sx={{
                      color: '#888',
                      fontSize: '0.75rem',
                      minWidth: 80,
                      mr: 1,
                      flexShrink: 0,
                    }}
                  >
                    {formatTimestamp(log.timestamp)}
                  </Typography>
                  <Typography
                    component="pre"
                    sx={{
                      margin: 0,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      color: getLogColor(log.stream),
                      flexGrow: 1,
                    }}
                  >
                    {log.content}
                  </Typography>
                </Box>
              ))}
              <div ref={logEndRef} />
            </>
          )}
        </Paper>

        {logs.length > 0 && (
          <Typography variant="caption" sx={{ mt: 1, color: 'textSecondary' }}>
            Showing {logs.length} log entries
          </Typography>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default SessionContainerLogsModal;
