import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  IconButton,
  Paper,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { deleteSession, getSessions, getTargets } from '../services/apiService';

const SessionList = () => {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [targets, setTargets] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [sessionToDelete, setSessionToDelete] = useState(null);
  const [hardDelete, setHardDelete] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [deleteInProgress, setDeleteInProgress] = useState(false);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);

  const fetchSessions = async () => {
    try {
      setLoading(true);
      const sessionsData = await getSessions(showArchived);
      setSessions(sessionsData);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching sessions:', err);
      setError('Failed to load sessions. Please try again later.');
      setLoading(false);
    }
  };

  const fetchTargets = async () => {
    try {
      const targetsData = await getTargets(true); // Include archived targets
      // Create a map of target_id to target name for quick lookup
      const targetsMap = {};
      targetsData.forEach(target => {
        targetsMap[target.id] = target.name || `Target ${target.id.substring(0, 8)}`;
      });
      setTargets(targetsMap);
    } catch (err) {
      console.error('Error fetching targets:', err);
    }
  };

  useEffect(() => {
    fetchSessions();
    fetchTargets();
  }, [showArchived]);

  const getStatusColor = status => {
    switch (status) {
      case 'COMPLETED':
        return 'success';
      case 'RUNNING':
        return 'info';
      case 'ERROR':
        return 'error';
      case 'PENDING':
        return 'warning';
      default:
        return 'default';
    }
  };

  const formatDate = dateString => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  const handleDeleteClick = (session, event) => {
    event.stopPropagation(); // Prevent row click navigation
    setSessionToDelete(session);
    setHardDelete(false);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!sessionToDelete) return;

    try {
      setDeleteInProgress(true);
      await deleteSession(sessionToDelete.id, hardDelete);

      // Refresh the sessions list
      await fetchSessions();

      setDeleteDialogOpen(false);
      setSessionToDelete(null);
    } catch (err) {
      console.error('Error deleting session:', err);
      // Keep the dialog open and show error
      setError(`Failed to delete session: ${err.message}`);
    } finally {
      setDeleteInProgress(false);
    }
  };

  const handleDeleteCancel = () => {
    if (deleteInProgress) return; // Prevent closing while delete is in progress
    setDeleteDialogOpen(false);
    setSessionToDelete(null);
  };

  const handleRowClick = session => {
    // Navigate to the target's detail page with the session pre-selected
    if (session.target_id) {
      navigate(`/targets/${session.target_id}?sessionId=${session.id}`);
    } else {
      // Fallback to old behavior if there's no target_id
      navigate(`/sessions/${session.id}`);
    }
  };

  const handleChangePage = (_event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = event => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return <Typography color="error">{error}</Typography>;
  }

  return (
    <Box sx={{ width: '100%' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h4">Sessions</Typography>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <FormControlLabel
            control={
              <Switch
                checked={showArchived}
                onChange={e => setShowArchived(e.target.checked)}
                color="primary"
              />
            }
            label="Show Archived"
            sx={{ mr: 2 }}
          />
          <Button
            component={RouterLink}
            to="/sessions/new"
            variant="contained"
            color="primary"
            startIcon={<AddIcon />}
          >
            New Session
          </Button>
        </Box>
      </Box>
      <Typography variant="body1" color="textSecondary" paragraph>
        Manage your API sessions
      </Typography>

      {sessions.length > 0 ? (
        <Paper sx={{ width: '100%', mb: 2 }}>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>ID</TableCell>
                  <TableCell>Target</TableCell>
                  <TableCell>State</TableCell>
                  <TableCell>Health</TableCell>
                  <TableCell>Created</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {[...sessions]
                  .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
                  .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
                  .map(session => (
                    <TableRow
                      hover
                      key={session.id}
                      onClick={() => handleRowClick(session)}
                      sx={{
                        cursor: 'pointer',
                        backgroundColor: session.is_archived ? 'rgba(0, 0, 0, 0.04)' : 'inherit',
                      }}
                    >
                      <TableCell>{session.id}</TableCell>
                      <TableCell>
                        {session.target_id ? (
                          <Tooltip title={`Target ID: ${session.target_id}`}>
                            <span>
                              {targets[session.target_id] || session.target_id.substring(0, 8)}
                            </span>
                          </Tooltip>
                        ) : (
                          <span>N/A</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {session.state && (
                          <Chip
                            label={session.state}
                            size="small"
                            color={getStatusColor(session.state)}
                          />
                        )}
                        {session.is_archived && (
                          <Tooltip title={`Reason: ${session.archive_reason || 'Not specified'}`}>
                            <Chip label="Archived" size="small" color="default" sx={{ ml: 1 }} />
                          </Tooltip>
                        )}
                      </TableCell>
                      <TableCell>
                        {session.container_status?.health ? (
                          <Tooltip
                            title={session.container_status.health.reason || 'No reason provided'}
                          >
                            <Chip
                              label={
                                session.container_status.health.healthy ? 'Healthy' : 'Unhealthy'
                              }
                              size="small"
                              color={session.container_status.health.healthy ? 'success' : 'error'}
                            />
                          </Tooltip>
                        ) : (
                          <Chip label="N/A" size="small" />
                        )}
                      </TableCell>
                      <TableCell>{formatDate(session.created_at)}</TableCell>
                      <TableCell align="right" sx={{ display: 'flex', gap: 2 }}>
                        {!session.is_archived && (
                          <Tooltip title="Archive Session">
                            <IconButton
                              size="small"
                              color="warning"
                              onClick={e => handleDeleteClick(session, e)}
                            >
                              <DeleteIcon />
                            </IconButton>
                          </Tooltip>
                        )}
                        <Tooltip title="Interactive Mode">
                          <IconButton
                            size="small"
                            color="primary"
                            onClick={e => {
                              e.stopPropagation();
                              navigate(`/sessions/${session.id}/interactive`);
                            }}
                          >
                            <SmartToyIcon />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            rowsPerPageOptions={[5, 10, 25]}
            component="div"
            count={sessions.length}
            rowsPerPage={rowsPerPage}
            page={page}
            onPageChange={handleChangePage}
            onRowsPerPageChange={handleChangeRowsPerPage}
          />
        </Paper>
      ) : (
        <Paper sx={{ p: 3, textAlign: 'center' }}>
          <Typography variant="h6" color="textSecondary">
            No Sessions Found
          </Typography>
          <Typography variant="body2" color="textSecondary" paragraph>
            Create a new session to get started
          </Typography>
          <Button
            component={RouterLink}
            to="/sessions/new"
            variant="outlined"
            startIcon={<AddIcon />}
          >
            Create Session
          </Button>
        </Paper>
      )}

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={handleDeleteCancel}>
        <DialogTitle>{hardDelete ? 'Permanently Delete Session?' : 'Archive Session?'}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {hardDelete
              ? 'This will permanently delete the session and cannot be undone. Are you sure you want to continue?'
              : 'This will archive the session. Archived sessions can be restored later. Do you want to continue?'}
          </DialogContentText>
          {deleteInProgress && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
              <CircularProgress size={24} />
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleDeleteCancel} color="primary" disabled={deleteInProgress}>
            Cancel
          </Button>
          <Button onClick={handleDeleteConfirm} color="error" autoFocus disabled={deleteInProgress}>
            {hardDelete ? 'Delete Permanently' : 'Archive'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default SessionList;
