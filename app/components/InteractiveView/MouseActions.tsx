import { ExpandMore, Mouse, SwipeUp, TouchApp } from '@mui/icons-material';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Grid,
  Typography,
} from '@mui/material';

interface MouseActionsProps {
  isExecuting: boolean;
  onLeftClick: () => void;
  onRightClick: () => void;
  onDoubleClick: () => void;
  onTripleClick: () => void;
  onMouseMove: () => void;
  onLeftClickDrag: () => void;
  onMouseDown: () => void;
  onMouseUp: () => void;
}

export default function MouseActions({
  isExecuting,
  onLeftClick,
  onRightClick,
  onDoubleClick,
  onTripleClick,
  onMouseMove,
  onLeftClickDrag,
  onMouseDown,
  onMouseUp,
}: MouseActionsProps) {
  return (
    <Accordion defaultExpanded>
      <AccordionSummary expandIcon={<ExpandMore />}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Mouse />
          <Typography variant="h6">Mouse Actions</Typography>
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        <Grid container spacing={2}>
          <Grid size={{ xs: 6, sm: 4 }}>
            <Button
              variant="outlined"
              fullWidth
              onClick={onLeftClick}
              disabled={isExecuting}
              startIcon={<TouchApp />}
            >
              Left Click
            </Button>
          </Grid>
          <Grid size={{ xs: 6, sm: 4 }}>
            <Button
              variant="outlined"
              fullWidth
              onClick={onRightClick}
              disabled={isExecuting}
              startIcon={<TouchApp />}
            >
              Right Click
            </Button>
          </Grid>
          <Grid size={{ xs: 6, sm: 4 }}>
            <Button
              variant="outlined"
              fullWidth
              onClick={onDoubleClick}
              disabled={isExecuting}
              startIcon={<TouchApp />}
            >
              Double Click
            </Button>
          </Grid>
          <Grid size={{ xs: 6, sm: 4 }}>
            <Button
              variant="outlined"
              fullWidth
              onClick={onTripleClick}
              disabled={isExecuting}
              startIcon={<TouchApp />}
            >
              Triple Click
            </Button>
          </Grid>
          <Grid size={{ xs: 6, sm: 4 }}>
            <Button
              variant="outlined"
              fullWidth
              onClick={onMouseMove}
              disabled={isExecuting}
              startIcon={<Mouse />}
            >
              Move Mouse
            </Button>
          </Grid>
          <Grid size={{ xs: 6, sm: 4 }}>
            <Button
              variant="outlined"
              fullWidth
              onClick={onLeftClickDrag}
              disabled={isExecuting}
              startIcon={<SwipeUp />}
            >
              Click & Drag
            </Button>
          </Grid>
          <Grid size={{ xs: 6, sm: 4 }}>
            <Button variant="outlined" fullWidth onClick={onMouseDown} disabled={isExecuting}>
              Mouse Down
            </Button>
          </Grid>
          <Grid size={{ xs: 6, sm: 4 }}>
            <Button variant="outlined" fullWidth onClick={onMouseUp} disabled={isExecuting}>
              Mouse Up
            </Button>
          </Grid>
        </Grid>
      </AccordionDetails>
    </Accordion>
  );
}
