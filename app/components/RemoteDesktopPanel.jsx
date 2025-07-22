import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Paper,
  Typography,
  IconButton,
  Button,
  Tooltip,
  Alert,
  CircularProgress,
  Chip,
  Menu,
  MenuItem,
  Divider
} from '@mui/material';
import {
  Fullscreen as FullscreenIcon,
  FullscreenExit as FullscreenExitIcon,
  Refresh as RefreshIcon,
  Settings as SettingsIcon,
  Screenshot as ScreenshotIcon,
  ZoomIn as ZoomInIcon,
  ZoomOut as ZoomOutIcon,
  FitScreen as FitScreenIcon,
  Mouse as MouseIcon,
  Keyboard as KeyboardIcon
} from '@mui/icons-material';
import VncViewer from './VncViewer';

const RemoteDesktopPanel = ({ sessionId, session }) => {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(100);
  const [settingsAnchor, setSettingsAnchor] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const [error, setError] = useState(null);
  const containerRef = useRef(null);
  const vncRef = useRef(null);

  useEffect(() => {
    if (session) {
      setConnectionStatus(session.state === 'ready' ? 'connected' : 'connecting');
    }
  }, [session]);

  const handleFullscreen = () => {
    if (!isFullscreen) {
      if (containerRef.current.requestFullscreen) {
        containerRef.current.requestFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
    }
  };

  const handleScreenshot = async () => {
    try {
      const response = await fetch(`/api/interactive/screenshot/${sessionId}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('apiKey')}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to take screenshot');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `screenshot-${sessionId}-${Date.now()}.png`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError('Failed to take screenshot: ' + err.message);
    }
  };

  const handleZoomIn = () => {
    setZoomLevel(prev => Math.min(prev + 25, 200));
  };

  const handleZoomOut = () => {
    setZoomLevel(prev => Math.max(prev - 25, 50));
  };

  const handleFitScreen = () => {
    setZoomLevel(100);
  };

  const handleRefresh = () => {
    if (vncRef.current && vncRef.current.refresh) {
      vncRef.current.refresh();
    }
  };

  const handleSendKeys = async (keys) => {
    try {
      const response = await fetch(`/api/interactive/send-keys/${sessionId}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('apiKey')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ keys })
      });

      if (!response.ok) {
        throw new Error('Failed to send keys');
      }
    } catch (err) {
      setError('Failed to send keys: ' + err.message);
    }
  };

  // Handle fullscreen events
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, []);

  const getStatusColor = () => {
    switch (connectionStatus) {
      case 'connected':
        return 'success';
      case 'connecting':
        return 'warning';
      case 'disconnected':
        return 'error';
      default:
        return 'default';
    }
  };

  const getStatusLabel = () => {
    switch (connectionStatus) {
      case 'connected':
        return 'Connected';
      case 'connecting':
        return 'Connecting...';
      case 'disconnected':
        return 'Disconnected';
      default:
        return 'Unknown';
    }
  };

  if (!session) {
    return (
      <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Alert severity="error">
          No session provided for remote desktop connection.
        </Alert>
      </Box>
    );
  }

  if (session.state !== 'ready') {
    return (
      <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', p: 3 }}>
        <Box sx={{ textAlign: 'center' }}>
          <CircularProgress sx={{ mb: 2 }} />
          <Typography variant="h6" color="text.secondary" gutterBottom>
            Session Not Ready
          </Typography>
          <Typography variant="body2" color="text.secondary">
            The session is in "{session.state}" state. Please wait for it to become ready.
          </Typography>
          <Chip
            label={session.state}
            color={session.state === 'initializing' ? 'warning' : 'error'}
            sx={{ mt: 2 }}
          />
        </Box>
      </Box>
    );
  }

  return (
    <Box 
      ref={containerRef}
      sx={{ 
        height: '100%', 
        display: 'flex', 
        flexDirection: 'column',
        backgroundColor: 'black',
        position: 'relative'
      }}
    >
      {/* Controls Bar */}
      <Paper 
        sx={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center', 
          p: 1,
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          color: 'white',
          position: isFullscreen ? 'absolute' : 'relative',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 1000,
          opacity: isFullscreen ? 0.9 : 1,
          transition: 'opacity 0.3s'
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Chip 
            size="small" 
            label={getStatusLabel()} 
            color={getStatusColor()}
          />
          <Typography variant="body2">
            {session.name}
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="body2" sx={{ mr: 1 }}>
            {zoomLevel}%
          </Typography>
          
          <Tooltip title="Zoom Out">
            <IconButton 
              size="small" 
              onClick={handleZoomOut}
              disabled={zoomLevel <= 50}
              sx={{ color: 'white' }}
            >
              <ZoomOutIcon />
            </IconButton>
          </Tooltip>

          <Tooltip title="Fit Screen">
            <IconButton 
              size="small" 
              onClick={handleFitScreen}
              sx={{ color: 'white' }}
            >
              <FitScreenIcon />
            </IconButton>
          </Tooltip>

          <Tooltip title="Zoom In">
            <IconButton 
              size="small" 
              onClick={handleZoomIn}
              disabled={zoomLevel >= 200}
              sx={{ color: 'white' }}
            >
              <ZoomInIcon />
            </IconButton>
          </Tooltip>

          <Divider orientation="vertical" flexItem sx={{ mx: 1, backgroundColor: 'rgba(255,255,255,0.3)' }} />

          <Tooltip title="Take Screenshot">
            <IconButton 
              size="small" 
              onClick={handleScreenshot}
              sx={{ color: 'white' }}
            >
              <ScreenshotIcon />
            </IconButton>
          </Tooltip>

          <Tooltip title="Refresh">
            <IconButton 
              size="small" 
              onClick={handleRefresh}
              sx={{ color: 'white' }}
            >
              <RefreshIcon />
            </IconButton>
          </Tooltip>

          <Tooltip title="Settings">
            <IconButton 
              size="small" 
              onClick={(e) => setSettingsAnchor(e.currentTarget)}
              sx={{ color: 'white' }}
            >
              <SettingsIcon />
            </IconButton>
          </Tooltip>

          <Tooltip title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}>
            <IconButton 
              size="small" 
              onClick={handleFullscreen}
              sx={{ color: 'white' }}
            >
              {isFullscreen ? <FullscreenExitIcon /> : <FullscreenIcon />}
            </IconButton>
          </Tooltip>
        </Box>
      </Paper>

      {/* Error Display */}
      {error && (
        <Alert 
          severity="error" 
          onClose={() => setError(null)}
          sx={{ 
            position: 'absolute', 
            top: isFullscreen ? 60 : 10, 
            left: 10, 
            right: 10, 
            zIndex: 1001 
          }}
        >
          {error}
        </Alert>
      )}

      {/* VNC Viewer */}
      <Box 
        sx={{ 
          flex: 1, 
          overflow: 'hidden',
          transform: `scale(${zoomLevel / 100})`,
          transformOrigin: 'top left',
          width: `${10000 / zoomLevel}%`,
          height: `${10000 / zoomLevel}%`
        }}
      >
        <VncViewer ref={vncRef} />
      </Box>

      {/* Settings Menu */}
      <Menu
        anchorEl={settingsAnchor}
        open={Boolean(settingsAnchor)}
        onClose={() => setSettingsAnchor(null)}
      >
        <MenuItem onClick={() => {
          handleSendKeys('CTRL+ALT+DELETE');
          setSettingsAnchor(null);
        }}>
          <KeyboardIcon sx={{ mr: 1 }} />
          Send Ctrl+Alt+Del
        </MenuItem>
        <MenuItem onClick={() => {
          handleSendKeys('ALT+TAB');
          setSettingsAnchor(null);
        }}>
          <KeyboardIcon sx={{ mr: 1 }} />
          Send Alt+Tab
        </MenuItem>
        <MenuItem onClick={() => {
          handleSendKeys('WIN');
          setSettingsAnchor(null);
        }}>
          <KeyboardIcon sx={{ mr: 1 }} />
          Send Windows Key
        </MenuItem>
        <Divider />
        <MenuItem onClick={() => {
          // Reset connection
          setConnectionStatus('connecting');
          setTimeout(() => setConnectionStatus('connected'), 2000);
          setSettingsAnchor(null);
        }}>
          <RefreshIcon sx={{ mr: 1 }} />
          Reset Connection
        </MenuItem>
      </Menu>

      {/* Keyboard Shortcuts Help */}
      {isFullscreen && (
        <Box
          sx={{
            position: 'absolute',
            bottom: 20,
            right: 20,
            backgroundColor: 'rgba(0, 0, 0, 0.8)',
            color: 'white',
            p: 2,
            borderRadius: 1,
            fontSize: '0.8rem',
            opacity: 0.7,
            zIndex: 1000
          }}
        >
          <Typography variant="caption" display="block">
            Press ESC to exit fullscreen
          </Typography>
          <Typography variant="caption" display="block">
            Right-click for context menu
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default RemoteDesktopPanel;