import { ExpandMore, Keyboard, Timer } from '@mui/icons-material';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Grid,
  TextField,
  Typography,
} from '@mui/material';

interface KeyboardActionsProps {
  textInput: string;
  setTextInput: (text: string) => void;
  keyInput: string;
  setKeyInput: (key: string) => void;
  duration: number;
  setDuration: (duration: number) => void;
  isExecuting: boolean;
  onType: () => void;
  onKey: () => void;
  onHoldKey: () => void;
}

export default function KeyboardActions({
  textInput,
  setTextInput,
  keyInput,
  setKeyInput,
  duration,
  setDuration,
  isExecuting,
  onType,
  onKey,
  onHoldKey,
}: KeyboardActionsProps) {
  return (
    <Accordion>
      <AccordionSummary expandIcon={<ExpandMore />}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Keyboard />
          <Typography variant="h6">Keyboard Actions</Typography>
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        {/* Single Actions */}
        <Typography variant="subtitle1" gutterBottom>
          Single Actions
        </Typography>
        <Box sx={{ mb: 3 }}>
          <TextField
            label="Text to Type"
            value={textInput}
            onChange={e => setTextInput(e.target.value)}
            fullWidth
            multiline
            rows={2}
            sx={{ mb: 2 }}
          />
          <Button
            variant="outlined"
            onClick={onType}
            disabled={isExecuting || !textInput.trim()}
            startIcon={<Keyboard />}
            sx={{ mb: 2, mr: 2 }}
          >
            Type Text
          </Button>
        </Box>

        <Box sx={{ mb: 3 }}>
          <TextField
            label="Key Combination (e.g., ctrl+c, alt+tab, Enter)"
            value={keyInput}
            onChange={e => setKeyInput(e.target.value)}
            fullWidth
            sx={{ mb: 2 }}
          />
          <Grid container spacing={2}>
            <Grid size={{ xs: 6 }}>
              <Button
                variant="outlined"
                onClick={onKey}
                disabled={isExecuting || !keyInput.trim()}
                fullWidth
              >
                Press Key
              </Button>
            </Grid>
            <Grid size={{ xs: 6 }}>
              <Button
                variant="outlined"
                onClick={onHoldKey}
                disabled={isExecuting || !keyInput.trim()}
                fullWidth
                startIcon={<Timer />}
              >
                Hold Key ({duration}s)
              </Button>
            </Grid>
          </Grid>
        </Box>

        <TextField
          label="Duration (seconds)"
          type="number"
          value={duration}
          onChange={e => setDuration(parseFloat(e.target.value) || 1)}
          slotProps={{
            input: {
              inputProps: { min: 0.1, max: 10, step: 0.1 },
            },
          }}
          size="small"
          sx={{ width: 150, mb: 3 }}
        />
      </AccordionDetails>
    </Accordion>
  );
}
