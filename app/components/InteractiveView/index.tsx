import { Alert, Box, Chip, Typography } from '@mui/material';
import { useContext, useState } from 'react';
import { SessionContext } from '../../App';
import { apiClient } from '../../services/apiService';
import ExecutionStatus from './ExecutionStatus';
import KeyboardActions from './KeyboardActions';
import KeyboardSequences from './KeyboardSequences';
import MouseActions from './MouseActions';
import MouseCoordinates from './MouseCoordinates';
import ResultsDisplay from './ResultsDisplay';
import ScreenActions from './ScreenActions';
import type { CoordinateInput, KeyboardSequenceStep, ToolResult } from './types';
import { SPECIAL_KEYS } from './types';

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
  const [keyboardSequence, setKeyboardSequence] = useState<KeyboardSequenceStep[]>([]);
  const [newStepType, setNewStepType] = useState<'text' | 'key'>('text');
  const [newStepContent, setNewStepContent] = useState('');
  const [selectedSpecialKey, setSelectedSpecialKey] = useState('tab');
  const [isExecutingSequence, setIsExecutingSequence] = useState(false);

  if (!currentSession || currentSession.is_archived || currentSession.state !== 'ready') {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">
          Please select a session which is ready to use the interactive tools.
        </Alert>
      </Box>
    );
  }

  const executeComputerTool = async (action: string, params: Record<string, unknown> = {}) => {
    if (!currentSession?.container_ip) {
      setLastResult({ error: 'No container IP available' });
      return;
    }

    setIsExecuting(true);
    setLastResult(null);

    try {
      const response = await apiClient.post(`/sessions/${currentSession.id}/tools/${action}`, {
        ...params,
        api_type: 'computer_20250124',
      });

      setLastResult(response.data);
    } catch (error) {
      console.error('Error executing computer tool:', error);
      setLastResult({
        error: error.response?.data?.message || error.message || 'Unknown error occurred',
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
      scroll_amount: scrollAmount,
    });
  };

  const handleWait = () => {
    executeComputerTool('wait', { duration });
  };

  const generateId = () => {
    return Math.random().toString(36).substring(2) + Date.now().toString(36);
  };

  const addSequenceStep = () => {
    if (!newStepContent.trim() && newStepType === 'text') return;

    const content = newStepType === 'key' ? selectedSpecialKey : newStepContent;
    const newStep: KeyboardSequenceStep = {
      id: generateId(),
      type: newStepType,
      content: content,
      delay: 0.1,
    };

    setKeyboardSequence([...keyboardSequence, newStep]);
    setNewStepContent('');
  };

  const removeSequenceStep = (id: string) => {
    setKeyboardSequence(keyboardSequence.filter(step => step.id !== id));
  };

  const executeSequenceStep = async (action: string, params: Record<string, unknown> = {}) => {
    if (!currentSession?.container_ip) {
      throw new Error('No container IP available');
    }

    try {
      const response = await apiClient.post(`/sessions/${currentSession.id}/tools/${action}`, {
        ...params,
        api_type: 'computer_20250124',
      });
      return response.data;
    } catch (error) {
      console.error('Error executing computer tool:', error);
      throw error;
    }
  };

  const executeKeyboardSequence = async () => {
    if (keyboardSequence.length === 0) return;

    setIsExecutingSequence(true);
    setLastResult(null);

    try {
      for (let i = 0; i < keyboardSequence.length; i++) {
        const step = keyboardSequence[i];

        let result: ToolResult;
        if (step.type === 'text') {
          result = await executeSequenceStep('type', { text: step.content });
        } else {
          const keyValue = SPECIAL_KEYS[step.content as keyof typeof SPECIAL_KEYS] || step.content;
          result = await executeSequenceStep('key', { text: keyValue });
        }

        // Update last result with the final step's result
        if (i === keyboardSequence.length - 1) {
          setLastResult(result);
        }

        const delay = step.delay ?? 0.1;

        // Add delay between steps
        if (i < keyboardSequence.length - 1 && delay) {
          await new Promise(resolve => setTimeout(resolve, delay * 1000));
        }
      }
    } catch (error) {
      console.error('Error executing keyboard sequence:', error);
      setLastResult({
        error: error.response?.data?.message || error.message || 'Unknown error occurred',
      });
    } finally {
      setIsExecutingSequence(false);
    }
  };

  const renderSequenceStep = (step: KeyboardSequenceStep, index: number) => {
    if (step.type === 'text') {
      return (
        <Chip
          key={step.id}
          label={`${index + 1}. "${step.content}"`}
          variant="outlined"
          color="primary"
          onDelete={() => removeSequenceStep(step.id)}
          sx={{ m: 0.5 }}
        />
      );
    } else {
      return (
        <Chip
          key={step.id}
          label={`${index + 1}. ${step.content}`}
          variant="filled"
          color="secondary"
          onDelete={() => removeSequenceStep(step.id)}
          sx={{
            m: 0.5,
            fontFamily: 'monospace',
            backgroundColor: 'secondary.dark',
            '&:hover': {
              backgroundColor: 'secondary.main',
            },
          }}
        />
      );
    }
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Interactive Computer Tools
      </Typography>

      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Control the remote computer directly using individual computer use tools.
      </Typography>

      <MouseCoordinates coordinate={coordinate} setCoordinate={setCoordinate} />

      <MouseActions
        isExecuting={isExecuting}
        onLeftClick={handleLeftClick}
        onRightClick={handleRightClick}
        onDoubleClick={handleDoubleClick}
        onTripleClick={handleTripleClick}
        onMouseMove={handleMouseMove}
        onLeftClickDrag={handleLeftClickDrag}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
      />

      <KeyboardActions
        textInput={textInput}
        setTextInput={setTextInput}
        keyInput={keyInput}
        setKeyInput={setKeyInput}
        duration={duration}
        setDuration={setDuration}
        isExecuting={isExecuting}
        onType={handleType}
        onKey={handleKey}
        onHoldKey={handleHoldKey}
      />

      <KeyboardSequences
        keyboardSequence={keyboardSequence}
        setKeyboardSequence={setKeyboardSequence}
        newStepType={newStepType}
        setNewStepType={setNewStepType}
        newStepContent={newStepContent}
        setNewStepContent={setNewStepContent}
        selectedSpecialKey={selectedSpecialKey}
        setSelectedSpecialKey={setSelectedSpecialKey}
        isExecutingSequence={isExecutingSequence}
        isExecuting={isExecuting}
        onAddSequenceStep={addSequenceStep}
        onExecuteKeyboardSequence={executeKeyboardSequence}
        onRemoveSequenceStep={removeSequenceStep}
        renderSequenceStep={renderSequenceStep}
      />

      <ScreenActions
        scrollDirection={scrollDirection}
        setScrollDirection={setScrollDirection}
        scrollAmount={scrollAmount}
        setScrollAmount={setScrollAmount}
        duration={duration}
        isExecuting={isExecuting}
        onScreenshot={handleScreenshot}
        onScroll={handleScroll}
        onWait={handleWait}
      />

      <ExecutionStatus isExecuting={isExecuting} isExecutingSequence={isExecutingSequence} />

      <ResultsDisplay lastResult={lastResult} />
    </Box>
  );
};

export default InteractiveView;
