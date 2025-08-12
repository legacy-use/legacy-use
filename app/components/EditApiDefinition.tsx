import AddIcon from '@mui/icons-material/Add';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import DeleteIcon from '@mui/icons-material/Delete';
import HistoryIcon from '@mui/icons-material/History';
import {
  Alert,
  Box,
  Button,
  Card,
  Chip,
  CircularProgress,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  TextField,
  Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  getApiDefinitionDetails,
  getApiDefinitionVersions,
  updateApiDefinition,
} from '../services/apiService';

const EditApiDefinition = () => {
  const { apiName } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const versionId = queryParams.get('version');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [apiDefinition, setApiDefinition] = useState({
    name: '',
    description: '',
    parameters: [],
    prompt: '',
    prompt_cleanup: '',
    response_example: {},
    is_archived: false,
  });

  const [versions, setVersions] = useState([]);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [selectedVersionId, setSelectedVersionId] = useState('');
  const [originalApiDefinition, setOriginalApiDefinition] = useState(null);
  const [isVersionModified, setIsVersionModified] = useState(false);

  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState('success');

  // Load API definition details
  useEffect(() => {
    const fetchApiDefinition = async () => {
      try {
        setLoading(true);
        const data = await getApiDefinitionDetails(apiName);
        setApiDefinition(data);
        setOriginalApiDefinition(data);
        setLoading(false);
      } catch (err) {
        console.error('Error fetching API definition:', err);
        setError(`Failed to load API definition: ${err.message}`);
        setLoading(false);
      }
    };

    fetchApiDefinition();
  }, [apiName]);

  // Load API definition versions
  useEffect(() => {
    const fetchVersions = async () => {
      try {
        setLoadingVersions(true);
        const versionsData = await getApiDefinitionVersions(apiName);
        setVersions(versionsData);

        // If a version ID is specified in the URL, select that version
        if (versionId) {
          setSelectedVersionId(versionId);
          const selectedVersion = versionsData.find(v => v.id === versionId);
          if (selectedVersion) {
            setApiDefinition(prevState => ({
              ...prevState,
              parameters: selectedVersion.parameters,
              prompt: selectedVersion.prompt,
              prompt_cleanup: selectedVersion.prompt_cleanup,
              response_example: selectedVersion.response_example,
            }));
            setOriginalApiDefinition(prevState => ({
              ...prevState,
              parameters: selectedVersion.parameters,
              prompt: selectedVersion.prompt,
              prompt_cleanup: selectedVersion.prompt_cleanup,
              response_example: selectedVersion.response_example,
            }));
          }
        }

        setLoadingVersions(false);
      } catch (err) {
        console.error('Error fetching API definition versions:', err);
        setError(`Failed to load API definition versions: ${err.message}`);
        setLoadingVersions(false);
      }
    };

    fetchVersions();
  }, [apiName, versionId]);

  // Check if the current version has been modified
  useEffect(() => {
    if (originalApiDefinition) {
      const isModified =
        JSON.stringify(apiDefinition.parameters) !==
          JSON.stringify(originalApiDefinition.parameters) ||
        apiDefinition.prompt !== originalApiDefinition.prompt ||
        apiDefinition.prompt_cleanup !== originalApiDefinition.prompt_cleanup ||
        JSON.stringify(apiDefinition.response_example) !==
          JSON.stringify(originalApiDefinition.response_example) ||
        apiDefinition.name !== originalApiDefinition.name ||
        apiDefinition.description !== originalApiDefinition.description;

      setIsVersionModified(isModified);
    }
  }, [apiDefinition, originalApiDefinition]);

  // Handle form field changes
  const handleChange = field => event => {
    setApiDefinition({
      ...apiDefinition,
      [field]: event.target.value,
    });
  };

  // Handle parameter changes
  const handleParameterChange = (index, field) => event => {
    const updatedParameters = [...apiDefinition.parameters];
    updatedParameters[index] = {
      ...updatedParameters[index],
      [field]: event.target.value,
    };

    setApiDefinition({
      ...apiDefinition,
      parameters: updatedParameters,
    });
  };

  // Add a new parameter
  const handleAddParameter = () => {
    setApiDefinition({
      ...apiDefinition,
      parameters: [
        ...apiDefinition.parameters,
        {
          name: '',
          description: '',
          type: 'string',
          required: false,
          default: '',
        },
      ],
    });
  };

  // Remove a parameter
  const handleRemoveParameter = index => {
    const updatedParameters = [...apiDefinition.parameters];
    updatedParameters.splice(index, 1);

    setApiDefinition({
      ...apiDefinition,
      parameters: updatedParameters,
    });
  };

  // Handle response example changes
  const handleResponseExampleChange = event => {
    try {
      const responseExample = JSON.parse(event.target.value);
      setApiDefinition({
        ...apiDefinition,
        response_example: responseExample,
      });
    } catch {
      // If JSON is invalid, just store the string value for now
      setApiDefinition({
        ...apiDefinition,
        response_example: event.target.value,
      });
    }
  };

  // Handle version selection change
  const handleVersionChange = event => {
    const newVersionId = event.target.value;

    // If there are unsaved changes, confirm before switching
    if (isVersionModified) {
      if (!window.confirm('You have unsaved changes. Are you sure you want to switch versions?')) {
        return;
      }
    }

    setSelectedVersionId(newVersionId);

    // Update URL with the selected version
    const newUrl = `/apis/edit/${apiName}?version=${newVersionId}`;
    window.history.pushState({}, '', newUrl);

    // Load the selected version
    if (newVersionId) {
      const selectedVersion = versions.find(v => v.id === newVersionId);
      if (selectedVersion) {
        setApiDefinition(prevState => ({
          ...prevState,
          parameters: selectedVersion.parameters,
          prompt: selectedVersion.prompt,
          prompt_cleanup: selectedVersion.prompt_cleanup,
          response_example: selectedVersion.response_example,
        }));
        setOriginalApiDefinition(prevState => ({
          ...prevState,
          parameters: selectedVersion.parameters,
          prompt: selectedVersion.prompt,
          prompt_cleanup: selectedVersion.prompt_cleanup,
          response_example: selectedVersion.response_example,
        }));

        setSnackbarMessage(`Loaded version ${selectedVersion.version_number}`);
        setSnackbarSeverity('info');
        setSnackbarOpen(true);
      }
    } else {
      // If no version is selected, load the current active version
      const activeVersion = versions.find(v => v.is_active);
      if (activeVersion) {
        setApiDefinition(prevState => ({
          ...prevState,
          parameters: activeVersion.parameters,
          prompt: activeVersion.prompt,
          prompt_cleanup: activeVersion.prompt_cleanup,
          response_example: activeVersion.response_example,
        }));
        setOriginalApiDefinition(prevState => ({
          ...prevState,
          parameters: activeVersion.parameters,
          prompt: activeVersion.prompt,
          prompt_cleanup: activeVersion.prompt_cleanup,
          response_example: activeVersion.response_example,
        }));
      }
    }
  };

  // Save API definition
  const handleSave = async () => {
    try {
      // Validate response_example is valid JSON
      let responseExample = apiDefinition.response_example;
      if (typeof responseExample === 'string') {
        try {
          responseExample = JSON.parse(responseExample);
        } catch {
          setSnackbarMessage('Response example must be valid JSON');
          setSnackbarSeverity('error');
          setSnackbarOpen(true);
          return;
        }
      }

      // Validate required fields
      if (!apiDefinition.name || !apiDefinition.description || !apiDefinition.prompt) {
        setSnackbarMessage('Name, description, and prompt are required');
        setSnackbarSeverity('error');
        setSnackbarOpen(true);
        return;
      }

      // Validate parameters have names
      if (apiDefinition.parameters.some(param => !param.name)) {
        setSnackbarMessage('All parameters must have names');
        setSnackbarSeverity('error');
        setSnackbarOpen(true);
        return;
      }

      // Process parameters before saving
      const processedParameters = apiDefinition.parameters.map(param => {
        if (
          param.type === 'list' &&
          typeof param.default === 'string' &&
          param.default.trim() !== ''
        ) {
          try {
            const parsedDefault = JSON.parse(param.default);
            if (!Array.isArray(parsedDefault)) {
              throw new Error('Default value for list must be a valid JSON array.');
            }
            return { ...param, default: parsedDefault };
          } catch {
            // Throw an error to be caught below, preventing save
            throw new Error(
              `Invalid JSON array in default value for list parameter '${param.name}'.`,
            );
          }
        }
        // Return parameter as is if not type list or default is not a string to parse
        return param;
      });

      // Prepare API definition for update
      const updatedApiDefinition = {
        ...apiDefinition,
        parameters: processedParameters, // Use processed parameters
        response_example: responseExample,
      };

      // Update API definition
      await updateApiDefinition(apiName, updatedApiDefinition);

      // Show success message
      setSnackbarMessage('API definition updated successfully');
      setSnackbarSeverity('success');
      setSnackbarOpen(true);

      // Refresh versions
      const versionsData = await getApiDefinitionVersions(apiName);
      setVersions(versionsData);

      // Update original API definition to reflect saved state
      setOriginalApiDefinition({
        ...apiDefinition,
        response_example: responseExample,
      });

      // Reset modified flag
      setIsVersionModified(false);

      // Navigate back to API list after a short delay
      setTimeout(() => {
        navigate('/apis');
      }, 1500);
    } catch (err) {
      console.error('Error saving API definition:', err);
      setError(`Failed to save API definition: ${err.message}`);
      setSnackbarMessage(`Failed to update API definition: ${err.message || 'Unknown error'}`);
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
    }
  };

  // Handle snackbar close
  const handleSnackbarClose = () => {
    setSnackbarOpen(false);
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
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <IconButton onClick={() => navigate('/apis')} sx={{ mr: 1 }}>
          <ArrowBackIcon />
        </IconButton>
        <Typography variant="h4">Edit API Definition: {apiName}</Typography>
        {apiDefinition.is_archived && (
          <Chip label="Archived" color="error" size="small" sx={{ ml: 2 }} />
        )}
        <Box sx={{ flexGrow: 1 }} />

        <FormControl sx={{ minWidth: 250 }}>
          <InputLabel id="version-select-label">
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              <HistoryIcon sx={{ mr: 1 }} />
              Select Version
            </Box>
          </InputLabel>
          <Select
            labelId="version-select-label"
            value={selectedVersionId}
            onChange={handleVersionChange}
            label="Select Version"
            disabled={loadingVersions || apiDefinition.is_archived}
          >
            {versions.map(version => (
              <MenuItem key={version.id} value={version.id}>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    width: '100%',
                  }}
                >
                  <Typography>Version {version.version_number}</Typography>
                  <Box>
                    {version.is_active && (
                      <Chip label="Active" color="primary" size="small" sx={{ ml: 1 }} />
                    )}
                  </Box>
                </Box>
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>
      {apiDefinition.is_archived && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          This API is archived. You cannot edit it. Please unarchive it from the API list page
          first.
        </Alert>
      )}
      {isVersionModified && !apiDefinition.is_archived && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          You have unsaved changes to this version. Save your changes or select another version to
          discard them.
        </Alert>
      )}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          Basic Information
        </Typography>

        <Grid container spacing={3}>
          <Grid
            size={{
              xs: 12,
              md: 6,
            }}
          >
            <TextField
              label="API Name"
              fullWidth
              value={apiDefinition.name}
              onChange={handleChange('name')}
              margin="normal"
              disabled={true}
            />
          </Grid>
          <Grid
            size={{
              xs: 12,
              md: 6,
            }}
          >
            <TextField
              label="Description"
              fullWidth
              value={apiDefinition.description}
              onChange={handleChange('description')}
              margin="normal"
              multiline
              rows={2}
              disabled={apiDefinition.is_archived}
            />
          </Grid>
        </Grid>
      </Paper>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          Parameters
        </Typography>

        {apiDefinition.parameters && apiDefinition.parameters.length > 0 ? (
          <Grid container spacing={2}>
            {apiDefinition.parameters.map((param, index) => (
              <Grid key={param.id} size={12}>
                <Card variant="outlined" sx={{ p: 2 }}>
                  <Grid container spacing={2}>
                    <Grid
                      size={{
                        xs: 12,
                        sm: 4,
                      }}
                    >
                      <TextField
                        label="Parameter Name"
                        value={param.name}
                        onChange={handleParameterChange(index, 'name')}
                        fullWidth
                        margin="normal"
                        disabled={apiDefinition.is_archived}
                      />
                    </Grid>
                    <Grid
                      size={{
                        xs: 12,
                        sm: 4,
                      }}
                    >
                      <FormControl fullWidth margin="normal" disabled={apiDefinition.is_archived}>
                        <InputLabel id={`param-type-label-${index}`}>Type</InputLabel>
                        <Select
                          labelId={`param-type-label-${index}`}
                          label="Type"
                          value={param.type || 'string'}
                          onChange={handleParameterChange(index, 'type')}
                        >
                          <MenuItem value="string">String</MenuItem>
                          <MenuItem value="list">List</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid
                      size={{
                        xs: 12,
                        sm: 4,
                      }}
                    >
                      <TextField
                        label="Default Value"
                        value={param.default || ''}
                        onChange={handleParameterChange(index, 'default')}
                        fullWidth
                        margin="normal"
                        disabled={apiDefinition.is_archived}
                      />
                    </Grid>
                    <Grid size={12}>
                      <TextField
                        label="Description"
                        value={param.description || ''}
                        onChange={handleParameterChange(index, 'description')}
                        fullWidth
                        margin="normal"
                        multiline
                        rows={2}
                        disabled={apiDefinition.is_archived}
                      />
                    </Grid>
                  </Grid>
                  {!apiDefinition.is_archived && (
                    <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 1 }}>
                      <Button
                        variant="outlined"
                        color="error"
                        startIcon={<DeleteIcon />}
                        onClick={() => handleRemoveParameter(index)}
                      >
                        Remove
                      </Button>
                    </Box>
                  )}
                </Card>
              </Grid>
            ))}
          </Grid>
        ) : (
          <Typography variant="body1" color="textSecondary">
            No parameters defined
          </Typography>
        )}

        {!apiDefinition.is_archived && (
          <Button
            variant="outlined"
            startIcon={<AddIcon />}
            onClick={handleAddParameter}
            sx={{ mt: 2 }}
          >
            Add Parameter
          </Button>
        )}
      </Paper>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          Prompt Configuration
        </Typography>

        <TextField
          label="Prompt Template"
          fullWidth
          multiline
          rows={10}
          value={apiDefinition.prompt}
          onChange={handleChange('prompt')}
          margin="normal"
          disabled={apiDefinition.is_archived}
        />

        <Typography variant="h6" sx={{ mt: 4, mb: 2 }}>
          Prompt Cleanup
        </Typography>

        <TextField
          label="Prompt Cleanup"
          fullWidth
          multiline
          rows={4}
          value={apiDefinition.prompt_cleanup}
          onChange={handleChange('prompt_cleanup')}
          margin="normal"
          helperText="JavaScript code to clean up the prompt before sending to the model"
          disabled={apiDefinition.is_archived}
        />
      </Paper>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          Response Example
        </Typography>

        <TextField
          label="Response Example (JSON)"
          fullWidth
          multiline
          rows={10}
          value={
            typeof apiDefinition.response_example === 'object'
              ? JSON.stringify(apiDefinition.response_example, null, 2)
              : apiDefinition.response_example
          }
          onChange={handleResponseExampleChange}
          margin="normal"
          error={
            typeof apiDefinition.response_example === 'string' &&
            apiDefinition.response_example.includes('Error')
          }
          helperText={
            typeof apiDefinition.response_example === 'string'
              ? apiDefinition.response_example
              : 'JSON example of the expected response'
          }
          disabled={apiDefinition.is_archived}
        />
      </Paper>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 3 }}>
        <Button variant="outlined" onClick={() => navigate('/apis')}>
          Cancel
        </Button>
        {!apiDefinition.is_archived && (
          <Button
            variant="contained"
            color="primary"
            onClick={handleSave}
            disabled={!isVersionModified}
          >
            Save Changes
          </Button>
        )}
      </Box>
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={6000}
        onClose={handleSnackbarClose}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={handleSnackbarClose} severity={snackbarSeverity} sx={{ width: '100%' }}>
          {snackbarMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default EditApiDefinition;
