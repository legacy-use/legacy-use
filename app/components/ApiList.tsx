import {
  Add as AddIcon,
  Archive as ArchiveIcon,
  Download as DownloadIcon,
  Edit as EditIcon,
  FileCopy as FileCopyIcon,
  PlayArrow as PlayArrowIcon,
  Settings as SettingsIcon,
  Unarchive as UnarchiveIcon,
  Upload as UploadIcon,
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
} from '@mui/icons-material';

import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Collapse,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SessionContext } from '../App';
import {
  archiveApiDefinition,
  createJob,
  exportApiDefinition,
  getApiDefinitions,
  getTargets,
  importApiDefinition,
  unarchiveApiDefinition,
} from '../services/apiService';
import AddApiDialog from './AddApiDialog';
import DuplicateApiDialog from './DuplicateApiDialog';

const ApiList = () => {
  const navigate = useNavigate();
  const { selectedSessionId, setSelectedSessionId } = useContext(SessionContext);
  const [apis, setApis] = useState([]);
  const [targets, setTargets] = useState([]);
  const [selectedTarget, setSelectedTarget] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [paramValues, setParamValues] = useState({});
  const [executingApi, setExecutingApi] = useState(null);
  const [executionResult, setExecutionResult] = useState({});
  const [expandedApis, setExpandedApis] = useState({});
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const fileInputRef = useRef(null);
  const [addApiDialogOpen, setAddApiDialogOpen] = useState(false);
  const [duplicateApiDialogOpen, setDuplicateApiDialogOpen] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [duplicateApiName, setDuplicateApiName] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [apisData, targetsData] = await Promise.all([
        getApiDefinitions(showArchived),
        getTargets(),
      ]);

      setApis(apisData);
      setTargets(targetsData);

      // Check for target and session parameters in URL
      const params = new URLSearchParams(window.location.search);
      const targetParam = params.get('targetId') || params.get('target');
      const sessionParam = params.get('sessionId');

      // Set selected target if available
      if (targetsData.length > 0) {
        // If target parameter exists and is valid, use it
        if (targetParam && targetsData.some(t => t.id === targetParam)) {
          setSelectedTarget(targetParam);
          setSelectedSessionId(sessionParam || targetParam); // Use sessionId if available, otherwise use targetId
        } else if (selectedSessionId) {
          // If there's a session in context, use it
          setSelectedTarget(selectedSessionId);
        } else {
          // Otherwise, don't pre-select any target
          setSelectedTarget('');
          setSelectedSessionId('');
        }
      }

      // Initialize parameter values
      const initialParamValues = {};
      const initialExpandedState = {};
      apisData.forEach(api => {
        const apiParams = {};
        if (api.parameters) {
          api.parameters.forEach(param => {
            apiParams[param.name] = param.default || '';
          });
        }
        initialParamValues[api.name] = apiParams;
        initialExpandedState[api.name] = false;
      });
      setParamValues(initialParamValues);
      setExpandedApis(initialExpandedState);

      setLoading(false);
    } catch (err) {
      console.error('Error fetching API data:', err);
      setError('Failed to load API data. Please try again later.');
      setLoading(false);
    }
  }, [selectedSessionId, setSelectedSessionId, showArchived]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Handle target change
  const handleTargetChange = event => {
    const newTargetId = event.target.value;
    setSelectedTarget(newTargetId);
    setSelectedSessionId(newTargetId); // Keep for compatibility with session context

    // Update URL with target parameter if a target is selected
    const url = new URL(window.location.href);
    if (newTargetId) {
      url.searchParams.set('target', newTargetId);
    } else {
      url.searchParams.delete('target');
    }
    window.history.replaceState({}, '', url);
  };

  const handleParamChange = (apiName, paramName, value) => {
    setParamValues(prev => ({
      ...prev,
      [apiName]: {
        ...prev[apiName],
        [paramName]: value,
      },
    }));
  };

  const toggleApiExpand = apiName => {
    setExpandedApis(prev => ({
      ...prev,
      [apiName]: !prev[apiName],
    }));
  };

  const handleExecuteApi = async api => {
    if (!selectedTarget) {
      setExecutionResult({
        ...executionResult,
        [api.name]: {
          success: false,
          message: 'Please select a target first',
        },
      });
      return;
    }

    try {
      setExecutingApi(api.name);
      setExecutionResult({
        ...executionResult,
        [api.name]: {
          success: null,
          message: 'Executing...',
        },
      });

      // Process parameters before sending
      const processedParams = { ...paramValues[api.name] };
      let validationError = null;
      if (api.parameters) {
        for (const param of api.parameters) {
          if (param.type === 'list') {
            const value = processedParams[param.name];
            if (typeof value === 'string' && value.trim() !== '') {
              try {
                const parsedValue = JSON.parse(value);
                if (!Array.isArray(parsedValue)) {
                  throw new Error('Must be a JSON array');
                }
                processedParams[param.name] = parsedValue;
              } catch {
                validationError = `Invalid JSON array for parameter '${param.name}'. Please enter a valid JSON array (e.g., ["item1", "item2"]) or leave it empty.`;
                break; // Stop processing on first error
              }
            } else if (typeof value === 'string' && value.trim() === '') {
              // If the string is empty, treat it as an empty list
              processedParams[param.name] = [];
            } else if (value === null || value === undefined) {
              // Treat null or undefined as an empty list
              processedParams[param.name] = [];
            } else if (!Array.isArray(value)) {
              // This case handles if the initial value wasn't a string (e.g., from default)
              validationError = `Parameter '${param.name}' expects a list (JSON array), but received unexpected type.`;
              break;
            }
            // If it's already an array (e.g. from default value parsing), keep it
          }
        }
      }

      // If validation failed, show error and return
      if (validationError) {
        setExecutionResult({
          ...executionResult,
          [api.name]: {
            success: false,
            message: validationError,
          },
        });
        setExecutingApi(null); // Reset executing state
        return;
      }

      const jobData = {
        api_name: api.name,
        parameters: processedParams, // Use processed parameters
      };

      const result = await createJob(selectedTarget, jobData);

      setExecutionResult({
        ...executionResult,
        [api.name]: {
          success: true,
          message: `Job created successfully with ID: ${result.id}`,
          jobId: result.id,
        },
      });

      // Navigate to the job details page with the logs tab active
      navigate(`/jobs/${selectedTarget}/${result.id}`);
    } catch (err) {
      console.error(`Error executing API ${api.name}:`, err);
      setExecutionResult({
        ...executionResult,
        [api.name]: {
          success: false,
          message: `Failed to execute API: ${err.message || 'Unknown error'}`,
        },
      });
    } finally {
      setExecutingApi(null);
    }
  };

  const handleExportDefinition = async apiName => {
    try {
      const data = await exportApiDefinition(apiName);
      const jsonString = JSON.stringify(data, null, 2);
      const blob = new Blob([jsonString], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${apiName}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error(`Error exporting API definition for ${apiName}:`, err);
      setError(`Failed to export API definition for ${apiName}`);
    }
  };

  const handleImportClick = () => {
    fileInputRef.current.click();
  };

  const handleFileUpload = async event => {
    const file = event.target.files[0];
    if (!file) return;

    try {
      const reader = new FileReader();
      reader.onload = async e => {
        try {
          const content = JSON.parse(e.target.result);

          // Check if the file has the expected structure
          if (!content.api_definition) {
            setSnackbarMessage('Invalid API definition file format');
            setSnackbarOpen(true);
            return;
          }

          // Import the API definition
          const result = await importApiDefinition({ api_definition: content.api_definition });

          // Show success message
          setSnackbarMessage(result.message);
          setSnackbarOpen(true);

          // Refresh the API list
          fetchData();
        } catch (err) {
          console.error('Error parsing or importing API definition:', err);
          setSnackbarMessage('Failed to import API definition');
          setSnackbarOpen(true);
        }
      };
      reader.readAsText(file);
    } catch (err) {
      console.error('Error reading file:', err);
      setSnackbarMessage('Failed to read file');
      setSnackbarOpen(true);
    }

    // Reset the file input
    event.target.value = null;
  };

  const handleSnackbarClose = () => {
    setSnackbarOpen(false);
  };

  const handleAddApiClick = () => {
    setAddApiDialogOpen(true);
  };

  const handleAddApiClose = () => {
    setAddApiDialogOpen(false);
  };

  const handleApiAdded = () => {
    // Show success message
    setSnackbarMessage('API created successfully');
    setSnackbarOpen(true);

    // Refresh the API list
    fetchData();
  };

  const handleArchiveApi = async (apiName, event) => {
    // Stop event propagation to prevent card expansion
    event.stopPropagation();

    try {
      await archiveApiDefinition(apiName);

      // Show success message
      setSnackbarMessage(`API "${apiName}" archived successfully`);
      setSnackbarOpen(true);

      // Refresh the API list
      fetchData();
    } catch (err) {
      console.error(`Error archiving API ${apiName}:`, err);
      setSnackbarMessage(`Failed to archive API: ${err.message || 'Unknown error'}`);
      setSnackbarOpen(true);
    }
  };

  const handleUnarchiveApi = async (apiName, event) => {
    // Stop event propagation to prevent card expansion
    event.stopPropagation();

    try {
      await unarchiveApiDefinition(apiName);

      // Show success message
      setSnackbarMessage(`API "${apiName}" unarchived successfully`);
      setSnackbarOpen(true);

      // Set showArchived to false to show the unarchived API
      setShowArchived(false);

      // Refresh the API list with showArchived=false
      getApiDefinitions(false)
        .then(apisData => {
          setApis(apisData);

          // Initialize parameter values
          const initialParamValues = {};
          const initialExpandedState = {};
          apisData.forEach(api => {
            const apiParams = {};
            if (api.parameters) {
              api.parameters.forEach(param => {
                apiParams[param.name] = param.default || '';
              });
            }
            initialParamValues[api.name] = apiParams;
            initialExpandedState[api.name] = false;
          });
          setParamValues(initialParamValues);
          setExpandedApis(initialExpandedState);
        })
        .catch(err => {
          console.error('Error fetching API data:', err);
          setError('Failed to load API data. Please try again later.');
        });
    } catch (err) {
      console.error(`Error unarchiving API ${apiName}:`, err);
      setSnackbarMessage(`Failed to unarchive API: ${err.message || 'Unknown error'}`);
      setSnackbarOpen(true);
    }
  };

  const toggleShowArchived = () => {
    setShowArchived(prev => {
      const newValue = !prev;
      // Explicitly call getApiDefinitions with the new value
      setLoading(true);
      getApiDefinitions(newValue)
        .then(apisData => {
          setApis(apisData);

          // Initialize parameter values
          const initialParamValues = {};
          const initialExpandedState = {};
          apisData.forEach(api => {
            const apiParams = {};
            if (api.parameters) {
              api.parameters.forEach(param => {
                apiParams[param.name] = param.default || '';
              });
            }
            initialParamValues[api.name] = apiParams;
            initialExpandedState[api.name] = false;
          });
          setParamValues(initialParamValues);
          setExpandedApis(initialExpandedState);
          setLoading(false);
        })
        .catch(err => {
          console.error('Error fetching API data:', err);
          setError('Failed to load API data. Please try again later.');
          setLoading(false);
        });
      return newValue;
    });
  };

  // Function to handle API duplication
  const handleDuplicateClick = apiName => {
    setDuplicateApiName(apiName);
    setDuplicateApiDialogOpen(true);
  };

  // Function to handle when API was duplicated successfully
  const handleApiDuplicated = () => {
    setSnackbarMessage('API duplicated successfully');
    setSnackbarOpen(true);
    fetchData();
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
      <Alert severity="error" sx={{ mt: 2 }}>
        {error}
      </Alert>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4">Available APIs</Typography>
        <Box sx={{ display: 'flex', gap: 2 }}>
          {selectedTarget ? (
            <Tooltip title="Add API">
              <Button variant="contained" color="primary" onClick={handleAddApiClick}>
                <AddIcon />
              </Button>
            </Tooltip>
          ) : (
            <Button
              variant="contained"
              color="primary"
              startIcon={<AddIcon />}
              onClick={handleAddApiClick}
            >
              Add API
            </Button>
          )}
          {!selectedTarget && (
            <>
              <Button variant="outlined" startIcon={<UploadIcon />} onClick={handleImportClick}>
                Import API
              </Button>
              <Button
                variant="outlined"
                startIcon={showArchived ? <VisibilityOffIcon /> : <VisibilityIcon />}
                onClick={toggleShowArchived}
                aria-label={showArchived ? 'Hide Archived APIs' : 'Show Archived APIs'}
                color={showArchived ? 'secondary' : 'primary'}
              >
                {showArchived ? 'Hide Archived APIs' : 'Show Archived APIs'}
              </Button>
            </>
          )}
          {selectedTarget && (
            <Tooltip title="View Target Details">
              <Button variant="outlined" onClick={() => navigate(`/targets/${selectedTarget}`)}>
                <VisibilityIcon />
              </Button>
            </Tooltip>
          )}
        </Box>
      </Box>
      {/* Target selector */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <FormControl fullWidth variant="outlined">
          <InputLabel id="target-select-label">Select Target</InputLabel>
          <Select
            labelId="target-select-label"
            id="target-select"
            value={selectedTarget}
            label="Select Target"
            onChange={handleTargetChange}
          >
            <MenuItem value="">
              <em>None</em>
            </MenuItem>
            {targets.map(target => (
              <MenuItem key={target.id} value={target.id}>
                {target.name || `Target ${target.id.substring(0, 8)}`}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Paper>
      {/* Rest of the component */}
      <Grid container spacing={3}>
        <Grid size={12}>
          {!selectedTarget && (
            <Typography variant="body1" color="textSecondary" sx={{ mb: 2 }}>
              View and test available APIs
            </Typography>
          )}
        </Grid>

        {apis.length > 0 ? (
          apis.map(api => (
            <Grid key={api.name} size={12}>
              <Card>
                <CardContent sx={{ pb: 0 }}>
                  <Box
                    sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                  >
                    <Box>
                      <Typography variant="h5" component="div">
                        {api.name}
                        {api.is_archived && (
                          <Chip
                            label="Archived"
                            size="small"
                            sx={{ ml: 1, bgcolor: 'rgba(255, 0, 0, 0.1)', color: 'error.light' }}
                          />
                        )}
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        {api.description || 'No description available'}
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      {!selectedTarget && (
                        <>
                          <Tooltip title="Export API Definition">
                            <IconButton
                              onClick={() => handleExportDefinition(api.name)}
                              aria-label="export api"
                            >
                              <DownloadIcon />
                            </IconButton>
                          </Tooltip>
                          {api.is_archived ? (
                            <Tooltip title="Unarchive API">
                              <IconButton
                                onClick={e => handleUnarchiveApi(api.name, e)}
                                aria-label="unarchive api"
                              >
                                <UnarchiveIcon />
                              </IconButton>
                            </Tooltip>
                          ) : (
                            <Tooltip title="Archive API">
                              <IconButton
                                onClick={e => handleArchiveApi(api.name, e)}
                                aria-label="archive api"
                              >
                                <ArchiveIcon />
                              </IconButton>
                            </Tooltip>
                          )}
                        </>
                      )}
                      <Tooltip title="Duplicate API">
                        <IconButton
                          onClick={() => handleDuplicateClick(api.name)}
                          aria-label="duplicate api"
                        >
                          <FileCopyIcon />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Edit API Definition">
                        <IconButton
                          onClick={() => navigate(`/apis/${api.name}/edit`)}
                          aria-label="edit api"
                        >
                          <EditIcon />
                        </IconButton>
                      </Tooltip>
                      {!api.is_archived && selectedTarget && (
                        <>
                          <IconButton
                            onClick={() => toggleApiExpand(api.name)}
                            aria-expanded={expandedApis[api.name]}
                            aria-label="show more"
                          >
                            <SettingsIcon />
                          </IconButton>
                          <Button
                            variant="contained"
                            color="primary"
                            startIcon={
                              executingApi === api.name ? (
                                <CircularProgress size={20} color="inherit" />
                              ) : (
                                <PlayArrowIcon />
                              )
                            }
                            onClick={() => handleExecuteApi(api)}
                            disabled={executingApi !== null}
                            sx={{ ml: 1 }}
                          >
                            {executingApi === api.name ? 'Executing...' : 'Execute'}
                          </Button>
                        </>
                      )}
                    </Box>
                  </Box>

                  {executionResult[api.name] && (
                    <Box sx={{ mt: 2 }}>
                      <Alert
                        severity={
                          executionResult[api.name].success === null
                            ? 'info'
                            : executionResult[api.name].success
                              ? 'success'
                              : 'error'
                        }
                      >
                        {executionResult[api.name].message}
                      </Alert>
                    </Box>
                  )}

                  <Collapse in={expandedApis[api.name]} timeout="auto" unmountOnExit>
                    <Box sx={{ p: 2 }}>
                      <Typography variant="h6" gutterBottom>
                        Parameters
                      </Typography>
                      {api.parameters && api.parameters.length > 0 ? (
                        <Grid container spacing={2}>
                          {api.parameters.map(param => (
                            <Grid
                              key={param.name}
                              size={{
                                xs: 12,
                                sm: 6,
                                md: 4,
                              }}
                            >
                              <TextField
                                label={`${param.name}${param.type === 'list' ? ' (JSON Array)' : ''}`}
                                fullWidth
                                margin="normal"
                                value={paramValues[api.name]?.[param.name] || ''}
                                onChange={e =>
                                  handleParamChange(api.name, param.name, e.target.value)
                                }
                                multiline={param.type === 'list'}
                                rows={param.type === 'list' ? 3 : 1}
                                helperText={param.description || ''}
                                placeholder={
                                  param.type === 'list' ? 'e.g., ["item1", "item2"]' : ''
                                }
                              />
                            </Grid>
                          ))}
                        </Grid>
                      ) : (
                        <Typography variant="body2">No parameters required.</Typography>
                      )}
                    </Box>
                  </Collapse>
                </CardContent>
              </Card>
            </Grid>
          ))
        ) : (
          <Grid size={{ xs: 12 }}>
            <Paper sx={{ p: 3, textAlign: 'center' }}>
              <Typography variant="h6">No APIs available</Typography>
            </Paper>
          </Grid>
        )}
      </Grid>
      {/* Hidden file input for importing API definitions */}
      <input
        type="file"
        ref={fileInputRef}
        style={{ display: 'none' }}
        accept=".json"
        onChange={handleFileUpload}
      />
      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={6000}
        onClose={handleSnackbarClose}
        message={snackbarMessage}
      />
      {/* Add API Dialog */}
      <AddApiDialog
        open={addApiDialogOpen}
        onClose={handleAddApiClose}
        onApiAdded={handleApiAdded}
      />
      {/* Duplicate API Dialog */}
      <DuplicateApiDialog
        open={duplicateApiDialogOpen}
        onClose={() => setDuplicateApiDialogOpen(false)}
        onApiDuplicated={handleApiDuplicated}
        apiName={duplicateApiName}
      />
    </Box>
  );
};

export default ApiList;
