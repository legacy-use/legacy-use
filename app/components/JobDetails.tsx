import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControl,
  MenuItem,
  Select,
  TextField,
  Typography,
} from '@mui/material';
import { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import type { HttpExchangeLog, Job, JobLogEntry, Target } from '@/gen/endpoints';
import { SessionContext } from '../App';
import {
  cancelJob,
  createJob,
  getApiDefinitionDetails,
  getJob,
  getJobHttpExchanges,
  getJobLogs,
  getSession,
  getTargets,
  interruptJob,
  resolveJob,
  resumeJob,
} from '../services/apiService';
import { getJobStatusChipColor } from '../utils/jobStatus';
import JobStatusCard from './JobStatusCard';
import JobTabs from './JobTabs';

const JobDetails = () => {
  const { targetId, jobId } = useParams();
  const targetIdReq = targetId as string;
  const jobIdReq = jobId as string;
  const navigate = useNavigate();
  const { setSelectedSessionId, setCurrentSession } = useContext(SessionContext);
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<(JobLogEntry & { type: string })[]>([]);
  const [httpExchanges, setHttpExchanges] = useState<HttpExchangeLog[]>([]);
  const [, setLogsLoading] = useState<boolean>(true);
  const [httpExchangesLoading, setHttpExchangesLoading] = useState<boolean>(false);
  const [httpExchangesLoaded, setHttpExchangesLoaded] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<number>(0);
  const [interrupting, setInterrupting] = useState<boolean>(false);
  const lastRefreshTimeRef = useRef<number>(0);
  const pollingActiveRef = useRef<boolean>(false);
  const logsLoadedRef = useRef<boolean>(false);
  const [showTargetDialog, setShowTargetDialog] = useState<boolean>(false);
  const [availableTargets, setAvailableTargets] = useState<Target[]>([]);
  const [rerunning, setRerunning] = useState<boolean>(false);
  const [selectedTargetForRerun, setSelectedTargetForRerun] = useState<string>('');

  // State for resolving a job
  const [resolveDialogOpen, setResolveDialogOpen] = useState<boolean>(false);
  const [resolving, setResolving] = useState<boolean>(false);
  const [resolveResult, setResolveResult] = useState<any>({});
  const [canceling, setCanceling] = useState<boolean>(false);
  const [resuming, setResuming] = useState<boolean>(false);

  // Normalize job status for consistent comparison
  const normalizedJobStatus = job?.status?.toLowerCase() || '';

  // Function to refresh job status
  const refreshJobStatus = useCallback(async () => {
    console.log(`[${new Date().toISOString()}] Refreshing job status`);
    try {
      const jobData = await getJob(targetIdReq, jobIdReq);
      console.log(`[${new Date().toISOString()}] Job status refreshed: ${jobData.status}`);
      setJob(jobData);
      return jobData;
    } catch (err) {
      console.error(`[${new Date().toISOString()}] Error refreshing job status:`, err);
      return null;
    }
  }, [targetIdReq, jobIdReq]);

  // Function to fetch HTTP exchanges
  const fetchJobHttpExchanges = useCallback(async () => {
    // Check if this is an initial load or a polling update
    const isInitialLoad = !httpExchanges.length || !httpExchangesLoaded;

    console.log(
      `[${new Date().toISOString()}] Starting to fetch HTTP exchanges (initial load: ${isInitialLoad})...`,
    );

    try {
      // Only show loading indicator for initial loads, not polling updates
      if (isInitialLoad) {
        setHttpExchangesLoading(true);
      }

      const httpExchangesData = await getJobHttpExchanges(targetIdReq, jobIdReq);
      console.log(
        `[${new Date().toISOString()}] Completed fetching HTTP exchanges, received ${httpExchangesData.length} exchanges`,
      );
      setHttpExchanges(httpExchangesData);
      setHttpExchangesLoaded(true);
    } catch (err) {
      console.error(`[${new Date().toISOString()}] Error fetching job HTTP exchanges:`, err);
    } finally {
      if (isInitialLoad) {
        setHttpExchangesLoading(false);
      }
    }
  }, [targetIdReq, jobIdReq, httpExchanges.length, httpExchangesLoaded]);

  // Function to fetch job logs
  const fetchJobLogs = useCallback(async () => {
    // Check if this is an initial load or a polling update
    const isInitialLoad = !logs.length || !logsLoadedRef.current;

    try {
      // Only show loading indicator for initial loads, not polling updates
      if (isInitialLoad) {
        setLogsLoading(true);
      }

      const logsData = await getJobLogs(targetIdReq, jobIdReq);
      console.log(`[${new Date().toISOString()}] Received ${logsData.length} log entries`);
      setLogs(logsData);
      logsLoadedRef.current = true;
    } catch (err) {
      console.error(`[${new Date().toISOString()}] Error fetching job logs:`, err);
      // Set logs to empty array in case of error to avoid UI hanging
      setLogs([]);
    } finally {
      if (isInitialLoad) {
        setLogsLoading(false);
      }
    }
  }, [targetIdReq, jobIdReq, logs.length]);

  // Define handleRefresh before any useEffect hooks that use it
  const handleRefresh = useCallback(async () => {
    console.log(`[${new Date().toISOString()}] Manual refresh requested`);

    // Prevent multiple refreshes in quick succession
    const now = Date.now();
    const minimumRefreshInterval = 1000; // Minimum 1 second between refreshes

    if (
      now - lastRefreshTimeRef.current < minimumRefreshInterval &&
      lastRefreshTimeRef.current > 0
    ) {
      console.log(
        `Throttling refresh requests. Last refresh was ${now - lastRefreshTimeRef.current}ms ago.`,
      );
      return;
    }

    // Update last refresh time
    lastRefreshTimeRef.current = now;

    // Define hasExistingJobData variable before the try block so it's accessible in finally
    const hasExistingJobData = !!job;

    try {
      // Only show loading for the initial job status fetch, not for the whole refresh process
      if (!hasExistingJobData) {
        setLoading(true);
      }

      // Use the refreshJobStatus function to refresh job details
      const jobData = await refreshJobStatus();

      // Preserve the API definition version which doesn't change
      if (jobData) {
        setJob(
          prevJob =>
            ({
              ...jobData,
              api_definition_version: (prevJob as any)?.api_definition_version,
            }) as Job,
        );
      }

      // Determine which tab is active and refresh only that data
      const isHttpTab = job?.error ? activeTab === 2 : activeTab === 1;

      if (isHttpTab) {
        // HTTP exchanges tab is active
        console.log(`[${new Date().toISOString()}] Refreshing HTTP exchanges for active tab`);
        await fetchJobHttpExchanges();
      } else if (activeTab === 0 || (job?.error && activeTab === 1)) {
        // Logs tab or error tab is active
        console.log(`[${new Date().toISOString()}] Refreshing logs for active tab`);
        logsLoadedRef.current = false; // Reset the logs loaded flag to force a reload
        await fetchJobLogs();
      }
    } catch (err: any) {
      console.error('Error refreshing job details:', err);
      setError(`Failed to refresh job details: ${err.message || 'Unknown error'}`);
    } finally {
      if (!hasExistingJobData) {
        setLoading(false);
      }
    }
  }, [
    targetIdReq,
    jobIdReq,
    refreshJobStatus,
    fetchJobLogs,
    fetchJobHttpExchanges,
    activeTab,
    job,
  ]);

  // Effect to update the VNC viewer context
  useEffect(() => {
    // If the job has a session_id, update the context for VNC viewer
    const sid = job?.session_id;
    if (sid) {
      const fetchSessionDetails = async () => {
        try {
          const sessionData = await getSession(sid as string);
          if (sessionData) {
            setSelectedSessionId(sid as string);
            setCurrentSession(sessionData as any);
          }
        } catch (err) {
          console.error('Error fetching session details for VNC viewer:', err);
        }
      };

      fetchSessionDetails();
    }

    // Clean up function to reset the session context when unmounting
    return () => {
      setSelectedSessionId(null);
      setCurrentSession(null);
    };
  }, [job?.session_id, setSelectedSessionId, setCurrentSession]);

  // Initial load effect - only runs once on component mount
  useEffect(() => {
    let isMounted = true;

    const fetchInitialData = async () => {
      try {
        setLoading(true);

        // First, get job details
        const jobData = await getJob(targetIdReq, jobIdReq);

        if (isMounted) {
          // Store the job data, including any version info that might be present
          setJob(jobData);

          // Then fetch logs for the initially active tab (which is logs by default)
          await fetchJobLogs();
        }
      } catch (err: any) {
        if (isMounted) {
          setError(`Failed to load job details: ${err.message || 'Unknown error'}`);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    // Perform initial data fetch
    fetchInitialData();

    return () => {
      isMounted = false;
    };
  }, [targetIdReq, jobIdReq, fetchJobLogs]);

  // Setup polling for logs when job is running (separate from initial load)
  useEffect(() => {
    // Only set up polling if we have job data and it's in RUNNING or QUEUED state
    // Stop polling if job is COMPLETED, FAILED, CANCELED, INTERRUPTED, or PAUSED
    const activePollingStates = ['running', 'queued'];
    if (!job || !activePollingStates.includes((job.status || '').toLowerCase())) {
      // console.log(`[${new Date().toISOString()}] Job status is ${job?.status}, not setting up polling`);
      return; // Stop polling if not running or queued
    }

    console.log(`[${new Date().toISOString()}] Job is ${job.status}, setting up polling for logs`);
    let pollingInterval: number | null = null;

    // Poll every 2 seconds
    pollingInterval = window.setInterval(async () => {
      // Prevent multiple polling calls from running simultaneously
      if (pollingActiveRef.current) {
        console.log(
          `[${new Date().toISOString()}] Previous polling operation still in progress, skipping this cycle`,
        );
        return;
      }

      console.log(`[${new Date().toISOString()}] Polling for job status`);
      pollingActiveRef.current = true;

      try {
        // Check if the job is still running or queued
        const jobData = await getJob(targetIdReq, jobIdReq);

        if (!jobData) {
          pollingActiveRef.current = false;
          return;
        }

        console.log(`[${new Date().toISOString()}] Current job status: ${jobData.status}`);

        // Update job state but preserve the prompt version which doesn't change
        setJob(
          prevJob =>
            ({
              ...jobData,
              api_definition_version: (prevJob as any)?.api_definition_version, // Preserve the version info
            }) as Job,
        );

        // If job is no longer running or queued (e.g., becomes PAUSED), clear the interval
        if (!activePollingStates.includes((jobData.status || '').toLowerCase())) {
          // console.log(`[${new Date().toISOString()}] Job is no longer running or queued (${jobData.status}), stopping polling`);

          // Reset the logs loaded flag to force a reload of the final logs
          logsLoadedRef.current = false;

          // Get the final logs or HTTP exchanges based on active tab
          try {
            // If on logs tab or error tab, fetch logs
            if (activeTab === 0 || (jobData.error && activeTab === 1)) {
              console.log(`[${new Date().toISOString()}] Fetching final logs for active tab`);
              await fetchJobLogs();
            }

            // If on HTTP exchanges tab, fetch HTTP exchanges
            const isHttpTab = jobData.error ? activeTab === 2 : activeTab === 1;
            if (isHttpTab) {
              console.log(
                `[${new Date().toISOString()}] Fetching final HTTP exchanges for active tab`,
              );
              await fetchJobHttpExchanges();
            }
          } catch (err) {
            console.error(`[${new Date().toISOString()}] Error fetching final data:`, err);
          }

          // Clear the interval
          if (pollingInterval) {
            clearInterval(pollingInterval);
          }
          pollingActiveRef.current = false;
          return;
        }

        // If job is still running or queued, fetch data based on active tab
        try {
          // If on logs tab or error tab, fetch logs
          if (activeTab === 0 || (jobData.error && activeTab === 1)) {
            console.log(`[${new Date().toISOString()}] Polling logs for active tab`);
            // Just set the flag to false but let the fetchJobLogs function handle showing loading state
            logsLoadedRef.current = false;
            await fetchJobLogs();
          }

          // If on HTTP exchanges tab, fetch HTTP exchanges
          const isHttpTab = jobData.error ? activeTab === 2 : activeTab === 1;
          if (isHttpTab) {
            console.log(`[${new Date().toISOString()}] Polling HTTP exchanges for active tab`);
            await fetchJobHttpExchanges();
          }
        } catch (err) {
          console.error(`[${new Date().toISOString()}] Error fetching data during polling:`, err);
        }
      } catch (err) {
        console.error(
          `[${new Date().toISOString()}] Error checking job status during polling:`,
          err,
        );
      } finally {
        pollingActiveRef.current = false;
      }
    }, 2000); // Poll every 2 seconds

    // Cleanup function to clear the interval when component unmounts or job status changes
    return () => {
      if (pollingInterval) {
        console.log(`[${new Date().toISOString()}] Clearing polling interval`);
        clearInterval(pollingInterval);
      }
    };
  }, [
    targetIdReq,
    jobIdReq,
    job?.status,
    activeTab,
    httpExchangesLoaded,
    fetchJobLogs,
    fetchJobHttpExchanges,
  ]);

  // Watch for job status changes (separate from polling)
  useEffect(() => {
    // Skip the initial render when job is null
    if (!job) return;

    // Track job status changes and fetch data as needed
    console.log(`[${new Date().toISOString()}] Job status changed or updated: ${job.status}`);
  }, [job?.status]); // Only depend on job status

  const handleInterruptJob = async () => {
    if (interrupting) return;

    try {
      setInterrupting(true);
      await interruptJob(targetIdReq, jobIdReq);

      // Refresh job status after interruption
      refreshJobStatus();

      setTimeout(() => {
        setInterrupting(false);
      }, 2000);
    } catch (err) {
      console.error('Error interrupting job:', err);
      setError(`Failed to interrupt job: ${err.message || 'Unknown error'}`);
      setInterrupting(false);
    }
  };

  // Handle tab change
  const handleTabChange = (_: any, newValue: number) => {
    console.log(`[${new Date().toISOString()}] Tab changed to index ${newValue}`);
    setActiveTab(newValue);

    // Reset the appropriate loaded flag and fetch data for the newly selected tab
    const isHttpTab = job?.error ? newValue === 2 : newValue === 1;

    if (isHttpTab) {
      console.log(`[${new Date().toISOString()}] HTTP tab selected, loading HTTP exchanges`);
      fetchJobHttpExchanges();
    } else if (newValue === 0 || (job?.error && newValue === 1)) {
      // This is the logs tab or error tab
      console.log(`[${new Date().toISOString()}] Logs tab selected, loading logs`);
      logsLoadedRef.current = false;
      fetchJobLogs();
    }
  };

  // Format timestamp for UI display
  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  // Calculate and format duration
  const formatDuration = (startDate?: string, endDate?: string) => {
    if (!startDate) return 'N/A';
    const start = new Date(startDate);
    const end = endDate ? new Date(endDate) : new Date();
    const diff = end.getTime() - start.getTime();
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) {
      return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    } else {
      return `${seconds}s`;
    }
  };

  // Get color based on job status
  const getStatusColor = (status?: string) => getJobStatusChipColor(status);

  // Handle rerun job button click
  const handleRerun = async () => {
    try {
      // Fetch available targets
      const targets = await getTargets();
      setAvailableTargets(targets.filter(target => !target.is_archived));

      // Set current target as default
      setSelectedTargetForRerun(targetIdReq);

      // Show dialog
      setShowTargetDialog(true);
    } catch (err: any) {
      setError(`Failed to load targets: ${err.message || 'Unknown error'}`);
    }
  };

  // Handle rerunning a job with the selected target
  const rerunJobWithParams = async (selectedTargetId: string) => {
    try {
      setRerunning(true);
      // Get the original job details
      const originalJob = await getJob(targetIdReq, jobIdReq);

      // Create new job with the same parameters
      const jobData = {
        api_name: originalJob.api_name,
        parameters: originalJob.parameters,
        api_definition_version: originalJob.api_definition_version_id,
      } as any;

      const newJob = await createJob(selectedTargetId, jobData);
      // Navigate to the correct job details page using the new routing
      navigate(`/jobs/${selectedTargetId}/${newJob.id}`);
    } catch (error: any) {
      console.error('Error creating new job:', error);
      setError(`Failed to rerun job: ${error.message || 'Unknown error'}`);
      setRerunning(false);
    }
  };

  // Handle opening the resolve job dialog
  const handleResolveJob = () => {
    // Pre-fill the result with the current job result or the API definition's example_response
    if (job?.result) {
      // If job already has a result, use it
      setResolveResult(job.result);
    } else if (job?.api_name) {
      // If no result but we have the API name, try to get the example response
      const fetchApiExample = async () => {
        try {
          const apiDefinition: any = await getApiDefinitionDetails(job.api_name);
          if (apiDefinition?.response_example) {
            setResolveResult(apiDefinition.response_example);
          } else {
            setResolveResult({});
          }
        } catch (err: any) {
          console.error('Error fetching API example:', err);
          setError(`Failed to fetch API example: ${err.message}`);
        }
        setResolveDialogOpen(true);
      };

      fetchApiExample();
      return; // Don't open the dialog yet, fetchApiExample will do it
    } else {
      // Fallback to empty object
      setResolveResult({});
    }

    setResolveDialogOpen(true);
  };

  // Handle saving the resolved job
  const handleResolveConfirm = async () => {
    if (resolving) return;

    try {
      setResolving(true);

      // Call the API to resolve the job
      await resolveJob(targetIdReq, jobIdReq, resolveResult);

      // Close the dialog and refresh the job
      setResolveDialogOpen(false);
      await refreshJobStatus();
      await fetchJobLogs();

      setResolving(false);
    } catch (err: any) {
      console.error('Error resolving job:', err);
      setError(`Failed to resolve job: ${err.message || 'Unknown error'}`);
      setResolving(false);
    }
  };

  // Handle target selection from dialog
  const handleTargetSelect = async () => {
    if (!selectedTargetForRerun) {
      return;
    }

    setShowTargetDialog(false);
    await rerunJobWithParams(selectedTargetForRerun);
  };

  // Dialog for selecting a target when rerunning a job
  const renderTargetDialog = () => (
    <Dialog open={showTargetDialog} onClose={() => setShowTargetDialog(false)}>
      <DialogTitle>Select Target for Rerun</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 2 }}>
          Select a target to run this job on:
        </Typography>
        <FormControl fullWidth>
          <Select
            value={selectedTargetForRerun}
            onChange={e => setSelectedTargetForRerun(e.target.value as string)}
          >
            {availableTargets.map(target => (
              <MenuItem key={target.id} value={target.id || ''}>
                {target.name || target.id} - {target.type}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setShowTargetDialog(false)}>Cancel</Button>
        <Button onClick={handleTargetSelect} variant="contained">
          Rerun
        </Button>
      </DialogActions>
    </Dialog>
  );

  // Dialog for resolving a job (setting it to success with a custom result)
  const renderResolveDialog = () => (
    <Dialog
      open={resolveDialogOpen}
      onClose={() => !resolving && setResolveDialogOpen(false)}
      maxWidth="md"
      fullWidth
    >
      <DialogTitle>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <CheckCircleIcon color="success" sx={{ mr: 1 }} />
          Resolve Job
        </Box>
      </DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2 }}>
          This will mark the job as successful and resume the queue. Enter the result data below:
        </DialogContentText>
        <TextField
          label="Job Result (JSON)"
          multiline
          rows={10}
          value={
            typeof resolveResult === 'object'
              ? JSON.stringify(resolveResult, null, 2)
              : resolveResult
          }
          onChange={e => {
            try {
              // Attempt to parse as JSON
              setResolveResult(JSON.parse(e.target.value));
            } catch {
              // If not valid JSON, store as a string
              setResolveResult(e.target.value);
            }
          }}
          fullWidth
          variant="outlined"
          disabled={resolving}
          error={
            typeof resolveResult === 'string' &&
            resolveResult.trim() !== '' &&
            !isValidJson(resolveResult)
          }
          helperText={
            typeof resolveResult === 'string' &&
            resolveResult.trim() !== '' &&
            !isValidJson(resolveResult)
              ? 'Invalid JSON'
              : ''
          }
          sx={{ fontFamily: 'monospace' }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setResolveDialogOpen(false)} disabled={resolving}>
          Cancel
        </Button>
        <Button
          onClick={handleResolveConfirm}
          variant="contained"
          color="success"
          disabled={resolving || (typeof resolveResult === 'string' && !isValidJson(resolveResult))}
          startIcon={resolving ? <CircularProgress size={16} /> : <CheckCircleIcon />}
        >
          Resolve Job
        </Button>
      </DialogActions>
    </Dialog>
  );

  // Helper function to check if a string is valid JSON
  const isValidJson = (str: string) => {
    try {
      JSON.parse(str);
      return true;
    } catch {
      return false;
    }
  };

  // Function to handle canceling a job
  const handleCancelJob = useCallback(async () => {
    if (canceling || !job) return;
    setCanceling(true);
    setError(null);
    try {
      await cancelJob(targetIdReq, jobIdReq);
      await handleRefresh();
    } catch (err: any) {
      setError(err.message || 'Failed to cancel job.');
    } finally {
      setCanceling(false);
    }
  }, [targetIdReq, jobIdReq, job, canceling, handleRefresh]);

  // Function to handle resuming a job
  const handleResumeJob = useCallback(async () => {
    if (resuming || !job || !['paused', 'error'].includes((job.status || '').toLowerCase())) return;
    setResuming(true);
    setError(null);
    try {
      await resumeJob(targetIdReq, jobIdReq);
      await handleRefresh();
    } catch (err: any) {
      setError(err.message || 'Failed to resume job');
    } finally {
      setResuming(false);
    }
  }, [targetIdReq, jobIdReq, job, resuming, handleRefresh]);

  if (loading && !job) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error && !job) {
    return (
      <Alert severity="error" sx={{ mt: 2 }}>
        {error}
      </Alert>
    );
  }

  if (!job) {
    return (
      <Alert severity="warning" sx={{ mt: 2 }}>
        Job not found
      </Alert>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Sticky JobStatusCard at the top */}
      <Box
        sx={{
          position: 'sticky',
          top: 0,
          zIndex: 10,
          background: '#181818',
          borderBottom: '1px solid #333',
        }}
      >
        <JobStatusCard
          job={job}
          formatDate={formatDate}
          formatDuration={formatDuration}
          tokenUsage={{
            input: job?.total_input_tokens || 0,
            output: job?.total_output_tokens || 0,
          }}
          getStatusColor={getStatusColor}
          onRerun={handleRerun}
          onStop={handleInterruptJob}
          onCancel={handleCancelJob}
          onResolve={handleResolveJob}
          onResume={handleResumeJob}
          rerunning={rerunning}
          interrupting={interrupting}
          resolving={resolving}
          canceling={canceling}
          resuming={resuming}
          normalizedJobStatus={normalizedJobStatus}
        />
      </Box>

      {/* Error alert if present */}
      {error && (
        <Alert severity="error" sx={{ mb: 2, mt: 2 }}>
          {error}
        </Alert>
      )}

      {/* Main content below sticky bar */}
      <Box sx={{ mt: 2 }}>
        <JobTabs
          activeTab={activeTab}
          handleTabChange={handleTabChange}
          job={job || {}}
          regularLogs={logs}
          httpExchanges={httpExchanges}
          httpExchangesLoading={httpExchangesLoading}
          hasHttpExchanges={true}
        />
      </Box>

      {renderTargetDialog()}
      {renderResolveDialog()}
    </Box>
  );
};

export default JobDetails;
