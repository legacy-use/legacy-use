import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import DeleteIcon from '@mui/icons-material/Delete';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import RefreshIcon from '@mui/icons-material/Refresh';
import VisibilityIcon from '@mui/icons-material/Visibility';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Collapse,
  Grid,
  IconButton,
  Paper,
  Snackbar,
  Tooltip,
  Typography,
} from '@mui/material';
import { useState } from 'react';
import ContainerLogsModal from './ContainerLogsModal';

const SessionDetailsCard = ({
  selectedSession,
  showContainerDetails,
  setShowContainerDetails,
  fetchContainerStatus,
  handleDeleteClick,
  handleCopyToClipboard,
  copySnackbarOpen,
  handleCopySnackbarClose,
  getDockerImageName,
  getContainerName,
  getStateBadgeColor,
}) => {
  const [logsModalOpen, setLogsModalOpen] = useState(false);
  if (!selectedSession) return null;
  return (
    <>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <Typography variant="h6">Session {selectedSession.id.substring(0, 8)}</Typography>
          <Tooltip title={selectedSession.id} placement="top">
            <IconButton
              size="small"
              sx={{ ml: 1 }}
              onClick={e => handleCopyToClipboard(selectedSession.id, e)}
            >
              <ContentCopyIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          {selectedSession.is_archived && (
            <Chip label="Archived" size="small" color="default" sx={{ ml: 2 }} />
          )}
        </Box>
        <Button
          variant="contained"
          color="error"
          startIcon={<DeleteIcon />}
          onClick={handleDeleteClick}
        >
          {selectedSession.is_archived ? 'Permanently Delete' : 'Archive Session'}
        </Button>
      </Box>
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2}>
            {selectedSession.is_archived && (
              <Grid
                size={{
                  xs: 12,
                  sm: 6,
                }}
              >
                <Typography variant="body2" color="textSecondary">
                  Archive Reason: {selectedSession.archive_reason || 'Not specified'}
                </Typography>
              </Grid>
            )}
            {selectedSession.container_status && (
              <>
                <Grid size={12}>
                  <Box display="flex" alignItems="center">
                    <Typography variant="body2" color="textSecondary" sx={{ mr: 1 }}>
                      Container Status:{' '}
                      {selectedSession.container_status.state?.Status || 'Unknown'}
                    </Typography>
                    <IconButton
                      size="small"
                      onClick={fetchContainerStatus}
                      title="Refresh container status"
                    >
                      <RefreshIcon fontSize="small" />
                    </IconButton>
                    <IconButton
                      size="small"
                      onClick={() => setLogsModalOpen(true)}
                      title="View container logs"
                    >
                      <VisibilityIcon fontSize="small" />
                    </IconButton>
                    <IconButton
                      size="small"
                      onClick={() => setShowContainerDetails(!showContainerDetails)}
                      title={showContainerDetails ? 'Hide details' : 'Show details'}
                    >
                      {showContainerDetails ? (
                        <ExpandLessIcon fontSize="small" />
                      ) : (
                        <ExpandMoreIcon fontSize="small" />
                      )}
                    </IconButton>
                  </Box>
                </Grid>
                <Grid size={12}>
                  <Collapse in={showContainerDetails}>
                    <Paper variant="outlined" sx={{ p: 2, mt: 1 }}>
                      <Typography variant="subtitle2" gutterBottom>
                        Container Details
                      </Typography>
                      {selectedSession.container_id && (
                        <Typography variant="body2" color="textSecondary">
                          Container ID: {selectedSession.container_id}
                        </Typography>
                      )}
                      <Typography variant="body2" color="textSecondary">
                        Docker Image: {getDockerImageName()}
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        Container Name: {getContainerName(selectedSession.id)}
                      </Typography>
                      {selectedSession.container_ip && (
                        <Typography variant="body2" color="textSecondary">
                          Container IP: {selectedSession.container_ip}
                        </Typography>
                      )}
                      {selectedSession.mapped_port && (
                        <Typography variant="body2" color="textSecondary">
                          Mapped Port: {selectedSession.mapped_port}
                        </Typography>
                      )}
                      {selectedSession.container_status.state && (
                        <Box>
                          <Typography variant="body2" color="textSecondary">
                            Running: {selectedSession.container_status.state.Running ? 'Yes' : 'No'}
                          </Typography>
                          <Typography variant="body2" color="textSecondary">
                            Started At: {selectedSession.container_status.state.StartedAt || 'N/A'}
                          </Typography>
                          {selectedSession.container_status.state.Error && (
                            <Typography variant="body2" color="error">
                              Error: {selectedSession.container_status.state.Error}
                            </Typography>
                          )}
                        </Box>
                      )}
                      {selectedSession.container_status.health && (
                        <Box mt={1}>
                          <Box display="flex" alignItems="center">
                            <Typography variant="subtitle2" sx={{ mr: 1 }}>
                              Health:
                            </Typography>
                            <Typography variant="body2" color="textSecondary">
                              {selectedSession.container_status.health.healthy ? 'Yes' : 'No'} (
                              {selectedSession.container_status.health.reason}) <br />
                              Last Check:{' '}
                              {new Date(
                                selectedSession.container_status.health.timestamp,
                              ).toLocaleString()}
                            </Typography>
                          </Box>
                          {selectedSession.container_status.health.raw_response && (
                            <Typography
                              variant="body2"
                              color="textSecondary"
                              sx={{ mt: 1, fontFamily: 'monospace' }}
                            >
                              Response:{' '}
                              {JSON.stringify(
                                selectedSession.container_status.health.raw_response,
                                null,
                                2,
                              )}
                            </Typography>
                          )}
                          {selectedSession.container_status.health.error && (
                            <Typography variant="body2" color="error" sx={{ mt: 1 }}>
                              Error: {selectedSession.container_status.health.error}
                            </Typography>
                          )}
                        </Box>
                      )}
                      {selectedSession.container_status.load_average &&
                        !selectedSession.container_status.load_average.error && (
                          <Box mt={1}>
                            <Typography variant="subtitle2" gutterBottom>
                              Load Average
                            </Typography>
                            <Typography variant="body2" color="textSecondary">
                              1 min: {selectedSession.container_status.load_average.load_1} | 5 min:{' '}
                              {selectedSession.container_status.load_average.load_5} | 15 min:{' '}
                              {selectedSession.container_status.load_average.load_15}
                            </Typography>
                          </Box>
                        )}
                      {selectedSession.container_status.network_settings?.Ports && (
                        <Box mt={1}>
                          <Typography variant="subtitle2" gutterBottom>
                            Port Mappings
                          </Typography>
                          {Object.entries(
                            selectedSession.container_status.network_settings.Ports,
                          ).map(([port, mapping]) => (
                            <Typography key={port} variant="body2" color="textSecondary">
                              {port} → {mapping ? mapping[0]?.HostPort : 'Not mapped'}
                            </Typography>
                          ))}
                        </Box>
                      )}
                    </Paper>
                  </Collapse>
                </Grid>
              </>
            )}
            <Grid
              size={{
                xs: 12,
                sm: 6,
              }}
            >
              <Typography variant="body2" color="textSecondary">
                Status: {selectedSession.status}
              </Typography>
            </Grid>
            <Grid
              size={{
                xs: 12,
                sm: 6,
              }}
            >
              <Box display="flex" alignItems="center">
                <Typography variant="body2" color="textSecondary">
                  State:
                </Typography>
                <Chip
                  label={selectedSession.state || 'unknown'}
                  size="small"
                  color={getStateBadgeColor(selectedSession.state)}
                  sx={{ ml: 1, fontWeight: 'bold' }}
                />
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>
      <Snackbar
        open={copySnackbarOpen}
        autoHideDuration={3000}
        onClose={handleCopySnackbarClose}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert onClose={handleCopySnackbarClose} severity="success" sx={{ width: '100%' }}>
          Session ID copied to clipboard
        </Alert>
      </Snackbar>
      <ContainerLogsModal
        open={logsModalOpen}
        onClose={() => setLogsModalOpen(false)}
        sessionId={selectedSession.id}
        sessionName={selectedSession.name}
      />
    </>
  );
};

export default SessionDetailsCard;
