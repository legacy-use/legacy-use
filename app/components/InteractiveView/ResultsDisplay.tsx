import { Alert, Box, Card, CardContent, Paper, Typography } from '@mui/material';
import type { ToolResult } from './types';

interface ResultsDisplayProps {
  lastResult: ToolResult | null;
}

export default function ResultsDisplay({ lastResult }: ResultsDisplayProps) {
  if (!lastResult) {
    return null;
  }

  return (
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
  );
}
