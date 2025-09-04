import { Box, CircularProgress, Typography } from '@mui/material';

interface ExecutionStatusProps {
  isExecuting: boolean;
  isExecutingSequence: boolean;
}

export default function ExecutionStatus({
  isExecuting,
  isExecutingSequence,
}: ExecutionStatusProps) {
  if (!isExecuting && !isExecutingSequence) {
    return null;
  }

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mt: 3 }}>
      <CircularProgress size={20} />
      <Typography>
        {isExecutingSequence ? 'Executing keyboard sequence...' : 'Executing tool...'}
      </Typography>
    </Box>
  );
}
