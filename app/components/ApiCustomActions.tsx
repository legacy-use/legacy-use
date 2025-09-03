import AddIcon from '@mui/icons-material/Add';
import {
  Alert,
  Box,
  Button,
  Card,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControl,
  Grid,
  MenuItem,
  Select,
  Snackbar,
  TextField,
  Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import {
  addCustomActionToApi,
  deleteCustomAction,
  getAvailableKeys,
  getToolsGroup,
  listCustomActions,
} from '../services/apiService';

type ToolActionSpec = {
  name: string;
  params?: Record<string, any>;
  required?: string[];
};

type ToolSpec = {
  name: string;
  description?: string;
  version?: string;
  actions?: ToolActionSpec[];
  input_schema?: {
    type?: string;
    properties?: Record<string, any>;
    required?: string[];
  };
  options?: Record<string, any>;
};

type ApiCustomActionsProps = {
  apiName: string;
  isArchived: boolean;
};

const ApiCustomActions = ({ apiName, isArchived }: ApiCustomActionsProps) => {
  // UI state
  const [snackbarOpen, setSnackbarOpen] = useState<boolean>(false);
  const [snackbarMessage, setSnackbarMessage] = useState<string>('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<
    'success' | 'error' | 'warning' | 'info'
  >('success');

  const [availableTools, setAvailableTools] = useState<ToolSpec[]>([]);
  const [toolsLoading, setToolsLoading] = useState<boolean>(false);
  const [toolsError, setToolsError] = useState<string | null>(null);
  const [selectedToolName, setSelectedToolName] = useState<string>('');
  const [selectedActionName, setSelectedActionName] = useState<string>('');
  const [paramValues, setParamValues] = useState<Record<string, any>>({});
  const [customActions, setCustomActions] = useState<
    { name: string; parameters: Record<string, any> }[]
  >([]);
  const [showAdvancedActions, setShowAdvancedActions] = useState<boolean>(false);
  const [customActionName, setCustomActionName] = useState<string>('');
  const [savingCustomAction, setSavingCustomAction] = useState<boolean>(false);
  const [existingCustomActions, setExistingCustomActions] = useState<Record<string, any>>({});
  const [loadingExistingActions, setLoadingExistingActions] = useState<boolean>(false);
  const [deleteConfirmName, setDeleteConfirmName] = useState<string | null>(null);

  // Available keys for key action
  const [availableKeys, setAvailableKeys] = useState<string[]>([]);
  const [keysError, setKeysError] = useState<string | null>(null);

  // Load tools for a specific group and keep only computer
  useEffect(() => {
    const fetchTools = async () => {
      try {
        setToolsLoading(true);
        // hardcoded computer_use_20250124, could be made dynamic at some point, but probably deprecating the 20241022 group is the better option
        const tools = (await getToolsGroup('computer_use_20250124')) as ToolSpec[];
        const computerOnly = (tools || []).filter(t => t.name === 'computer');
        setAvailableTools(computerOnly);
        if (computerOnly.length > 0) {
          setSelectedToolName(computerOnly[0].name);
        }
        setToolsLoading(false);
      } catch (err: any) {
        console.error('Error fetching tools group:', err);
        setToolsError(`Failed to load tools: ${err?.message || 'Unknown error'}`);
        setToolsLoading(false);
      }
    };
    fetchTools();
  }, []);

  // Load existing saved custom actions for this API
  useEffect(() => {
    const fetchExisting = async () => {
      if (!apiName) return;
      try {
        setLoadingExistingActions(true);
        const actions = await listCustomActions(apiName);
        setExistingCustomActions(actions || {});
      } catch (err: any) {
        console.error('Error fetching existing custom actions:', err);
      } finally {
        setLoadingExistingActions(false);
      }
    };
    fetchExisting();
  }, [apiName, snackbarOpen]);

  // Load available keys for the key action on demand
  useEffect(() => {
    let cancelled = false;
    const loadKeys = async () => {
      if (selectedActionName !== 'key' || availableKeys.length > 0) return;
      try {
        const keys = await getAvailableKeys();
        if (!cancelled) {
          setAvailableKeys(Array.isArray(keys) ? keys : []);
        }
      } catch (err: any) {
        if (!cancelled) {
          setKeysError(`Failed to load keys: ${err?.message || 'Unknown error'}`);
        }
      }
    };
    loadKeys();
    return () => {
      cancelled = true;
    };
  }, [selectedActionName, availableKeys.length]);

  // Derived helpers for selected tool/action
  const selectedTool: ToolSpec | undefined = availableTools.find(t => t.name === selectedToolName);
  const selectedAction: ToolActionSpec | undefined = selectedTool?.actions?.find(
    a => a.name === selectedActionName,
  );

  // Partition actions into primary vs advanced
  const primaryActionNames = new Set([
    'left_click',
    'type',
    'key',
    'scroll',
    'double_click',
    'right_click',
    'wait',
  ]);
  const allActions = selectedTool?.actions || [];
  const primaryActions = allActions.filter(a => primaryActionNames.has(a.name));
  const advancedActions = allActions.filter(a => !primaryActionNames.has(a.name));

  const currentParamSpec: Record<string, any> =
    (selectedAction?.params as Record<string, any>) ||
    (selectedTool?.input_schema?.properties as Record<string, any>) ||
    {};

  const currentRequired: string[] =
    (selectedAction?.required as string[]) ||
    (selectedTool?.input_schema?.required as string[]) ||
    [];

  const canConfigureSelectedAction = Boolean(selectedAction);

  const handleParamChange = (key: string) => (event: any) => {
    setParamValues(prev => ({ ...prev, [key]: event.target.value }));
  };

  const handleCoordinateChange = (axis: 0 | 1) => (event: any) => {
    const raw = event.target.value;
    const num = raw === '' ? '' : Number(raw);
    setParamValues(prev => {
      const prevArr = Array.isArray(prev.coordinate) ? prev.coordinate : ['', ''];
      const nextArr: any[] = [...prevArr];
      nextArr[axis] = Number.isNaN(num as any) ? raw : num;
      return { ...prev, coordinate: nextArr };
    });
  };

  const parseParamValue = (schema: any, raw: any) => {
    if (raw === '' || raw === undefined || raw === null) return undefined;
    const type = schema?.type;
    if (type === 'integer' || type === 'number') {
      const n = Number(raw);
      return Number.isNaN(n) ? raw : n;
    }
    if (type === 'array' || type === 'object') {
      if (typeof raw === 'string') {
        try {
          return JSON.parse(raw);
        } catch {
          return raw;
        }
      }
      return raw;
    }
    return raw;
  };

  const handleAddConfiguredAction = () => {
    if (!selectedTool) {
      setSnackbarMessage('Please select a tool');
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
      return;
    }
    if (selectedTool.actions && selectedTool.actions.length > 0 && !selectedAction) {
      setSnackbarMessage('Please select an action');
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
      return;
    }
    for (const key of currentRequired) {
      const val = paramValues[key];
      if (val === undefined || val === '') {
        setSnackbarMessage(`Missing required parameter: ${key}`);
        setSnackbarSeverity('error');
        setSnackbarOpen(true);
        return;
      }
    }
    const builtParams: Record<string, any> = {};
    Object.entries(currentParamSpec).forEach(([key, schema]) => {
      const raw = (paramValues as any)[key];
      if (raw !== undefined && raw !== '') {
        builtParams[key] = parseParamValue(schema as any, raw);
      }
    });
    if (selectedAction) {
      builtParams.action = selectedAction.name;
    }
    const newAction = { name: selectedTool.name, parameters: builtParams };
    setCustomActions(prev => [...prev, newAction]);
    setParamValues({});
    setSelectedActionName('');
    setSnackbarMessage('Action added');
    setSnackbarSeverity('success');
    setSnackbarOpen(true);
  };

  const handleRemoveConfiguredAction = (index: number) => {
    setCustomActions(prev => prev.filter((_, i) => i !== index));
  };

  const handleSaveCustomAction = async () => {
    if (!apiName) return;
    if (!customActionName.trim()) {
      setSnackbarMessage('Please provide a name for this custom action');
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
      return;
    }
    if (customActions.length === 0) {
      setSnackbarMessage('Add at least one action to save');
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
      return;
    }
    try {
      setSavingCustomAction(true);
      const payload = {
        name: customActionName.trim(),
        tools: customActions,
      };
      await addCustomActionToApi(apiName, payload);
      setSnackbarMessage('Custom action saved');
      setSnackbarSeverity('success');
      setSnackbarOpen(true);
      setCustomActions([]);
      setCustomActionName('');
    } catch (err: any) {
      setSnackbarMessage(`Failed to save custom action: ${err?.message || 'Unknown error'}`);
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
    } finally {
      setSavingCustomAction(false);
    }
  };

  const handleDeleteExistingCustomAction = async (name: string) => {
    if (!apiName) return;
    try {
      await deleteCustomAction(apiName, name);
      setSnackbarMessage('Custom action deleted');
      setSnackbarSeverity('success');
      setSnackbarOpen(true);
      setExistingCustomActions(prev => {
        const copy = { ...prev } as any;
        delete copy[name];
        return copy;
      });
    } catch (err: any) {
      setSnackbarMessage(`Failed to delete custom action: ${err?.message || 'Unknown error'}`);
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
    }
  };

  const openDeleteConfirm = (name: string) => setDeleteConfirmName(name);
  const closeDeleteConfirm = () => setDeleteConfirmName(null);
  const confirmDelete = async () => {
    if (deleteConfirmName) {
      await handleDeleteExistingCustomAction(deleteConfirmName);
    }
    closeDeleteConfirm();
  };

  const handleSnackbarClose = () => setSnackbarOpen(false);

  const selectedToolHasActions = Boolean(
    selectedTool && selectedTool.actions && selectedTool.actions.length > 0,
  );

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Custom Actions
      </Typography>

      {toolsLoading && (
        <Typography variant="body2" color="textSecondary">
          Loading tools…
        </Typography>
      )}
      {toolsError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {toolsError}
        </Alert>
      )}

      <Grid container spacing={2}>
        {/* Actions as selectable buttons (no dropdown) */}
        {selectedToolHasActions && (
          <Grid size={12}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mt: 1 }}>
              <Typography variant="subtitle2">Actions</Typography>
              {advancedActions.length > 0 && (
                <Button
                  size="small"
                  onClick={() => setShowAdvancedActions(v => !v)}
                  disabled={isArchived}
                >
                  {showAdvancedActions ? 'Hide advanced' : 'Show advanced'}
                </Button>
              )}
            </Box>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1 }}>
              {primaryActions.map(action => (
                <Button
                  key={action.name}
                  size="small"
                  variant={selectedActionName === action.name ? 'contained' : 'outlined'}
                  onClick={() => setSelectedActionName(action.name)}
                  disabled={isArchived}
                >
                  {action.name}
                </Button>
              ))}
              {showAdvancedActions &&
                advancedActions.map(action => (
                  <Button
                    key={action.name}
                    size="small"
                    variant={selectedActionName === action.name ? 'contained' : 'outlined'}
                    onClick={() => setSelectedActionName(action.name)}
                    disabled={isArchived}
                  >
                    {action.name}
                  </Button>
                ))}
            </Box>
          </Grid>
        )}

        {/* Dynamic parameter inputs */}
        {canConfigureSelectedAction && Object.keys(currentParamSpec).length > 0 && (
          <Grid size={12}>
            <Card variant="outlined" sx={{ p: 2 }}>
              <Grid container spacing={2}>
                {Object.entries(currentParamSpec).map(([key, schema]) => {
                  const sch: any = schema as any;
                  const type = sch?.type;
                  const isJson = type === 'array' || type === 'object';
                  const isNumber = type === 'integer' || type === 'number';
                  const required = currentRequired.includes(key);
                  const isCoordinateTuple =
                    key === 'coordinate' &&
                    type === 'array' &&
                    sch?.minItems === 2 &&
                    sch?.maxItems === 2;

                  if (isCoordinateTuple) {
                    const xVal = Array.isArray(paramValues.coordinate)
                      ? (paramValues.coordinate[0] ?? '')
                      : '';
                    const yVal = Array.isArray(paramValues.coordinate)
                      ? (paramValues.coordinate[1] ?? '')
                      : '';
                    return (
                      <Grid key={key} size={{ xs: 12 }}>
                        <Typography variant="subtitle2">{`${key}${required ? ' *' : ''}`}</Typography>
                        <Box sx={{ display: 'flex', gap: 2 }}>
                          <TextField
                            label="X"
                            value={xVal}
                            onChange={handleCoordinateChange(0)}
                            fullWidth
                            margin="normal"
                            type="number"
                            disabled={isArchived}
                          />
                          <TextField
                            label="Y"
                            value={yVal}
                            onChange={handleCoordinateChange(1)}
                            fullWidth
                            margin="normal"
                            type="number"
                            disabled={isArchived}
                          />
                        </Box>
                      </Grid>
                    );
                  }

                  // Special Autocomplete for key action's text parameter
                  if (selectedAction?.name === 'key' && key === 'text') {
                    const currentText =
                      typeof paramValues.text === 'string' ? paramValues.text : '';
                    const handleAppendKey = (k: string) => {
                      const base = currentText.trim();
                      const next = base ? `${base}+${k}` : k;
                      setParamValues(prev => ({ ...prev, text: next }));
                    };
                    return (
                      <Grid key={key} size={{ xs: 12 }}>
                        <Grid container spacing={2}>
                          <Grid size={{ xs: 12, md: 8 }}>
                            <TextField
                              label={`${key}${required ? ' *' : ''}`}
                              value={currentText}
                              onChange={e =>
                                setParamValues(prev => ({ ...prev, text: e.target.value }))
                              }
                              fullWidth
                              margin="normal"
                              helperText={
                                keysError
                                  ? keysError
                                  : 'Type freely (e.g., ctrl+c) or add from the list'
                              }
                              disabled={isArchived}
                            />
                          </Grid>
                          <Grid size={{ xs: 12, md: 4 }}>
                            <FormControl fullWidth margin="normal" disabled={isArchived}>
                              <Select
                                labelId={`available-keys-label-${key}`}
                                value=""
                                displayEmpty
                                onChange={e => {
                                  const v = e.target.value as string;
                                  if (v) handleAppendKey(v);
                                }}
                              >
                                <MenuItem value="">
                                  <em>Add key…</em>
                                </MenuItem>
                                {availableKeys.map(k => (
                                  <MenuItem key={k} value={k}>
                                    {k}
                                  </MenuItem>
                                ))}
                              </Select>
                            </FormControl>
                          </Grid>
                        </Grid>
                      </Grid>
                    );
                  }

                  return (
                    <Grid key={key} size={{ xs: 12, md: 4 }}>
                      <TextField
                        label={`${key}${required ? ' *' : ''}`}
                        value={(paramValues as any)[key] ?? ''}
                        onChange={handleParamChange(key)}
                        fullWidth
                        margin="normal"
                        type={isNumber ? 'number' : 'text'}
                        multiline={isJson}
                        rows={isJson ? 3 : 1}
                        helperText={isJson ? 'Enter valid JSON' : sch?.description || ''}
                        disabled={isArchived}
                      />
                    </Grid>
                  );
                })}
              </Grid>
            </Card>
          </Grid>
        )}

        {canConfigureSelectedAction && (
          <Grid size={12}>
            <Button
              variant="outlined"
              startIcon={<AddIcon />}
              onClick={handleAddConfiguredAction}
              sx={{ mt: 1 }}
              disabled={isArchived}
            >
              Add Action To List
            </Button>
          </Grid>
        )}
      </Grid>

      {/* Current configured actions */}
      {customActions.length > 0 && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="subtitle1" gutterBottom>
            Configured Actions
          </Typography>

          <Grid container spacing={2}>
            {customActions.map((act, idx) => (
              <Grid key={`${act.name}-${idx}`} size={{ xs: 12, md: 6 }}>
                <Card variant="outlined" sx={{ p: 2 }}>
                  <Box
                    sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
                  >
                    <Box>
                      <Typography variant="body1">
                        {idx + 1}. {act.name}
                      </Typography>
                      <Typography
                        variant="body2"
                        color="textSecondary"
                        sx={{ whiteSpace: 'pre-wrap' }}
                      >
                        {JSON.stringify(act.parameters)}
                      </Typography>
                    </Box>
                    {!isArchived && (
                      <Button
                        color="error"
                        variant="outlined"
                        onClick={() => handleRemoveConfiguredAction(idx)}
                      >
                        Remove
                      </Button>
                    )}
                  </Box>
                </Card>
              </Grid>
            ))}
          </Grid>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                label="Custom action name"
                fullWidth
                value={customActionName}
                onChange={e => setCustomActionName(e.target.value)}
                margin="normal"
                disabled={isArchived}
              />
              <Button
                variant="contained"
                onClick={handleSaveCustomAction}
                disabled={isArchived || savingCustomAction}
              >
                {savingCustomAction ? 'Saving…' : 'Save Custom Action'}
              </Button>
            </Grid>
          </Grid>
        </Box>
      )}

      {/* Existing saved custom actions */}
      <Box sx={{ mt: 4 }}>
        <Typography variant="subtitle1" gutterBottom>
          Saved Custom Actions
        </Typography>
        {loadingExistingActions ? (
          <Typography variant="body2" color="textSecondary">
            Loading…
          </Typography>
        ) : Object.keys(existingCustomActions).length === 0 ? (
          <Typography variant="body2" color="textSecondary">
            No saved custom actions
          </Typography>
        ) : (
          <Grid container spacing={2}>
            {Object.entries(existingCustomActions).map(([name, action]) => (
              <Grid key={name} size={{ xs: 12, md: 6 }}>
                <Card variant="outlined" sx={{ p: 2 }}>
                  <Box
                    sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
                  >
                    <Box>
                      <Typography variant="body1">{name}</Typography>
                      <Typography
                        variant="body2"
                        color="textSecondary"
                        sx={{ whiteSpace: 'pre-wrap' }}
                      >
                        {JSON.stringify((action as any).tools ?? (action as any).actions ?? action)}
                      </Typography>
                    </Box>
                    {!isArchived && (
                      <Button
                        color="error"
                        variant="outlined"
                        onClick={() => openDeleteConfirm(name)}
                      >
                        Delete
                      </Button>
                    )}
                  </Box>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </Box>

      {/* Delete confirmation dialog */}
      <Dialog open={Boolean(deleteConfirmName)} onClose={closeDeleteConfirm}>
        <DialogTitle>Delete custom action</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to delete "{deleteConfirmName}"? This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDeleteConfirm}>Cancel</Button>
          <Button color="error" variant="contained" onClick={confirmDelete}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>

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

export default ApiCustomActions;
