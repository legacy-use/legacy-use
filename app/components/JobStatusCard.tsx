import CancelIcon from '@mui/icons-material/Cancel';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import ReplayIcon from '@mui/icons-material/Replay';
import StopIcon from '@mui/icons-material/Stop';
import {
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  IconButton,
  Tooltip,
  Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getApiDefinitionVersion } from '../services/apiService';

const JobStatusCard = ({
  job,
  formatDate,
  formatDuration,
  getStatusColor,
  tokenUsage,
  onRerun,
  onStop,
  onCancel,
  onResolve,
  onResume,
  rerunning,
  interrupting,
  resolving,
  canceling,
  resuming,
  normalizedJobStatus,
}) => {
  const [versionInfo, setVersionInfo] = useState(null);
  const [loadingVersion, setLoadingVersion] = useState(false);

  // Fetch version information if available
  useEffect(() => {
    const fetchVersionInfo = async () => {
      if (job?.api_definition_version_id && job.api_name && !versionInfo) {
        try {
          setLoadingVersion(true);
          const version = await getApiDefinitionVersion(
            job.api_name,
            job.api_definition_version_id,
          );
          setVersionInfo(version);
          setLoadingVersion(false);
        } catch (err) {
          console.error('Error fetching version info:', err);
          setLoadingVersion(false);
        }
      }
    };

    fetchVersionInfo();
  }, [job?.api_definition_version_id, job?.api_name, versionInfo]);

  if (!job) return null;

  // Check if the job can be interrupted/canceled/resumed
  const isInterruptible =
    normalizedJobStatus === 'running' ||
    normalizedJobStatus === 'queued' ||
    normalizedJobStatus === 'pending';
  const isCancelable = normalizedJobStatus === 'queued' || normalizedJobStatus === 'pending';
  const isResumable = normalizedJobStatus === 'paused' || normalizedJobStatus === 'error';
  const isResolvable = normalizedJobStatus === 'paused' || normalizedJobStatus === 'error';

  const renderDurationAndTokens = () => {
    const duration = formatDuration(job.created_at, job.completed_at);
    const tokens = tokenUsage
      ? `${tokenUsage.input.toLocaleString()} in / ${tokenUsage.output.toLocaleString()} out`
      : 'N/A';
    const isRunning = normalizedJobStatus === 'running';

    // Calculate costs if token usage is available
    let costInfo = null;
    if (tokenUsage) {
      const inputCost = (tokenUsage.input / 1000000) * 3; // $3 per 1M input tokens
      const outputCost = (tokenUsage.output / 1000000) * 15; // $15 per 1M output tokens
      const totalCost = inputCost + outputCost;
      costInfo = `($${totalCost.toFixed(3)})`;
    }

    return (
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="body2" color="textSecondary">
            Duration: {duration}
          </Typography>
          {isRunning && <CircularProgress size={12} sx={{ color: 'info.main' }} />}
        </Box>
        <Typography variant="body2" color="textSecondary">
          •
        </Typography>
        <Typography variant="body2" color="textSecondary">
          Tokens: {tokens} {costInfo}
        </Typography>
      </Box>
    );
  };

  return (
    <Card sx={{ boxShadow: 2 }}>
      <CardContent sx={{ p: 2, pb: '10px!important' }}>
        {/* First line: Name, status ribbon, and action buttons */}
        <Box
          sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}
        >
          {/* Left side: Name and status */}
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              minWidth: 0,
              maxWidth: '60%', // Prevent left side from taking all space
              flexShrink: 1,
            }}
          >
            <Typography
              variant="h5"
              sx={{
                mr: 2,
                fontWeight: 600,
                textOverflow: 'ellipsis',
                overflow: 'hidden',
                whiteSpace: 'nowrap',
                minWidth: 0,
              }}
            >
              {job.api_name}
            </Typography>
            <Chip label={job.status} color={getStatusColor(job.status)} size="small" />
          </Box>

          {/* Right side: Action buttons */}
          <Box
            sx={{
              display: 'flex',
              gap: 1,
              flexShrink: 0,
              minWidth: 'fit-content',
            }}
          >
            {/* Resume Action */}
            <Tooltip title={isResumable ? 'Resume Job' : 'Resume not available'}>
              <span>
                <IconButton
                  size="small"
                  onClick={onResume}
                  disabled={!isResumable || resuming || interrupting || resolving || canceling}
                  sx={{
                    color: isResumable ? 'inherit' : 'action.disabled',
                    '&:hover': {
                      color: isResumable ? 'primary.main' : 'action.disabled',
                    },
                  }}
                >
                  {resuming ? <CircularProgress size={20} /> : <PlayArrowIcon fontSize="small" />}
                </IconButton>
              </span>
            </Tooltip>

            {/* Rerun Action */}
            <Tooltip title="Rerun Job">
              <span>
                <IconButton
                  size="small"
                  onClick={onRerun}
                  disabled={rerunning || interrupting || resolving || canceling || resuming}
                >
                  {rerunning ? <CircularProgress size={20} /> : <ReplayIcon fontSize="small" />}
                </IconButton>
              </span>
            </Tooltip>

            {/* Interrupt Action */}
            <Tooltip title={isInterruptible ? 'Interrupt Job' : 'Interrupt not available'}>
              <span>
                <IconButton
                  size="small"
                  onClick={onStop}
                  disabled={!isInterruptible || interrupting || resolving || canceling || resuming}
                  sx={{
                    color: isInterruptible ? 'inherit' : 'action.disabled',
                    '&:hover': {
                      color: isInterruptible ? 'primary.main' : 'action.disabled',
                    },
                  }}
                >
                  {interrupting ? <CircularProgress size={20} /> : <StopIcon fontSize="small" />}
                </IconButton>
              </span>
            </Tooltip>

            {/* Cancel Action */}
            <Tooltip title={isCancelable ? 'Cancel Job' : 'Cancel not available'}>
              <span>
                <IconButton
                  size="small"
                  onClick={onCancel}
                  disabled={!isCancelable || canceling || interrupting || resolving || resuming}
                  sx={{
                    color: isCancelable ? 'inherit' : 'action.disabled',
                    '&:hover': {
                      color: isCancelable ? 'primary.main' : 'action.disabled',
                    },
                  }}
                >
                  {canceling ? <CircularProgress size={20} /> : <CancelIcon fontSize="small" />}
                </IconButton>
              </span>
            </Tooltip>

            {/* Resolve Action */}
            <Tooltip title={isResolvable ? 'Resolve Job' : 'Resolve not available'}>
              <span>
                <IconButton
                  size="small"
                  onClick={onResolve}
                  disabled={!isResolvable || resolving || interrupting || canceling || resuming}
                  sx={{
                    color: isResolvable ? 'inherit' : 'action.disabled',
                    '&:hover': {
                      color: isResolvable ? 'primary.main' : 'action.disabled',
                    },
                  }}
                >
                  {resolving ? (
                    <CircularProgress size={20} />
                  ) : (
                    <CheckCircleIcon fontSize="small" />
                  )}
                </IconButton>
              </span>
            </Tooltip>
          </Box>
        </Box>
        {/* Second line: Essential information */}
        <Grid container spacing={0.5} sx={{ mb: 0.5, mt: 0 }} alignItems="center">
          <Grid>
            <Typography variant="body2" color="textSecondary">
              <strong>Created:</strong> {formatDate(job.created_at)}
            </Typography>
          </Grid>
          <Grid>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {renderDurationAndTokens()}
            </Box>
          </Grid>
          {/* API Version info and link */}
          {versionInfo ? (
            <Grid sx={{ display: 'flex', alignItems: 'center' }}>
              <Typography
                variant="body2"
                color="textSecondary"
                sx={{ display: 'flex', alignItems: 'center' }}
              >
                <strong>API Version:</strong> {versionInfo.version_number}
                {versionInfo.is_active && (
                  <Chip
                    label="Active"
                    color="primary"
                    size="small"
                    sx={{ ml: 1, height: 18, fontSize: '0.7rem' }}
                  />
                )}
                {/* API Version link as icon */}
                <Tooltip title="View API Version">
                  <IconButton
                    component={Link}
                    to={`/apis/${job.api_name}/edit?version=${job.api_definition_version_id}`}
                    size="small"
                    sx={{ ml: 1, p: 0.5 }}
                  >
                    <OpenInNewIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Typography>
            </Grid>
          ) : loadingVersion ? (
            <Grid>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Typography variant="body2" color="textSecondary" sx={{ mr: 1 }}>
                  <strong>API Version:</strong>
                </Typography>
                <CircularProgress size={14} />
              </Box>
            </Grid>
          ) : null}
        </Grid>
        {/* Result section */}
        {job.result && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Result
            </Typography>
            <Box
              sx={{
                backgroundColor: '#2d2d2d',
                p: 1.5,
                fontFamily: 'monospace',
                fontSize: '0.9rem',
                maxHeight: '220px',
                overflowY: 'auto',
              }}
            >
              <pre style={{ margin: 0 }}>{JSON.stringify(job.result, null, 2)}</pre>
            </Box>
          </Box>
        )}
        {/* Job details for reference */}
        <Box sx={{ mt: 2, display: 'none' }}>
          <Typography variant="body2" color="textSecondary">
            <strong>Job ID:</strong> {job.id}
          </Typography>
          <Typography variant="body2" color="textSecondary">
            <strong>Session ID:</strong> {job.session_id}
          </Typography>
        </Box>
      </CardContent>
    </Card>
  );
};

export default JobStatusCard;
