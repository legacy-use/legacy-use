import React, { useState, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Button,
  IconButton,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  Menu,
  MenuItem,
  Divider,
  Card,
  CardContent,
  CardActions,
  FormControl,
  InputLabel,
  Select,
  Alert
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  Edit as EditIcon,
  PlayArrow as PlayIcon,
  DragIndicator as DragIcon,
  ExpandMore as ExpandMoreIcon,
  MoreVert as MoreVertIcon,
  ContentCopy as CopyIcon,
  ArrowUpward as MoveUpIcon,
  ArrowDownward as MoveDownIcon
} from '@mui/icons-material';

// Action types available for computer use
const ACTION_TYPES = {
  CLICK: 'click',
  TYPE: 'type',
  KEY_PRESS: 'key_press',
  SCROLL: 'scroll',
  WAIT: 'wait',
  EXTRACT: 'extract',
  UI_CHECK: 'ui_check'
};

const ACTION_TYPE_LABELS = {
  [ACTION_TYPES.CLICK]: 'Click',
  [ACTION_TYPES.TYPE]: 'Type Text',
  [ACTION_TYPES.KEY_PRESS]: 'Press Key',
  [ACTION_TYPES.SCROLL]: 'Scroll',
  [ACTION_TYPES.WAIT]: 'Wait',
  [ACTION_TYPES.EXTRACT]: 'Extract Data',
  [ACTION_TYPES.UI_CHECK]: 'UI Verification'
};

const WorkflowEditor = ({ 
  workflow, 
  onChange, 
  onExecuteAction, 
  executionResults, 
  isExecuting 
}) => {
  const [editingStep, setEditingStep] = useState(null);
  const [editingAction, setEditingAction] = useState(null);
  const [stepDialogOpen, setStepDialogOpen] = useState(false);
  const [actionDialogOpen, setActionDialogOpen] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState(null);
  const [selectedStepId, setSelectedStepId] = useState(null);
  const [expandedStep, setExpandedStep] = useState(null);

  // Step form state
  const [stepForm, setStepForm] = useState({
    name: '',
    description: '',
    prompt: ''
  });

  // Action form state
  const [actionForm, setActionForm] = useState({
    type: ACTION_TYPES.CLICK,
    description: '',
    parameters: {},
    expectedUI: '',
    prompt: ''
  });

  const handleAddStep = () => {
    setEditingStep(null);
    setStepForm({
      name: '',
      description: '',
      prompt: ''
    });
    setStepDialogOpen(true);
  };

  const handleEditStep = (step) => {
    setEditingStep(step);
    setStepForm({
      name: step.name,
      description: step.description,
      prompt: step.prompt || ''
    });
    setStepDialogOpen(true);
  };

  const handleSaveStep = () => {
    const newStep = {
      id: editingStep?.id || Date.now(),
      name: stepForm.name,
      description: stepForm.description,
      prompt: stepForm.prompt,
      actions: editingStep?.actions || []
    };

    const updatedSteps = editingStep
      ? workflow.steps.map(step => step.id === editingStep.id ? newStep : step)
      : [...workflow.steps, newStep];

    onChange({
      ...workflow,
      steps: updatedSteps
    });

    setStepDialogOpen(false);
    setEditingStep(null);
  };

  const handleDeleteStep = (stepId) => {
    const updatedSteps = workflow.steps.filter(step => step.id !== stepId);
    onChange({
      ...workflow,
      steps: updatedSteps
    });
  };

  const handleMoveStep = (stepId, direction) => {
    const stepIndex = workflow.steps.findIndex(step => step.id === stepId);
    if (stepIndex === -1) return;

    const newIndex = direction === 'up' ? stepIndex - 1 : stepIndex + 1;
    if (newIndex < 0 || newIndex >= workflow.steps.length) return;

    const updatedSteps = [...workflow.steps];
    [updatedSteps[stepIndex], updatedSteps[newIndex]] = [updatedSteps[newIndex], updatedSteps[stepIndex]];

    onChange({
      ...workflow,
      steps: updatedSteps
    });
  };

  const handleAddAction = (stepId) => {
    setSelectedStepId(stepId);
    setEditingAction(null);
    setActionForm({
      type: ACTION_TYPES.CLICK,
      description: '',
      parameters: {},
      expectedUI: '',
      prompt: ''
    });
    setActionDialogOpen(true);
  };

  const handleEditAction = (stepId, action) => {
    setSelectedStepId(stepId);
    setEditingAction(action);
    setActionForm({
      type: action.type,
      description: action.description,
      parameters: action.parameters || {},
      expectedUI: action.expectedUI || '',
      prompt: action.prompt || ''
    });
    setActionDialogOpen(true);
  };

  const handleSaveAction = () => {
    const newAction = {
      id: editingAction?.id || Date.now(),
      type: actionForm.type,
      description: actionForm.description,
      parameters: actionForm.parameters,
      expectedUI: actionForm.expectedUI,
      prompt: actionForm.prompt
    };

    const updatedSteps = workflow.steps.map(step => {
      if (step.id === selectedStepId) {
        const updatedActions = editingAction
          ? step.actions.map(action => action.id === editingAction.id ? newAction : action)
          : [...(step.actions || []), newAction];
        
        return { ...step, actions: updatedActions };
      }
      return step;
    });

    onChange({
      ...workflow,
      steps: updatedSteps
    });

    setActionDialogOpen(false);
    setEditingAction(null);
  };

  const handleDeleteAction = (stepId, actionId) => {
    const updatedSteps = workflow.steps.map(step => {
      if (step.id === stepId) {
        return {
          ...step,
          actions: step.actions.filter(action => action.id !== actionId)
        };
      }
      return step;
    });

    onChange({
      ...workflow,
      steps: updatedSteps
    });
  };

  const getActionParameters = (type) => {
    switch (type) {
      case ACTION_TYPES.CLICK:
        return (
          <TextField
            fullWidth
            label="Element Description"
            value={actionForm.parameters.element || ''}
            onChange={(e) => setActionForm(prev => ({
              ...prev,
              parameters: { ...prev.parameters, element: e.target.value }
            }))}
            placeholder="e.g., 'OK button', 'username field'"
            margin="normal"
          />
        );
      case ACTION_TYPES.TYPE:
        return (
          <TextField
            fullWidth
            label="Text to Type"
            value={actionForm.parameters.text || ''}
            onChange={(e) => setActionForm(prev => ({
              ...prev,
              parameters: { ...prev.parameters, text: e.target.value }
            }))}
            placeholder="Text to enter"
            margin="normal"
          />
        );
      case ACTION_TYPES.KEY_PRESS:
        return (
          <TextField
            fullWidth
            label="Key(s) to Press"
            value={actionForm.parameters.keys || ''}
            onChange={(e) => setActionForm(prev => ({
              ...prev,
              parameters: { ...prev.parameters, keys: e.target.value }
            }))}
            placeholder="e.g., 'RETURN', 'CTRL+C', 'TAB'"
            margin="normal"
          />
        );
      case ACTION_TYPES.SCROLL:
        return (
          <FormControl fullWidth margin="normal">
            <InputLabel>Scroll Direction</InputLabel>
            <Select
              value={actionForm.parameters.direction || 'down'}
              onChange={(e) => setActionForm(prev => ({
                ...prev,
                parameters: { ...prev.parameters, direction: e.target.value }
              }))}
            >
              <MenuItem value="up">Up</MenuItem>
              <MenuItem value="down">Down</MenuItem>
            </Select>
          </FormControl>
        );
      case ACTION_TYPES.WAIT:
        return (
          <TextField
            fullWidth
            type="number"
            label="Wait Duration (seconds)"
            value={actionForm.parameters.duration || 1}
            onChange={(e) => setActionForm(prev => ({
              ...prev,
              parameters: { ...prev.parameters, duration: parseInt(e.target.value) }
            }))}
            margin="normal"
          />
        );
      case ACTION_TYPES.EXTRACT:
        return (
          <TextField
            fullWidth
            label="Data to Extract"
            value={actionForm.parameters.target || ''}
            onChange={(e) => setActionForm(prev => ({
              ...prev,
              parameters: { ...prev.parameters, target: e.target.value }
            }))}
            placeholder="Description of data to extract"
            margin="normal"
          />
        );
      default:
        return null;
    }
  };

  const getExecutionResult = (stepId, actionId) => {
    return executionResults.find(result => 
      result.stepId === stepId && result.actionId === actionId
    );
  };

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', p: 2 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6">{workflow.name}</Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={handleAddStep}
          size="small"
        >
          Add Step
        </Button>
      </Box>

      {/* Workflow Steps */}
      <Box sx={{ flex: 1, overflow: 'auto' }}>
        {workflow.steps.length === 0 ? (
          <Paper sx={{ p: 3, textAlign: 'center', backgroundColor: 'background.default' }}>
            <Typography color="text.secondary">
              No workflow steps defined. Click "Add Step" to get started.
            </Typography>
          </Paper>
        ) : (
          workflow.steps.map((step, stepIndex) => (
            <Accordion
              key={step.id}
              expanded={expandedStep === step.id}
              onChange={(_, isExpanded) => setExpandedStep(isExpanded ? step.id : null)}
              sx={{ mb: 1 }}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box sx={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                  <DragIcon sx={{ mr: 1, color: 'text.secondary' }} />
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="subtitle1">
                      {stepIndex + 1}. {step.name}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {step.actions?.length || 0} actions
                    </Typography>
                  </Box>
                  <IconButton
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuAnchor(e.currentTarget);
                      setSelectedStepId(step.id);
                    }}
                  >
                    <MoreVertIcon />
                  </IconButton>
                </Box>
              </AccordionSummary>
              
              <AccordionDetails>
                <Box>
                  {step.description && (
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {step.description}
                    </Typography>
                  )}

                  {/* Actions */}
                  <Box sx={{ mb: 2 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                      <Typography variant="subtitle2">Actions</Typography>
                      <Button
                        size="small"
                        startIcon={<AddIcon />}
                        onClick={() => handleAddAction(step.id)}
                      >
                        Add Action
                      </Button>
                    </Box>

                    {step.actions?.map((action, actionIndex) => {
                      const result = getExecutionResult(step.id, action.id);
                      return (
                        <Card key={action.id} sx={{ mb: 1, backgroundColor: 'background.default' }}>
                          <CardContent sx={{ pb: 1 }}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                              <Box sx={{ flex: 1 }}>
                                <Typography variant="body2" fontWeight="medium">
                                  {actionIndex + 1}. {ACTION_TYPE_LABELS[action.type]}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                  {action.description}
                                </Typography>
                                {result && (
                                  <Chip
                                    size="small"
                                    label={result.result.success ? 'Success' : 'Failed'}
                                    color={result.result.success ? 'success' : 'error'}
                                    sx={{ mt: 1 }}
                                  />
                                )}
                              </Box>
                              <Box>
                                <IconButton
                                  size="small"
                                  onClick={() => onExecuteAction(step.id, action.id)}
                                  disabled={isExecuting}
                                >
                                  <PlayIcon />
                                </IconButton>
                                <IconButton
                                  size="small"
                                  onClick={() => handleEditAction(step.id, action)}
                                >
                                  <EditIcon />
                                </IconButton>
                                <IconButton
                                  size="small"
                                  onClick={() => handleDeleteAction(step.id, action.id)}
                                  color="error"
                                >
                                  <DeleteIcon />
                                </IconButton>
                              </Box>
                            </Box>
                          </CardContent>
                        </Card>
                      );
                    })}

                    {(!step.actions || step.actions.length === 0) && (
                      <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                        No actions defined for this step.
                      </Typography>
                    )}
                  </Box>
                </Box>
              </AccordionDetails>
            </Accordion>
          ))
        )}
      </Box>

      {/* Step Context Menu */}
      <Menu
        anchorEl={menuAnchor}
        open={Boolean(menuAnchor)}
        onClose={() => setMenuAnchor(null)}
      >
        <MenuItem onClick={() => {
          const step = workflow.steps.find(s => s.id === selectedStepId);
          handleEditStep(step);
          setMenuAnchor(null);
        }}>
          <EditIcon sx={{ mr: 1 }} />
          Edit Step
        </MenuItem>
        <MenuItem onClick={() => {
          handleMoveStep(selectedStepId, 'up');
          setMenuAnchor(null);
        }}>
          <MoveUpIcon sx={{ mr: 1 }} />
          Move Up
        </MenuItem>
        <MenuItem onClick={() => {
          handleMoveStep(selectedStepId, 'down');
          setMenuAnchor(null);
        }}>
          <MoveDownIcon sx={{ mr: 1 }} />
          Move Down
        </MenuItem>
        <Divider />
        <MenuItem onClick={() => {
          handleDeleteStep(selectedStepId);
          setMenuAnchor(null);
        }} sx={{ color: 'error.main' }}>
          <DeleteIcon sx={{ mr: 1 }} />
          Delete Step
        </MenuItem>
      </Menu>

      {/* Step Dialog */}
      <Dialog open={stepDialogOpen} onClose={() => setStepDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editingStep ? 'Edit Step' : 'Add New Step'}</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            label="Step Name"
            value={stepForm.name}
            onChange={(e) => setStepForm(prev => ({ ...prev, name: e.target.value }))}
            margin="normal"
          />
          <TextField
            fullWidth
            multiline
            rows={3}
            label="Description"
            value={stepForm.description}
            onChange={(e) => setStepForm(prev => ({ ...prev, description: e.target.value }))}
            margin="normal"
          />
          <TextField
            fullWidth
            multiline
            rows={4}
            label="Custom Prompt (Optional)"
            value={stepForm.prompt}
            onChange={(e) => setStepForm(prev => ({ ...prev, prompt: e.target.value }))}
            margin="normal"
            placeholder="Custom instructions for this step..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStepDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleSaveStep} variant="contained" disabled={!stepForm.name}>
            {editingStep ? 'Update' : 'Add'} Step
          </Button>
        </DialogActions>
      </Dialog>

      {/* Action Dialog */}
      <Dialog open={actionDialogOpen} onClose={() => setActionDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editingAction ? 'Edit Action' : 'Add New Action'}</DialogTitle>
        <DialogContent>
          <FormControl fullWidth margin="normal">
            <InputLabel>Action Type</InputLabel>
            <Select
              value={actionForm.type}
              onChange={(e) => setActionForm(prev => ({ ...prev, type: e.target.value }))}
            >
              {Object.entries(ACTION_TYPE_LABELS).map(([value, label]) => (
                <MenuItem key={value} value={value}>{label}</MenuItem>
              ))}
            </Select>
          </FormControl>

          <TextField
            fullWidth
            label="Action Description"
            value={actionForm.description}
            onChange={(e) => setActionForm(prev => ({ ...prev, description: e.target.value }))}
            margin="normal"
            placeholder="Brief description of what this action does"
          />

          {getActionParameters(actionForm.type)}

          <TextField
            fullWidth
            multiline
            rows={2}
            label="Expected UI State"
            value={actionForm.expectedUI}
            onChange={(e) => setActionForm(prev => ({ ...prev, expectedUI: e.target.value }))}
            margin="normal"
            placeholder="Describe what the UI should look like before this action"
          />

          <TextField
            fullWidth
            multiline
            rows={3}
            label="Custom Prompt (Optional)"
            value={actionForm.prompt}
            onChange={(e) => setActionForm(prev => ({ ...prev, prompt: e.target.value }))}
            margin="normal"
            placeholder="Custom instructions for this action..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setActionDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleSaveAction} 
            variant="contained" 
            disabled={!actionForm.description}
          >
            {editingAction ? 'Update' : 'Add'} Action
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default WorkflowEditor;