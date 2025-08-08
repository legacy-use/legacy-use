import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Typography from '@mui/material/Typography';
import { useContext, useEffect, useState } from 'react';
import { Link as RouterLink, useLocation, useParams } from 'react-router-dom';
import type { Job, Session, Target } from '@/gen/endpoints';
import { SessionContext } from '../App';
import {
  deleteSession,
  getJobQueueStatus,
  getJobs,
  getSession,
  getSessions,
  getTarget,
} from '../services/apiService';
import DeleteSessionDialog from './DeleteSessionDialog';
import JobsSection from './JobsSection';
import SessionDetailsCard from './SessionDetailsCard';
import SessionSelector from './SessionSelector';
import TargetInfoCard from './TargetInfoCard';

const TargetDetails = () => {
  const { targetId } = useParams();
  const location = useLocation();
  const { setCurrentSession, setSelectedSessionId } = useContext(SessionContext);

  // Get sessionId from URL query params if it exists
  const queryParams = new URLSearchParams(location.search);
  const sessionIdFromUrl = queryParams.get('sessionId');

  const [target, setTarget] = useState<Target | null>(null);
  const [targetSessions, setTargetSessions] = useState<Session[]>([]);
  const [selectedSession, setSelectedSession] = useState<Session | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [queuedJobs, setQueuedJobs] = useState<Job[]>([]);
  const [executedJobs, setExecutedJobs] = useState<Job[]>([]);
  const [blockingJobs, setBlockingJobs] = useState<Job[]>([]);
  const [queueStatus, setQueueStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showContainerDetails, setShowContainerDetails] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [hardDelete, setHardDelete] = useState(false);
  const [deleteInProgress, setDeleteInProgress] = useState(false);
  const [activeTab, setActiveTab] = useState(0);
  const [copySnackbarOpen, setCopySnackbarOpen] = useState(false);

  useEffect(() => {
    const fetchTargetDetails = async () => {
      try {
        setLoading(true);

        // Fetch target information
        const targetData = await getTarget(targetId);
        setTarget(targetData);

        // Fetch all sessions for this target
        const sessionsData = await getSessions(true); // Include archived sessions
        const filteredSessions = sessionsData.filter(s => s.target_id === targetId);
        setTargetSessions(filteredSessions);

        // If there are sessions, select the appropriate one
        if (filteredSessions.length > 0) {
          let sessionToSelect: Session | undefined;

          // If we have a sessionId from URL, try to find that session
          if (sessionIdFromUrl) {
            sessionToSelect = filteredSessions.find(s => s.id === sessionIdFromUrl);
          }

          // If no session found from URL param, default to most recent
          if (!sessionToSelect) {
            // Sort sessions by creation date (newest first)
            const sortedSessions = [...filteredSessions].sort(
              (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
            );

            sessionToSelect = sortedSessions[0];
          }

          // Fetch detailed session information including container_status
          try {
            const detailedSession = await getSession(sessionToSelect.id);
            setSelectedSession(detailedSession);
            setCurrentSession(detailedSession);
            setSelectedSessionId(detailedSession.id);
          } catch (err) {
            console.error('Error fetching detailed session:', err);
            // Fallback to basic session data
            setSelectedSession(sessionToSelect);
            setCurrentSession(sessionToSelect);
            setSelectedSessionId(sessionToSelect.id);
          }

          // Fetch jobs for the selected session
          fetchJobsForSession();
        }

        setLoading(false);
      } catch (err) {
        console.error('Error fetching target details:', err);
        setError(`Failed to load target details: ${err.message}`);
        setLoading(false);
      }
    };

    fetchTargetDetails();

    // Clean up function
    return () => {
      setCurrentSession(null);
      setSelectedSessionId(null);
    };
  }, [targetId, sessionIdFromUrl, setCurrentSession, setSelectedSessionId]);

  // Add polling for session state updates
  useEffect(() => {
    // Only poll if we have a selected session and it's not archived
    if (selectedSession && !selectedSession.is_archived) {
      const pollInterval = setInterval(async () => {
        try {
          // Fetch the latest sessions data
          const sessionsData = await getSessions(true);
          const updatedSessions = sessionsData.filter(s => s.target_id === targetId);
          setTargetSessions(updatedSessions);

          // Update the selected session if it exists
          const updatedSession = updatedSessions.find(s => s.id === selectedSession.id);
          if (updatedSession) {
            // Fetch detailed session information including container_status
            try {
              const detailedSession = await getSession(updatedSession.id);
              setSelectedSession(detailedSession);
              setCurrentSession(detailedSession);
            } catch (err) {
              console.error('Error fetching detailed session during polling:', err);
              // Fallback to basic session data
              setSelectedSession(updatedSession);
              setCurrentSession(updatedSession);
            }
          }

          // Fetch the latest jobs
          if (selectedSession) {
            fetchJobsForSession();
          }
        } catch (err) {
          console.error('Error polling updates:', err);
        }
      }, 5000); // Poll every 5 seconds

      return () => clearInterval(pollInterval);
    }
  }, [selectedSession, targetId, setCurrentSession]);

  const fetchJobsForSession = async () => {
    try {
      // Fetch jobs for this target without filtering by session
      const jobsData = await getJobs(targetId);
      setJobs(jobsData);

      // Get the target to get blocking jobs information
      const targetData = await getTarget(targetId);

      // Fetch queue status
      try {
        const queueStatusData = await getJobQueueStatus();
        setQueueStatus(queueStatusData);

        // Separate jobs into queued and executed
        // Get blocking jobs from the target data
        const queued = jobsData.filter(job => job.status === 'queued');
        const blocking = targetData.blocking_jobs || [];

        // For executed jobs, filter out queued and blocking jobs
        const blockingIds = new Set(blocking.map(job => job.id));
        const executed = jobsData.filter(
          job => job.status !== 'queued' && !blockingIds.has(job.id), // Exclude jobs that are in the blocking list
        );

        setQueuedJobs(queued);
        setBlockingJobs(blocking);
        setExecutedJobs(executed);
      } catch (queueErr) {
        console.error('Error fetching queue status:', queueErr);
        // If we can't get queue status, just show all jobs as executed
        setExecutedJobs(jobsData);
      }
    } catch (err) {
      console.error('Error fetching jobs:', err);
      setError(`Failed to fetch jobs: ${err.message}`);
    }
  };

  const handleSessionChange = async event => {
    const sessionId = event.target.value;
    const session = targetSessions.find(s => s.id === sessionId);
    
    // Fetch detailed session information including container_status
    try {
      const detailedSession = await getSession(sessionId);
      setSelectedSession(detailedSession);
      setCurrentSession(detailedSession);
      setSelectedSessionId(sessionId);
    } catch (err) {
      console.error('Error fetching detailed session:', err);
      // Fallback to basic session data
      setSelectedSession(session);
      setCurrentSession(session);
      setSelectedSessionId(sessionId);
    }

    // Update URL with the new session ID without navigating
    const newUrl = `/targets/${targetId}?sessionId=${sessionId}`;
    window.history.pushState({}, '', newUrl);

    if (session) {
      fetchJobsForSession();
    } else {
      setJobs([]);
      setQueuedJobs([]);
      setExecutedJobs([]);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'warning';
      case 'success':
        return 'success';
      case 'error':
        return 'error';
      case 'queued':
        return 'info';
      case 'canceled':
        return 'default';
      case 'pending':
        return 'default';
      default:
        return 'default';
    }
  };

  const formatDate = (dateString: string) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  const getDockerImageName = () => {
    // Only use the image information from container status
    if (selectedSession?.container_status?.image) {
      return selectedSession.container_status.image;
    }

    // No fallback, just show that we don't have information
    return 'Unknown';
  };

  const getContainerName = (sessionId: string) => {
    if (!sessionId) return 'N/A';
    // Use the same naming convention as in the backend
    const shortId = sessionId.replace(/-/g, '').substring(0, 12);
    return `legacy-use-session-${shortId}`;
  };

  const fetchContainerStatus = async () => {
    try {
      // Fetch the updated sessions data
      const sessionsData = await getSessions();
      const updatedSessions = sessionsData.filter(s => s.target_id === targetId);
      setTargetSessions(updatedSessions);

      // Update the selected session if it exists
      if (selectedSession) {
        // Fetch detailed session information including container_status
        try {
          const detailedSession = await getSession(selectedSession.id);
          setSelectedSession(detailedSession);
          setCurrentSession(detailedSession);
        } catch (err) {
          console.error('Error fetching detailed session during refresh:', err);
          // Fallback to basic session data
          const updatedSession = updatedSessions.find(s => s.id === selectedSession.id);
          if (updatedSession) {
            setSelectedSession(updatedSession);
            setCurrentSession(updatedSession);
          }
        }
      }
    } catch (err) {
      console.error('Error refreshing session data:', err);
    }
  };

  const handleDeleteClick = () => {
    // If the session is already archived, set hardDelete to true
    setHardDelete(selectedSession.is_archived);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    try {
      setDeleteInProgress(true);
      await deleteSession(selectedSession.id, hardDelete);

      // Refresh the sessions list
      const sessionsData = await getSessions(true);
      const filteredSessions = sessionsData.filter(s => s.target_id === targetId);
      setTargetSessions(filteredSessions);

      // Select another session if available, otherwise clear selection
      if (filteredSessions.length > 0) {
        setSelectedSession(filteredSessions[0]);
        setCurrentSession(filteredSessions[0]);
        fetchJobsForSession();
      } else {
        setSelectedSession(null);
        setCurrentSession(null);
        setJobs([]);
      }
    } catch (err) {
      console.error('Error deleting session:', err);
      setError(`Failed to delete session: ${err.message}`);
    } finally {
      setDeleteInProgress(false);
      setDeleteDialogOpen(false);
    }
  };

  const handleDeleteCancel = () => {
    if (deleteInProgress) return; // Prevent closing while delete is in progress
    setDeleteDialogOpen(false);
  };

  // Add a function to get state badge color
  const getStateBadgeColor = state => {
    switch (state) {
      case 'initializing':
        return 'warning';
      case 'authenticating':
        return 'info';
      case 'ready':
        return 'success';
      case 'destroying':
        return 'error';
      case 'destroyed':
        return 'default';
      default:
        return 'default';
    }
  };

  // Handle browser back/forward navigation
  useEffect(() => {
    const handlePopState = () => {
      // Get the updated sessionId from URL query params
      const params = new URLSearchParams(window.location.search);
      const newSessionId = params.get('sessionId');

      // Find that session in our list of target sessions
      if (newSessionId && targetSessions.length > 0) {
        const session = targetSessions.find(s => s.id === newSessionId);
        if (session) {
          setSelectedSession(session);
          setCurrentSession(session);
          setSelectedSessionId(newSessionId);
          fetchJobsForSession();
        }
      }
    };

    // Add event listener for browser back button
    window.addEventListener('popstate', handlePopState);

    // Clean up
    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, [targetSessions, setCurrentSession, setSelectedSessionId]);

  const handleCopyToClipboard = (text, event) => {
    if (event) event.stopPropagation();
    navigator.clipboard
      .writeText(text)
      .then(() => {
        setCopySnackbarOpen(true);
      })
      .catch(err => {
        console.error('Error copying to clipboard:', err);
      });
  };

  const handleCopySnackbarClose = () => {
    setCopySnackbarOpen(false);
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box>
        <Button component={RouterLink} to="/targets" startIcon={<ArrowBackIcon />} sx={{ mb: 2 }}>
          Back to Targets
        </Button>
        <Typography color="error">{error}</Typography>
      </Box>
    );
  }

  if (!target) {
    return <Typography>Target not found</Typography>;
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Button component={RouterLink} to="/targets" startIcon={<ArrowBackIcon />}>
          Back to Targets
        </Button>
      </Box>

      {target && (
        <>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
            <Typography variant="h4">
              {target.name || `Target ${target.id.substring(0, 8)}`}
            </Typography>
          </Box>

          <TargetInfoCard target={target} formatDate={formatDate} />

          <JobsSection
            jobs={jobs}
            blockingJobs={blockingJobs}
            queuedJobs={queuedJobs}
            executedJobs={executedJobs}
            queueStatus={queueStatus}
            activeTab={activeTab}
            setActiveTab={setActiveTab}
            targetId={targetId}
            selectedSession={selectedSession}
            setSelectedSessionId={setSelectedSessionId}
            formatDate={formatDate}
            getStatusColor={getStatusColor}
          />

          <SessionSelector
            targetSessions={targetSessions}
            selectedSession={selectedSession}
            handleSessionChange={handleSessionChange}
          />

          {selectedSession && (
            <SessionDetailsCard
              selectedSession={selectedSession}
              showContainerDetails={showContainerDetails}
              setShowContainerDetails={setShowContainerDetails}
              fetchContainerStatus={fetchContainerStatus}
              handleDeleteClick={handleDeleteClick}
              handleCopyToClipboard={handleCopyToClipboard}
              copySnackbarOpen={copySnackbarOpen}
              handleCopySnackbarClose={handleCopySnackbarClose}
              getDockerImageName={getDockerImageName}
              getContainerName={getContainerName}
              getStateBadgeColor={getStateBadgeColor}
            />
          )}
        </>
      )}

      <DeleteSessionDialog
        open={deleteDialogOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        hardDelete={hardDelete}
        deleteInProgress={deleteInProgress}
      />
    </Box>
  );
};

export default TargetDetails;
