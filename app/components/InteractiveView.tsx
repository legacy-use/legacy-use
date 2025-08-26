import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  Paper,
  TextField,
  Typography,
  Alert,
  CircularProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import {
  ExpandMore,
  Mouse,
  Keyboard,
  CropFree,
  TouchApp,
  SwipeUp,
  Timer,
} from '@mui/icons-material';
import { useContext, useState } from 'react';
import { SessionContext } from '../App';
import { apiClient } from '../services/apiService';

interface ToolResult {
  output?: string;
  error?: string;
  base64_image?: string;
}

interface CoordinateInput {
  x: number;
  y: number;
}

const InteractiveView = () => {
  const { currentSession } = useContext(SessionContext);
  const [isExecuting, setIsExecuting] = useState(false);
  const [lastResult, setLastResult] = useState<ToolResult | null>(null);
  const [coordinate, setCoordinate] = useState<CoordinateInput>({ x: 0, y: 0 });
  const [textInput, setTextInput] = useState('');
  const [keyInput, setKeyInput] = useState('');
  const [scrollDirection, setScrollDirection] = useState<'up' | 'down' | 'left' | 'right'>('up');
  const [scrollAmount, setScrollAmount] = useState(3);
  const [duration, setDuration] = useState(1);

  if (!currentSession || currentSession.is_archived || currentSession.state !== 'ready') {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">
          Please select a session which is ready to use the interactive tools.
        </Alert>
      </Box>
    );
  }

  const executeComputerTool = async (action: string, params: Record<string, any> = {}) => {
    if (!currentSession?.container_ip) {
      setLastResult({ error: 'No container IP available' });
      return;
    }

    setIsExecuting(true);
    setLastResult(null);

    try {
      // Call the new computer tool endpoint
      const response = await apiClient.post(
        `/sessions/${currentSession.id}/tools/${action}`,
        {
          ...params,
          api_type: 'computer_20250124', // Use the latest version
        }
      );

      setLastResult(response.data);
    } catch (error: any) {
      console.error('Error executing computer tool:', error);
      setLastResult({
        error: error.response?.data?.message || error.message || 'Unknown error occurred'
      });
    } finally {
      setIsExecuting(false);
    }
  };

  const handleScreenshot = () => {
    executeComputerTool('screenshot');
  };

  const handleLeftClick = () => {
    executeComputerTool('left_click', { coordinate: [coordinate.x, coordinate.y] });
  };

  const handleRightClick = () => {
    executeComputerTool('right_click', { coordinate: [coordinate.x, coordinate.y] });
  };

  const handleDoubleClick = () => {
    executeComputerTool('double_click', { coordinate: [coordinate.x, coordinate.y] });
  };

  const handleTripleClick = () => {
    executeComputerTool('triple_click', { coordinate: [coordinate.x, coordinate.y] });
  };

  const handleMouseMove = () => {
    executeComputerTool('mouse_move', { coordinate: [coordinate.x, coordinate.y] });
  };

  const handleLeftClickDrag = () => {
    executeComputerTool('left_click_drag', { coordinate: [coordinate.x, coordinate.y] });
  };

  const handleMouseDown = () => {
    executeComputerTool('left_mouse_down', { coordinate: [coordinate.x, coordinate.y] });
  };

  const handleMouseUp = () => {
    executeComputerTool('left_mouse_up', { coordinate: [coordinate.x, coordinate.y] });
  };

  const handleType = () => {
    if (!textInput.trim()) return;
    executeComputerTool('type', { text: textInput });
  };

  const handleKey = () => {
    if (!keyInput.trim()) return;
    executeComputerTool('key', { text: keyInput });
  };

  const handleHoldKey = () => {
    if (!keyInput.trim()) return;
    executeComputerTool('hold_key', { text: keyInput, duration });
  };

  const handleScroll = () => {
    executeComputerTool('scroll', { 
      scroll_direction: scrollDirection, 
      scroll_amount: scrollAmount 
    });
  };

  const handleWait = () => {
    executeComputerTool('wait', { duration });
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Interactive Computer Tools
      </Typography>

      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Control the remote computer directly using individual computer use tools.
      </Typography>

      {/* Coordinate Input */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Mouse Coordinates
          </Typography>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={6}>
              <TextField
                label="X Coordinate"
                type="number"
                value={coordinate.x}
                onChange={(e) => setCoordinate({ ...coordinate, x: parseInt(e.target.value) || 0 })}
                fullWidth
                size="small"
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                label="Y Coordinate"
                type="number"
                value={coordinate.y}
                onChange={(e) => setCoordinate({ ...coordinate, y: parseInt(e.target.value) || 0 })}
                fullWidth
                size="small"
              />
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Mouse Actions */}
      <Accordion defaultExpanded>
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Mouse />
            <Typography variant="h6">Mouse Actions</Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={2}>
            <Grid item xs={6} sm={4}>
              <Button
                variant="outlined"
                fullWidth
                onClick={handleLeftClick}
                disabled={isExecuting}
                startIcon={<TouchApp />}
              >
                Left Click
              </Button>
            </Grid>
            <Grid item xs={6} sm={4}>
              <Button
                variant="outlined"
                fullWidth
                onClick={handleRightClick}
                disabled={isExecuting}
                startIcon={<TouchApp />}
              >
                Right Click
              </Button>
            </Grid>
            <Grid item xs={6} sm={4}>
              <Button
                variant="outlined"
                fullWidth
                onClick={handleDoubleClick}
                disabled={isExecuting}
                startIcon={<TouchApp />}
              >
                Double Click
              </Button>
            </Grid>
            <Grid item xs={6} sm={4}>
              <Button
                variant="outlined"
                fullWidth
                onClick={handleTripleClick}
                disabled={isExecuting}
                startIcon={<TouchApp />}
              >
                Triple Click
              </Button>
            </Grid>
            <Grid item xs={6} sm={4}>
              <Button
                variant="outlined"
                fullWidth
                onClick={handleMouseMove}
                disabled={isExecuting}
                startIcon={<Mouse />}
              >
                Move Mouse
              </Button>
            </Grid>
            <Grid item xs={6} sm={4}>
              <Button
                variant="outlined"
                fullWidth
                onClick={handleLeftClickDrag}
                disabled={isExecuting}
                startIcon={<SwipeUp />}
              >
                Click & Drag
              </Button>
            </Grid>
            <Grid item xs={6} sm={4}>
              <Button
                variant="outlined"
                fullWidth
                onClick={handleMouseDown}
                disabled={isExecuting}
              >
                Mouse Down
              </Button>
            </Grid>
            <Grid item xs={6} sm={4}>
              <Button
                variant="outlined"
                fullWidth
                onClick={handleMouseUp}
                disabled={isExecuting}
              >
                Mouse Up
              </Button>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Keyboard Actions */}
      <Accordion>
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Keyboard />
            <Typography variant="h6">Keyboard Actions</Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ mb: 2 }}>
            <TextField
              label="Text to Type"
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              fullWidth
              multiline
              rows={2}
              sx={{ mb: 2 }}
            />
            <Button
              variant="outlined"
              onClick={handleType}
              disabled={isExecuting || !textInput.trim()}
              startIcon={<Keyboard />}
              sx={{ mb: 2, mr: 2 }}
            >
              Type Text
            </Button>
          </Box>

          <Box sx={{ mb: 2 }}>
            <TextField
              label="Key Combination (e.g., ctrl+c, alt+tab, Enter)"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              fullWidth
              sx={{ mb: 2 }}
            />
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Button
                  variant="outlined"
                  onClick={handleKey}
                  disabled={isExecuting || !keyInput.trim()}
                  fullWidth
                >
                  Press Key
                </Button>
              </Grid>
              <Grid item xs={6}>
                <Button
                  variant="outlined"
                  onClick={handleHoldKey}
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
            onChange={(e) => setDuration(parseFloat(e.target.value) || 1)}
            inputProps={{ min: 0.1, max: 10, step: 0.1 }}
            size="small"
            sx={{ width: 150 }}
          />
        </AccordionDetails>
      </Accordion>

      {/* Screen Actions */}
      <Accordion>
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CropFree />
            <Typography variant="h6">Screen Actions</Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={12} sm={6}>
              <Button
                variant="contained"
                fullWidth
                onClick={handleScreenshot}
                disabled={isExecuting}
                startIcon={<CropFree />}
              >
                Take Screenshot
              </Button>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Button
                variant="outlined"
                fullWidth
                onClick={handleWait}
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
              <Grid item xs={6} sm={4}>
                <FormControl fullWidth size="small">
                  <InputLabel>Direction</InputLabel>
                  <Select
                    value={scrollDirection}
                    onChange={(e) => setScrollDirection(e.target.value as any)}
                    label="Direction"
                  >
                    <MenuItem value="up">Up</MenuItem>
                    <MenuItem value="down">Down</MenuItem>
                    <MenuItem value="left">Left</MenuItem>
                    <MenuItem value="right">Right</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={6} sm={4}>
                <TextField
                  label="Amount"
                  type="number"
                  value={scrollAmount}
                  onChange={(e) => setScrollAmount(parseInt(e.target.value) || 1)}
                  inputProps={{ min: 1, max: 10 }}
                  size="small"
                  fullWidth
                />
              </Grid>
              <Grid item xs={12} sm={4}>
                <Button
                  variant="outlined"
                  fullWidth
                  onClick={handleScroll}
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

      {/* Execution Status */}
      {isExecuting && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mt: 3 }}>
          <CircularProgress size={20} />
          <Typography>Executing tool...</Typography>
        </Box>
      )}

      {/* Results */}
      {lastResult && (
        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Last Result
            </Typography>
            
            {lastResult.error && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {lastResult.error}
              </Alert>
            )}
            
            {lastResult.output && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Output:
                </Typography>
                <Paper sx={{ p: 2, bgcolor: 'grey.900' }}>
                  <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap' }}>
                    {lastResult.output}
                  </Typography>
                </Paper>
              </Box>
            )}
            
            {lastResult.base64_image && (
              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  Screenshot:
                </Typography>
                <Paper sx={{ p: 1, textAlign: 'center' }}>
                  <img
                    src={`data:image/png;base64,${lastResult.base64_image}`}
                    alt="Screenshot result"
                    style={{
                      maxWidth: '100%',
                      maxHeight: '400px',
                      objectFit: 'contain',
                    }}
                  />
                </Paper>
              </Box>
            )}
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

export default InteractiveView;
