import AddIcon from '@mui/icons-material/Add';
import BlockIcon from '@mui/icons-material/Block';
import ComputerIcon from '@mui/icons-material/Computer';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import UnarchiveIcon from '@mui/icons-material/Unarchive';
import {
  Alert,
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
  Grid,
  IconButton,
  Paper,
  Snackbar,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import type { Target } from '@/gen/endpoints';
import {
  deleteTarget,
  getJobs,
  getTarget,
  getTargets,
  unarchiveTarget,
  updateTarget,
} from '../services/apiService';
import ResolutionRecommendation from './ResolutionRecommendation';
import VPNConfigInputField from './VPNConfigInputField';

type TargetWithDetails = Target & {
  is_blocked: boolean | 'Error' | null | undefined;
  queued_tasks_count: number | 'Error';
};

const TargetList = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState<boolean>(false);
  const [targetToDelete, setTargetToDelete] = useState<Target | null>(null);
  const [hardDelete, setHardDelete] = useState<boolean>(false);
  const [showArchived, setShowArchived] = useState<boolean>(false);
  const [deleteInProgress, setDeleteInProgress] = useState<boolean>(false);
  const [editTargetDialogOpen, setEditTargetDialogOpen] = useState<boolean>(false);
  const [targetToEdit, setTargetToEdit] = useState<Target | null>(null);
  const [editInProgress, setEditInProgress] = useState<boolean>(false);
  const [editFormData, setEditFormData] = useState<any>({});
  const [validationErrors, setValidationErrors] = useState<any>({});
  const [page, setPage] = useState<number>(0);
  const [rowsPerPage, setRowsPerPage] = useState<number>(10);
  const [targetsWithDetails, setTargetsWithDetails] = useState<TargetWithDetails[]>([]);

  const fetchTargets = async () => {
    try {
      setLoading(true);
      const targetsData = await getTargets(showArchived);
      // setTargets(targetsData); // We will set targetsWithDetails instead

      // Fetch additional details for each target
      const detailedTargets: TargetWithDetails[] = await Promise.all(
        targetsData.map(async target => {
          try {
            const fullTargetDetails = await getTarget(target.id as string);
            const jobs = await getJobs(target.id as string);
            const queuedTasks = jobs.filter(job => job.status === 'queued').length;
            return {
              ...target,
              is_blocked:
                fullTargetDetails.blocking_jobs && fullTargetDetails.blocking_jobs.length > 0,
              queued_tasks_count: queuedTasks,
            } as TargetWithDetails;
          } catch (err) {
            console.error(`Error fetching details for target ${target.id}:`, err);
            // Return target with default/error state for additional fields
            return {
              ...target,
              is_blocked: 'Error', // Indicate error or unknown
              queued_tasks_count: 'Error', // Indicate error or unknown
            } as TargetWithDetails;
          }
        }),
      );
      setTargetsWithDetails(detailedTargets);
      setLoading(false);
    } catch (err: any) {
      console.error('Error fetching targets:', err);
      setError('Failed to load targets. Please try again later.');
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTargets();

    // Refresh data every 30 seconds
    const intervalId = setInterval(fetchTargets, 30000);

    return () => clearInterval(intervalId);
  }, [showArchived]);

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  const handleDeleteClick = (target: Target, event: any) => {
    event.stopPropagation(); // Prevent row click navigation
    setTargetToDelete(target);
    setDeleteDialogOpen(true);
    setHardDelete(false);
  };

  const handleDeleteConfirm = async () => {
    if (!targetToDelete) return;

    try {
      setDeleteInProgress(true);
      await deleteTarget(targetToDelete.id as string, hardDelete);
      // Refresh the targets list
      fetchTargets();
      // Close the dialog
      setDeleteDialogOpen(false);
      setTargetToDelete(null);
    } catch (err: any) {
      console.error('Error deleting target:', err);
      setError(`Failed to delete target: ${err.message}`);
    } finally {
      setDeleteInProgress(false);
    }
  };

  const handleDeleteCancel = () => {
    if (deleteInProgress) return; // Prevent closing while delete is in progress
    setDeleteDialogOpen(false);
    setTargetToDelete(null);
  };

  const handleUnarchiveClick = async (target: Target, event: any) => {
    event.stopPropagation(); // Prevent row click navigation
    try {
      await unarchiveTarget(target.id as string);
      // Refresh the targets list
      fetchTargets();
    } catch (err: any) {
      console.error('Error unarchiving target:', err);
      setError(`Failed to unarchive target: ${err.message}`);
    }
  };

  // TODO: Potentially move this into a seperate component since it's mostly redudant with CreateTarget.js
  const handleEditClick = async (target: Target, event: any) => {
    event.stopPropagation(); // Prevent row click navigation
    try {
      const targetDetails = await getTarget(target.id as string);
      setTargetToEdit(targetDetails);
      // VPN fields are now stored separately in the database

      setEditFormData({
        name: targetDetails.name || '',
        type: targetDetails.type || '',
        host: targetDetails.host || '',
        port: targetDetails.port || null,
        username: targetDetails.username || '',
        password: targetDetails.password || '',
        width: targetDetails.width || 1024,
        height: targetDetails.height || 768,
        vpn_config: targetDetails.vpn_config || '',
        vpn_username: targetDetails.vpn_username || '',
        vpn_password: targetDetails.vpn_password || '',
        rdp_params: targetDetails.rdp_params || '',
      });
      setEditTargetDialogOpen(true);
    } catch (err: any) {
      console.error('Error fetching target details:', err);
      setError(`Failed to fetch target details: ${err.message}`);
    }
  };

  const handleRowClick = (target: Target) => {
    navigate(`/targets/${target.id}`);
  };

  const handleChangePage = (_event: any, newPage: number) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event: any) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleEditCancel = () => {
    if (editInProgress) return; // Prevent closing while edit is in progress
    setEditTargetDialogOpen(false);
    setTargetToEdit(null);
    setEditFormData({});
    setValidationErrors({});
  };

  const handleEditChange = (e: any) => {
    const { name, value } = e.target;
    setEditFormData((prev: any) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleEditPortChange = (e: any) => {
    const value = e.target.value;
    if (value === '') {
      setEditFormData((prev: any) => ({
        ...prev,
        port: null,
      }));
    } else {
      const portValue = parseInt(value, 10);
      if (!Number.isNaN(portValue)) {
        setEditFormData((prev: any) => ({
          ...prev,
          port: portValue,
        }));
      }
    }
  };

  const handleEditResolutionChange = (e: any) => {
    const { name, value } = e.target;
    const numValue = parseInt(value, 10);
    if (!Number.isNaN(numValue)) {
      setEditFormData((prev: any) => ({
        ...prev,
        [name]: numValue,
      }));
    }
  };

  const handleEditRecommendedResolutionClick = ({
    width,
    height,
  }: {
    width: number;
    height: number;
  }) => {
    setEditFormData((prev: any) => ({ ...prev, width, height }));
  };

  const validateEditForm = () => {
    const errors: any = {};

    if (!editFormData.name.trim()) {
      errors.name = 'Name is required';
    }

    if (!editFormData.host.trim()) {
      errors.host = 'Host is required';
    }

    if (
      editFormData.port !== null &&
      (Number.isNaN(editFormData.port) || editFormData.port < 1 || editFormData.port > 65535)
    ) {
      errors.port = 'Port must be a valid number between 1 and 65535';
    }

    if (!editFormData.width || Number.isNaN(editFormData.width) || editFormData.width < 1) {
      errors.width = 'Width must be a positive number';
    }

    if (!editFormData.height || Number.isNaN(editFormData.height) || editFormData.height < 1) {
      errors.height = 'Height must be a positive number';
    }

    // Validate OpenVPN fields when target type is rdp+openvpn
    if (editFormData.type === 'rdp+openvpn') {
      if (!editFormData.vpn_username || !editFormData.vpn_username.trim()) {
        errors.vpn_username = 'OpenVPN username is required';
      }
      if (!editFormData.vpn_password || !editFormData.vpn_password.trim()) {
        errors.vpn_password = 'OpenVPN password is required';
      }
      if (!editFormData.vpn_config || !editFormData.vpn_config.trim()) {
        errors.vpn_config = 'OpenVPN config is required';
      }
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleEditConfirm = async () => {
    if (!targetToEdit) return;

    if (!validateEditForm()) {
      return;
    }

    try {
      setEditInProgress(true);

      // Prepare data for submission
      const submissionData = { ...editFormData } as any;

      // No need to concatenate VPN fields anymore - they are sent as separate fields

      await updateTarget(targetToEdit.id as string, submissionData);

      // Refresh the targets list
      fetchTargets();

      // Close the dialog
      setEditTargetDialogOpen(false);
      setTargetToEdit(null);
      setEditFormData({});

      // Show notification that sessions need to be restarted
      setNotificationOpen(true);
    } catch (err: any) {
      console.error('Error updating target:', err);
      setError(`Failed to update target: ${err.message}`);
    } finally {
      setEditInProgress(false);
    }
  };

  const [notificationOpen, setNotificationOpen] = useState<boolean>(false);

  const handleNotificationClose = () => {
    setNotificationOpen(false);
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
      <Box sx={{ mt: 2 }}>
        <Typography color="error" variant="body1">
          {error}
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ width: '100%' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h4">Targets</Typography>
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
            to="/targets/new"
            variant="contained"
            color="primary"
            startIcon={<AddIcon />}
          >
            New Target
          </Button>
        </Box>
      </Box>
      <Typography variant="body1" color="textSecondary" paragraph>
        Manage your targets for API sessions
      </Typography>
      {targetsWithDetails.length === 0 ? (
        <Paper sx={{ p: 3, textAlign: 'center' }}>
          <ComputerIcon sx={{ fontSize: 60, color: 'text.secondary', mb: 2 }} />
          <Typography variant="h6" color="text.secondary">
            No Targets Found
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Create a new target to get started
          </Typography>
          <Button
            component={RouterLink}
            to="/targets/new"
            variant="outlined"
            startIcon={<AddIcon />}
          >
            Create Target
          </Button>
        </Paper>
      ) : (
        <Paper sx={{ width: '100%', mb: 2 }}>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Host</TableCell>
                  <TableCell>Blocked</TableCell>
                  <TableCell>Queued Tasks</TableCell>
                  <TableCell>Created</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {targetsWithDetails
                  .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
                  .map(target => (
                    <TableRow
                      hover
                      key={target.id}
                      onClick={() => handleRowClick(target)}
                      sx={{
                        cursor: 'pointer',
                        backgroundColor: target.is_archived ? 'rgba(0, 0, 0, 0.04)' : 'inherit',
                      }}
                    >
                      <TableCell>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          {target.name || `Target ${String(target.id).substring(0, 8)}`}
                          {target.is_archived && (
                            <Tooltip title="Archived">
                              <Chip label="Archived" size="small" color="default" sx={{ ml: 1 }} />
                            </Tooltip>
                          )}
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={target.type}
                          color="primary"
                          size="small"
                          sx={{ textTransform: 'capitalize' }}
                        />
                      </TableCell>
                      <TableCell>
                        {target.host}
                        {target.port ? `:${target.port}` : ''}
                      </TableCell>
                      <TableCell>
                        {target.is_blocked === 'Error' ? (
                          <Tooltip title="Error fetching status">
                            <Chip label="Error" color="default" size="small" />
                          </Tooltip>
                        ) : target.is_blocked ? (
                          <Tooltip title="Target is blocked by one or more jobs">
                            <Chip icon={<BlockIcon />} label="Blocked" color="error" size="small" />
                          </Tooltip>
                        ) : (
                          <Chip label="No" color="success" size="small" />
                        )}
                      </TableCell>
                      <TableCell>
                        {target.queued_tasks_count === 'Error' ? (
                          <Tooltip title="Error fetching queue count">
                            <Chip label="Error" color="default" size="small" />
                          </Tooltip>
                        ) : (
                          <Chip
                            icon={<HourglassEmptyIcon />}
                            label={target.queued_tasks_count}
                            color={
                              typeof target.queued_tasks_count === 'number' &&
                              target.queued_tasks_count > 0
                                ? 'warning'
                                : 'default'
                            }
                            size="small"
                          />
                        )}
                      </TableCell>
                      <TableCell>{formatDate(target.created_at)}</TableCell>
                      <TableCell align="right">
                        {target.is_archived ? (
                          <Tooltip title="Unarchive Target">
                            <IconButton
                              size="small"
                              color="primary"
                              onClick={e => handleUnarchiveClick(target, e)}
                            >
                              <UnarchiveIcon />
                            </IconButton>
                          </Tooltip>
                        ) : (
                          <>
                            <Tooltip title="Edit Target">
                              <IconButton
                                size="small"
                                color="primary"
                                onClick={e => handleEditClick(target, e)}
                                sx={{ mr: 1 }}
                              >
                                <EditIcon />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Archive Target">
                              <IconButton
                                size="small"
                                color="warning"
                                onClick={e => handleDeleteClick(target, e)}
                              >
                                <DeleteIcon />
                              </IconButton>
                            </Tooltip>
                          </>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            rowsPerPageOptions={[5, 10, 25]}
            component="div"
            count={targetsWithDetails.length}
            rowsPerPage={rowsPerPage}
            page={page}
            onPageChange={handleChangePage}
            onRowsPerPageChange={handleChangeRowsPerPage}
          />
        </Paper>
      )}
      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={handleDeleteCancel}>
        <DialogTitle>{hardDelete ? 'Permanently Delete Target?' : 'Archive Target?'}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {hardDelete
              ? 'This will permanently delete the target and cannot be undone. Are you sure you want to continue?'
              : 'This will archive the target. Archived targets can be restored later. Do you want to continue?'}
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
      {/* Edit Target Dialog */}
      <Dialog open={editTargetDialogOpen} onClose={handleEditCancel} maxWidth="md" fullWidth>
        <DialogTitle>Edit Target</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            Edit target details. Note that any changes will require restarting sessions that use
            this target.
          </DialogContentText>

          <Grid container spacing={3}>
            <Grid
              size={{
                xs: 12,
                md: 6,
              }}
            >
              <TextField
                fullWidth
                label="Target Name"
                name="name"
                value={editFormData.name || ''}
                onChange={handleEditChange}
                error={!!validationErrors.name}
                helperText={validationErrors.name}
                disabled={editInProgress}
                required
                margin="normal"
              />
            </Grid>

            <Grid
              size={{
                xs: 12,
                md: 8,
              }}
            >
              <TextField
                fullWidth
                label="Host"
                name="host"
                value={editFormData.host || ''}
                onChange={handleEditChange}
                error={!!validationErrors.host}
                helperText={validationErrors.host}
                disabled={editInProgress}
                required
                margin="normal"
                placeholder="hostname or IP address"
              />
            </Grid>

            <Grid
              size={{
                xs: 12,
                md: 4,
              }}
            >
              <TextField
                fullWidth
                label="Port"
                name="port"
                type="number"
                value={editFormData.port === null ? '' : editFormData.port}
                onChange={handleEditPortChange}
                error={!!validationErrors.port}
                helperText={validationErrors.port}
                disabled={editInProgress}
                placeholder="Optional"
                margin="normal"
              />
            </Grid>

            <Grid size={12}>
              <VPNConfigInputField
                targetData={editFormData}
                validationErrors={validationErrors}
                loading={editInProgress}
                handleChange={handleEditChange}
              />
            </Grid>

            <Grid
              size={{
                xs: 12,
                sm: 6,
              }}
            >
              <TextField
                fullWidth
                variant="outlined"
                label="Username (optional)"
                name="username"
                value={editFormData.username || ''}
                onChange={handleEditChange}
                error={!!validationErrors.username}
                helperText={validationErrors.username}
                margin="normal"
              />
            </Grid>

            <Grid
              size={{
                xs: 12,
                md: 6,
              }}
            >
              <TextField
                fullWidth
                label="Password"
                name="password"
                type="password"
                value={editFormData.password || ''}
                onChange={handleEditChange}
                error={!!validationErrors.password}
                helperText={validationErrors.password || 'Leave empty to keep existing password'}
                disabled={editInProgress}
                margin="normal"
              />
            </Grid>

            <Grid
              size={{
                xs: 12,
                md: 6,
              }}
            >
              <TextField
                fullWidth
                label="Width (px)"
                name="width"
                type="number"
                value={editFormData.width || ''}
                onChange={handleEditResolutionChange}
                error={!!validationErrors.width}
                helperText={validationErrors.width}
                disabled={editInProgress}
                required
                margin="normal"
                InputProps={{ inputProps: { min: 1 } }}
              />
            </Grid>

            <Grid
              size={{
                xs: 12,
                md: 6,
              }}
            >
              <TextField
                fullWidth
                label="Height (px)"
                name="height"
                type="number"
                value={editFormData.height || ''}
                onChange={handleEditResolutionChange}
                error={!!validationErrors.height}
                helperText={validationErrors.height}
                disabled={editInProgress}
                required
                margin="normal"
                InputProps={{ inputProps: { min: 1 } }}
              />
            </Grid>

            {/* RDP customization options */}
            {(editFormData.type?.startsWith('rdp') || editFormData.type?.includes('rdp')) && (
              <Grid size={12}>
                <TextField
                  fullWidth
                  multiline
                  minRows={2}
                  label="FreeRDP parameters"
                  name="rdp_params"
                  value={editFormData.rdp_params || ''}
                  onChange={handleEditChange}
                  disabled={editInProgress}
                  placeholder="Defaults: /f +auto-reconnect +clipboard /cert:ignore. You can add or override here. Username (/u), Password (/p) and Host (/v) are always included."
                  margin="normal"
                />
              </Grid>
            )}

            {/* Resolution recommendation warning */}
            <Grid size={12}>
              <ResolutionRecommendation
                width={editFormData.width || 1024}
                height={editFormData.height || 768}
                onRecommendedResolutionClick={handleEditRecommendedResolutionClick}
                disabled={editInProgress}
              />
            </Grid>
          </Grid>

          {editInProgress && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
              <CircularProgress size={24} />
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleEditCancel} color="primary" disabled={editInProgress}>
            Cancel
          </Button>
          <Button
            onClick={handleEditConfirm}
            color="primary"
            variant="contained"
            disabled={editInProgress}
          >
            Save Changes
          </Button>
        </DialogActions>
      </Dialog>
      {/* Notification for target updates */}
      <Snackbar
        open={notificationOpen}
        autoHideDuration={8000}
        onClose={handleNotificationClose}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={handleNotificationClose} severity="warning" sx={{ width: '100%' }}>
          Target updated successfully. Any active sessions using this target will need to be
          restarted for changes to take effect.
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default TargetList;
