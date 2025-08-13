import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import { useContext, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { SessionContext } from '../App';
import { API_BASE_URL } from '../utils/apiConstants';

const VncViewer = ({ viewOnly = true }: { viewOnly?: boolean }) => {
  const location = useLocation();
  const { selectedSessionId, currentSession } = useContext(SessionContext);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [cookieSet, setCookieSet] = useState<boolean>(false);

  // Get session ID from context or URL
  useEffect(() => {
    setLoading(true);

    // First try to get session ID from context (for API page)
    if (selectedSessionId) {
      setSessionId(selectedSessionId);
      setLoading(false);
      return;
    }

    // Otherwise extract from URL path (for session details page)
    const pathParts = location.pathname.split('/');
    const sessionIdIndex = pathParts.indexOf('sessions') + 1;

    if (sessionIdIndex > 0 && sessionIdIndex < pathParts.length) {
      setSessionId(pathParts[sessionIdIndex]);
      setLoading(false);
    } else {
      setError('No active session found. Please select a session first.');
      setLoading(false);
    }
  }, [location.pathname, selectedSessionId]);

  // set cookie for api key
  // Future improvement: session-based authentication approach on the backend
  useEffect(() => {
    if (sessionId) {
      const cookieName = `vnc_auth_${sessionId}`;
      const apiKey = localStorage.getItem('apiKey');
      const maxAge = 60 * 60 * 24 * 1; // 1 day
      const secure = window.location.protocol === 'https:' ? 'Secure' : '';
      if (apiKey) {
        // biome-ignore lint/suspicious/noDocumentCookie: use cookie for vnc auth
        document.cookie = `${cookieName}=${apiKey}; Max-Age=${maxAge}; ${secure}; Path=/`;
        // Set cookieSet to true after the cookie is set
        setCookieSet(true);
      } else {
        setError('No API key found. Please set your API key first.');
      }
    } else {
      setCookieSet(false);
    }
  }, [sessionId]);

  // We should only render the VNC viewer if the session is ready
  // This component should not be rendered at all for other states
  // But we'll add these checks as a safeguard
  if (!currentSession || currentSession.is_archived || currentSession.state !== 'ready') {
    return null;
  }

  // Use the same hostname as the frontend - Vite will proxy /api requests to the backend
  const baseApiUrl = window.location.origin;

  // Show loading while we're getting session ID or setting cookie
  if (loading || !cookieSet) {
    return (
      <Paper
        elevation={3}
        sx={{
          height: 'calc(100vh - 100px)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
        }}
      >
        <CircularProgress />
      </Paper>
    );
  }

  if (error || !sessionId) {
    return (
      <Paper
        elevation={3}
        sx={{
          height: 'calc(100vh - 100px)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          p: 3,
        }}
      >
        <Typography variant="h6" color="error" align="center">
          {error || 'No session selected'}
        </Typography>
      </Paper>
    );
  }

  // Construct the VNC URL using our proxy endpoint
  // Remove leading slash to avoid double slash when concatenating with baseApiUrl
  const proxyPath = `sessions/${sessionId}/vnc`;

  // Use API_BASE_URL constant while preserving double slash prevention logic
  // API_BASE_URL is '/api', so we need to construct the full path properly
  const combinedWebsocketPath = `${API_BASE_URL}/${proxyPath}/websockify`;
  // Remove any leading slashes to avoid double slashes
  const websocketPath = combinedWebsocketPath.replace(/^\/+/, '');

  const vncParams = `resize=scale&autoconnect=1&view_only=${viewOnly ? 1 : 0}&reconnect=1&reconnect_delay=2000&path=${websocketPath}`;

  const vncUrl = `${baseApiUrl}${API_BASE_URL}/${proxyPath}/vnc.html?${vncParams}`;

  return (
    <Paper
      elevation={3}
      sx={{
        height: 'calc(100vh - 100px)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      <Box sx={{ flexGrow: 1, overflow: 'hidden' }}>
        <iframe
          src={vncUrl}
          title="VNC Viewer"
          style={{
            width: '100%',
            height: '100%',
            border: 'none',
          }}
        />
      </Box>
    </Paper>
  );
};

export default VncViewer;
