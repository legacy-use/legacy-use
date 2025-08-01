// biome-ignore assist/source/organizeImports: must be on top
import CssBaseline from '@mui/material/CssBaseline';

import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Grid from '@mui/material/Grid';
import Paper from '@mui/material/Paper';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import Typography from '@mui/material/Typography';
import React, { useEffect, useState } from 'react';
import { Outlet, Route, BrowserRouter as Router, Routes, useLocation } from 'react-router-dom';
import ApiKeyDialog from './components/ApiKeyDialog';
import ApiList from './components/ApiList';
import AppHeader from './components/AppHeader';
import CreateSession from './components/CreateSession';
import CreateTarget from './components/CreateTarget';
import Dashboard from './components/Dashboard';
import EditApiDefinition from './components/EditApiDefinition';
import InteractiveSession from './components/InteractiveSession';
import JobDetails from './components/JobDetails';
import JobsList from './components/JobsList';
import OnboardingWizard from './components/OnboardingWizard';
import SessionList from './components/SessionList';
import TargetDetails from './components/TargetDetails';
import TargetList from './components/TargetList';
import VncViewer from './components/VncViewer';
import { AiProvider, useAiProvider } from './contexts/AiProviderContext';
import { ApiKeyProvider, useApiKey } from './contexts/ApiKeyContext';
import type { Session } from './gen/endpoints';
import { getSessions, setApiKeyHeader, testApiKey } from './services/apiService';

// Create a dark theme
const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#90caf9',
    },
    secondary: {
      main: '#f48fb1',
    },
    background: {
      default: '#121212',
      paper: '#1e1e1e',
    },
  },
  shape: {
    borderRadius: 12, // Slightly rounded corners for all components
  },
  components: {
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: '#1e1e1e',
        },
      },
    },
  },
});

// Context for sharing selected session across components
export const SessionContext = React.createContext({
  selectedSessionId: null as string | null,
  setSelectedSessionId: (_id: string | null) => {},
  currentSession: null as Session | null,
  setCurrentSession: (_session: Session | null) => {},
});

// Placeholder component for archived sessions
const ArchivedSessionPlaceholder = () => {
  return (
    <Paper
      elevation={3}
      sx={{
        height: 'calc(100vh - 100px)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.1)',
        p: 3,
      }}
    >
      <Box sx={{ textAlign: 'center' }}>
        <Typography variant="h5" color="text.secondary" gutterBottom>
          VNC Viewer Not Available
        </Typography>
        <Typography variant="body1" color="text.secondary">
          This session is archived. The VNC connection is no longer available.
        </Typography>
      </Box>
    </Paper>
  );
};

// Placeholder for sessions that are not ready
const NotReadySessionPlaceholder = ({ session }: { session: Session }) => {
  // Get a user-friendly message based on the state
  const getStateMessage = (state: Session['state']) => {
    switch (state) {
      case 'initializing':
        return 'The session is initializing. Please wait while the container starts up.';
      case 'authenticating':
        return 'The session is authenticating. Please wait while credentials are verified.';
      case 'destroying':
        return 'The session is being destroyed. Please wait while resources are cleaned up.';
      default:
        return `The session is in the "${state}" state. The VNC connection is not available yet.`;
    }
  };

  return (
    <Paper
      elevation={3}
      sx={{
        height: 'calc(100vh - 100px)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.1)',
        p: 3,
      }}
    >
      <Box sx={{ textAlign: 'center' }}>
        <CircularProgress sx={{ mb: 3 }} />
        <Typography variant="h5" color="text.secondary" gutterBottom>
          VNC Viewer Not Available
        </Typography>
        <Typography variant="body1" color="text.secondary" gutterBottom>
          {getStateMessage(session.state)}
        </Typography>
        <Chip
          label={session.state || 'unknown'}
          size="small"
          color={
            session.state === 'initializing'
              ? 'warning'
              : session.state === 'authenticating'
                ? 'info'
                : session.state === 'ready'
                  ? 'success'
                  : session.state === 'destroying'
                    ? 'error'
                    : 'default'
          }
          sx={{ mt: 1 }}
        />
      </Box>
    </Paper>
  );
};

// Layout component that conditionally renders the VNC viewer
const AppLayout = () => {
  const location = useLocation();
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const { apiKey, setIsApiKeyValid } = useApiKey();
  const [apiKeyDialogOpen, setApiKeyDialogOpen] = useState(false);
  const [isValidatingApiKey, setIsValidatingApiKey] = useState(true);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [hasCompletedOnboarding, setHasCompletedOnboarding] = useState(false);
  const { isProviderValid } = useAiProvider();

  // Check if we're on a session detail page or job detail page
  const isSessionDetail =
    location.pathname.includes('/sessions/') && !location.pathname.includes('/sessions/new');

  // Check if we're on a job detail page
  const isJobDetail = location.pathname.includes('/jobs/');

  // Check if we're on a target detail page
  const isTargetDetail =
    location.pathname.includes('/targets/') && !location.pathname.includes('/targets/new');

  // Extract session ID from URL if we're on a session detail page
  useEffect(() => {
    if (isSessionDetail) {
      const pathParts = location.pathname.split('/');
      const sessionIdIndex = pathParts.indexOf('sessions') + 1;

      if (sessionIdIndex > 0 && sessionIdIndex < pathParts.length) {
        const newSessionId = pathParts[sessionIdIndex];
        setSelectedSessionId(newSessionId);
      }
    }
  }, [isSessionDetail, location.pathname]);

  // Fetch session details when selectedSessionId changes
  useEffect(() => {
    if (selectedSessionId) {
      const fetchSessionDetails = async () => {
        try {
          const sessionsData = await getSessions(true); // Include archived sessions
          const sessionData = sessionsData.find(s => s.id === selectedSessionId);
          setCurrentSession(sessionData || null);
        } catch (err) {
          console.error('Error fetching session details:', err);
          setCurrentSession(null);
        }
      };

      fetchSessionDetails();
    } else {
      setCurrentSession(null);
    }
  }, [selectedSessionId]);

  // Check if user has completed onboarding
  useEffect(() => {
    const onboardingCompleted = localStorage.getItem('onboardingCompleted');
    const hasOnboarded = onboardingCompleted === 'true';
    setHasCompletedOnboarding(hasOnboarded);

    // Show onboarding for new users without API key
    // Disabled: onboarding dialog will not open automatically
    // if (!hasOnboarded) {
    //   setOnboardingOpen(true);
    // }
  }, [apiKey]);

  // Validate API key on mount and when it changes
  useEffect(() => {
    const validateApiKey = async () => {
      setIsValidatingApiKey(true);
      if (apiKey) {
        try {
          // Set the API key header for all requests
          setApiKeyHeader(apiKey);

          // Test if the API key is valid
          await testApiKey(apiKey);

          // If successful, mark the API key as valid
          setIsApiKeyValid(true);
          setApiKeyDialogOpen(false);
        } catch (error) {
          console.error('API key validation failed:', error);
          setIsApiKeyValid(false);
          setApiKeyDialogOpen(true);
        }
      } else {
        setApiKeyHeader(null);
        setIsApiKeyValid(false);
        setApiKeyDialogOpen(true);
      }
      setIsValidatingApiKey(false);
    };

    validateApiKey();
  }, [apiKey, setIsApiKeyValid, hasCompletedOnboarding]);

  // Extract session ID from URL if we're on a target detail page
  useEffect(() => {
    if (isTargetDetail) {
      const searchParams = new URLSearchParams(location.search);
      const sessionIdParam = searchParams.get('sessionId');

      if (sessionIdParam) {
        setSelectedSessionId(sessionIdParam);
      }
    }
  }, [isTargetDetail, location.search, setSelectedSessionId]);

  // Determine if we should show the VNC viewer
  // Show it for session details, job details, API page with a selected session, or target details with a selected session
  // But don't show it for archived sessions or sessions not in ready state
  const showVncViewer =
    (isSessionDetail ||
      isJobDetail ||
      isTargetDetail ||
      (location.pathname === '/apis' && selectedSessionId)) &&
    !currentSession?.is_archived &&
    currentSession &&
    currentSession.state === 'ready';
  const isInteractiveMode = location.pathname.includes('/interactive');

  // Determine if we should show the not ready placeholder
  const showNotReadyPlaceholder =
    (isSessionDetail ||
      isJobDetail ||
      isTargetDetail ||
      (location.pathname === '/apis' && selectedSessionId)) &&
    currentSession &&
    !currentSession.is_archived &&
    currentSession.state !== 'ready';

  // Determine if we should show the archived placeholder
  const showArchivedPlaceholder =
    (isSessionDetail ||
      isJobDetail ||
      isTargetDetail ||
      (location.pathname === '/apis' && selectedSessionId)) &&
    currentSession &&
    currentSession.is_archived;

  // Adjust the grid layout based on what's being shown
  const showRightPanel = showVncViewer || showNotReadyPlaceholder || showArchivedPlaceholder;

  // Handle onboarding completion
  const handleOnboardingComplete = () => {
    localStorage.setItem('onboardingCompleted', 'true');
    setHasCompletedOnboarding(true);
    setOnboardingOpen(false);
  };

  // Show loading state while validating API key
  if (isValidatingApiKey) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
        }}
      >
        <Typography variant="h6">Validating API key...</Typography>
      </Box>
    );
  }

  return (
    <SessionContext.Provider
      value={{ selectedSessionId, setSelectedSessionId, currentSession, setCurrentSession }}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
        <AppHeader />

        {/* Show warning if no ai provider is configured */}
        {!isProviderValid && !onboardingOpen && (
          <Box sx={{ p: 2 }}>
            <Alert
              severity="warning"
              action={
                <Button color="inherit" size="small" onClick={() => setOnboardingOpen(true)}>
                  Complete Onboarding
                </Button>
              }
            >
              No AI provider configured. Please complete the onboarding wizard or configure a custom
              AI provider to use the app.
            </Alert>
          </Box>
        )}

        <Box component="main" sx={{ flexGrow: 1, overflow: 'hidden' }}>
          <Grid container sx={{ height: '100%' }}>
            {/* Left panel - adjusts width based on whether VNC viewer is shown */}
            <Grid
              item
              xs={12}
              md={showRightPanel ? 4 : 12}
              lg={showRightPanel ? 3.6 : 12}
              sx={{
                height: '100%',
                overflow: 'auto',
                borderRight: showRightPanel ? '1px solid rgba(255, 255, 255, 0.12)' : 'none',
                p: 2,
              }}
            >
              <Outlet />
            </Grid>

            {/* Right panel - shown for session details or API page with selected session */}
            {showRightPanel && (
              <Grid
                item
                xs={12}
                md={showRightPanel ? 8 : 12}
                lg={showRightPanel ? 8.4 : 12}
                sx={{ height: '100%', p: 2 }}
              >
                {showVncViewer && <VncViewer viewOnly={!isInteractiveMode} />}
                {showNotReadyPlaceholder && <NotReadySessionPlaceholder session={currentSession} />}
                {showArchivedPlaceholder && <ArchivedSessionPlaceholder />}
              </Grid>
            )}
          </Grid>
        </Box>
      </Box>

      {/* API Key Dialog */}
      <ApiKeyDialog open={apiKeyDialogOpen} onClose={() => setApiKeyDialogOpen(false)} />

      {/* Onboarding Wizard */}
      <OnboardingWizard
        open={onboardingOpen && !apiKeyDialogOpen}
        onClose={() => setOnboardingOpen(false)}
        onComplete={handleOnboardingComplete}
      />
    </SessionContext.Provider>
  );
};

function App() {
  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <ApiKeyProvider>
        <AiProvider>
          <Router
            future={{
              v7_relativeSplatPath: true,
              v7_startTransition: true,
            }}
          >
            <Routes>
              <Route element={<AppLayout />}>
                <Route path="" element={<Dashboard />} />
                <Route path="apis" element={<ApiList />} />
                <Route path="apis/:apiName/edit" element={<EditApiDefinition />} />
                <Route path="sessions" element={<SessionList />} />
                <Route path="sessions/new" element={<CreateSession />} />
                <Route path="sessions/:sessionId" element={<TargetDetails />} />
                <Route path="sessions/:sessionId/interactive" element={<InteractiveSession />} />
                <Route path="jobs" element={<JobsList />} />
                <Route path="jobs/:targetId/:jobId" element={<JobDetails />} />
                <Route path="targets" element={<TargetList />} />
                <Route path="targets/new" element={<CreateTarget />} />
                <Route path="targets/:targetId" element={<TargetDetails />} />
              </Route>
            </Routes>
          </Router>
        </AiProvider>
      </ApiKeyProvider>
    </ThemeProvider>
  );
}

export default App;
