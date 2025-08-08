import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  CircularProgress,
  Alert,
  IconButton,
  Tooltip,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import { getSessionContainerLogs } from '../services/apiService';

interface ContainerLogsModalProps {
  open: boolean;
  onClose: () => void;
  sessionId: string;
  sessionName: string;
}

const ContainerLogsModal: React.FC<ContainerLogsModalProps> = ({
  open,
  onClose,
  sessionId,
  sessionName,
}) => {
  const [logs, setLogs] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lines, setLines] = useState(1000);

  const fetchLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await getSessionContainerLogs(sessionId, lines);
      setLogs(response.logs || 'No logs available');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch logs');
      setLogs('');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      fetchLogs();
    }
  }, [open, sessionId, lines]);

  const handleRefresh = () => {
    fetchLogs();
  };

  const handleCopyLogs = () => {
    navigator.clipboard.writeText(logs);
  };

  const handleLinesChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    setLines(Number(event.target.value));
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Typography variant="h6">
            Container Logs - {sessionName}
          </Typography>
          <Box display="flex" alignItems="center" gap={1}>
            <select
              value={lines}
              onChange={handleLinesChange}
              style={{ padding: '4px 8px', borderRadius: '4px', border: '1px solid #ccc' }}
            >
              <option value={100}>Last 100 lines</option>
              <option value={500}>Last 500 lines</option>
              <option value={1000}>Last 1000 lines</option>
              <option value={2000}>Last 2000 lines</option>
            </select>
            <Tooltip title="Copy logs to clipboard">
              <IconButton onClick={handleCopyLogs} size="small">
                <ContentCopyIcon />
              </IconButton>
            </Tooltip>
            <Tooltip title="Refresh logs">
              <IconButton onClick={handleRefresh} size="small" disabled={loading}>
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>
      </DialogTitle>
      <DialogContent>
        {loading && (
          <Box display="flex" justifyContent="center" p={2}>
            <CircularProgress />
          </Box>
        )}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        {!loading && !error && (
          <Box
            sx={{
              backgroundColor: '#1e1e1e',
              color: '#d4d4d4',
              fontFamily: 'monospace',
              fontSize: '12px',
              padding: 2,
              borderRadius: 1,
              maxHeight: '60vh',
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {logs || 'No logs available'}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
};

export default ContainerLogsModal; 