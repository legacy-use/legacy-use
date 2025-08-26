import { Add, ExpandMore, PlayArrow } from '@mui/icons-material';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  TextField,
  Typography,
} from '@mui/material';
import type { KeyboardSequenceStep } from './types';
import { SPECIAL_KEYS } from './types';

interface KeyboardSequencesProps {
  keyboardSequence: KeyboardSequenceStep[];
  setKeyboardSequence: (sequence: KeyboardSequenceStep[]) => void;
  newStepType: 'text' | 'key';
  setNewStepType: (type: 'text' | 'key') => void;
  newStepContent: string;
  setNewStepContent: (content: string) => void;
  selectedSpecialKey: string;
  setSelectedSpecialKey: (key: string) => void;
  isExecutingSequence: boolean;
  isExecuting: boolean;
  onAddSequenceStep: () => void;
  onExecuteKeyboardSequence: () => void;
  onRemoveSequenceStep: (id: string) => void;
  renderSequenceStep: (step: KeyboardSequenceStep, index: number) => React.ReactNode;
}

export default function KeyboardSequences({
  keyboardSequence,
  setKeyboardSequence,
  newStepType,
  setNewStepType,
  newStepContent,
  setNewStepContent,
  selectedSpecialKey,
  setSelectedSpecialKey,
  isExecutingSequence,
  isExecuting,
  onAddSequenceStep,
  onExecuteKeyboardSequence,
  onRemoveSequenceStep,
  renderSequenceStep,
}: KeyboardSequencesProps) {
  return (
    <Accordion>
      <AccordionSummary expandIcon={<ExpandMore />}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <PlayArrow />
          <Typography variant="h6">Keyboard Sequences</Typography>
          {keyboardSequence.length > 0 && (
            <Chip
              label={`${keyboardSequence.length} steps`}
              size="small"
              color="primary"
              sx={{ ml: 1 }}
            />
          )}
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
          Build and execute multi-step keyboard sequences with text input and special keys.
        </Typography>

        {/* Sequence Builder */}
        <Paper sx={{ p: 2, mb: 2, backgroundColor: 'grey.900' }}>
          <Typography variant="subtitle2" gutterBottom>
            Add New Step
          </Typography>
          <Grid container spacing={2} alignItems="center">
            <Grid size={{ xs: 12, sm: 3 }}>
              <FormControl fullWidth size="small">
                <InputLabel>Type</InputLabel>
                <Select
                  value={newStepType}
                  onChange={e => setNewStepType(e.target.value as 'text' | 'key')}
                  label="Type"
                >
                  <MenuItem value="text">Text</MenuItem>
                  <MenuItem value="key">Special Key</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            {newStepType === 'text' ? (
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField
                  label="Text to type"
                  value={newStepContent}
                  onChange={e => setNewStepContent(e.target.value)}
                  fullWidth
                  size="small"
                  placeholder="Enter text to type..."
                />
              </Grid>
            ) : (
              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel>Special Key</InputLabel>
                  <Select
                    value={selectedSpecialKey}
                    onChange={e => setSelectedSpecialKey(e.target.value)}
                    label="Special Key"
                  >
                    {Object.entries(SPECIAL_KEYS).map(([key, value]) => (
                      <MenuItem key={key} value={key}>
                        {key} ({value})
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
            )}

            <Grid size={{ xs: 12, sm: 3 }}>
              <Button
                variant="contained"
                onClick={onAddSequenceStep}
                disabled={newStepType === 'text' && !newStepContent.trim()}
                startIcon={<Add />}
                fullWidth
              >
                Add Step
              </Button>
            </Grid>
          </Grid>
        </Paper>

        {/* Sequence Display */}
        {keyboardSequence.length > 0 ? (
          <Paper sx={{ p: 2, mb: 2 }}>
            <Box
              sx={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                mb: 2,
              }}
            >
              <Typography variant="subtitle2">
                Current Sequence ({keyboardSequence.length} steps)
              </Typography>
              <Box>
                <Button
                  variant="contained"
                  color="success"
                  onClick={onExecuteKeyboardSequence}
                  disabled={isExecutingSequence || isExecuting}
                  startIcon={isExecutingSequence ? <CircularProgress size={16} /> : <PlayArrow />}
                  sx={{ mr: 1 }}
                >
                  {isExecutingSequence ? 'Executing...' : 'Execute Sequence'}
                </Button>
                <Button
                  variant="outlined"
                  onClick={() => setKeyboardSequence([])}
                  disabled={isExecutingSequence}
                >
                  Clear All
                </Button>
              </Box>
            </Box>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              {keyboardSequence.map((step, index) => renderSequenceStep(step, index))}
            </Box>
          </Paper>
        ) : (
          <Paper sx={{ p: 3, textAlign: 'center', backgroundColor: 'grey.900' }}>
            <Typography variant="body2" color="text.secondary">
              No steps added yet. Use the form above to build your keyboard sequence.
            </Typography>
          </Paper>
        )}
      </AccordionDetails>
    </Accordion>
  );
}
