import { CropFree, ExpandMore, SwipeUp, Timer } from '@mui/icons-material';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
} from '@mui/material';

interface ScreenActionsProps {
  scrollDirection: 'up' | 'down' | 'left' | 'right';
  setScrollDirection: (direction: 'up' | 'down' | 'left' | 'right') => void;
  scrollAmount: number;
  setScrollAmount: (amount: number) => void;
  duration: number;
  isExecuting: boolean;
  onScreenshot: () => void;
  onScroll: () => void;
  onWait: () => void;
}

export default function ScreenActions({
  scrollDirection,
  setScrollDirection,
  scrollAmount,
  setScrollAmount,
  duration,
  isExecuting,
  onScreenshot,
  onScroll,
  onWait,
}: ScreenActionsProps) {
  return (
    <Accordion>
      <AccordionSummary expandIcon={<ExpandMore />}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CropFree />
          <Typography variant="h6">Screen Actions</Typography>
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid size={{ xs: 12, sm: 6 }}>
            <Button
              variant="contained"
              fullWidth
              onClick={onScreenshot}
              disabled={isExecuting}
              startIcon={<CropFree />}
            >
              Take Screenshot
            </Button>
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <Button
              variant="outlined"
              fullWidth
              onClick={onWait}
              disabled={isExecuting}
              startIcon={<Timer />}
            >
              Wait ({duration}s)
            </Button>
          </Grid>
        </Grid>

        <Box>
          <Typography variant="subtitle2" gutterBottom>
            Scroll
          </Typography>
          <Grid container spacing={2} alignItems="center">
            <Grid size={{ xs: 6, sm: 4 }}>
              <FormControl fullWidth size="small">
                <InputLabel>Direction</InputLabel>
                <Select
                  value={scrollDirection}
                  onChange={e =>
                    setScrollDirection(e.target.value as 'up' | 'down' | 'left' | 'right')
                  }
                  label="Direction"
                >
                  <MenuItem value="up">Up</MenuItem>
                  <MenuItem value="down">Down</MenuItem>
                  <MenuItem value="left">Left</MenuItem>
                  <MenuItem value="right">Right</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid size={{ xs: 6, sm: 4 }}>
              <TextField
                label="Amount"
                type="number"
                value={scrollAmount}
                onChange={e => setScrollAmount(parseInt(e.target.value, 10) || 1)}
                slotProps={{
                  input: {
                    inputProps: { min: 1, max: 10 },
                  },
                }}
                size="small"
                fullWidth
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <Button
                variant="outlined"
                fullWidth
                onClick={onScroll}
                disabled={isExecuting}
                startIcon={<SwipeUp />}
              >
                Scroll
              </Button>
            </Grid>
          </Grid>
        </Box>
      </AccordionDetails>
    </Accordion>
  );
}
