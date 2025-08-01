import { Cancel, Circle, Replay, RestoreFromTrash } from '@mui/icons-material';
import { Alert, Box, Button, Card, CardContent, CircularProgress, Typography } from '@mui/material';
import { useContext, useState } from 'react';
import { useLocalStorage } from 'usehooks-ts';
import { SessionContext } from '../App';
import type { AnalyzeVideoAiAnalyzePostResult, RecordingResultResponse } from '../gen/endpoints';
import { analyzeVideo } from '../services/apiService';
import { base64ToVideoFile } from '../utils/video';
import InteractiveBuilder from './InteractiveBuilder';
import RecordingButton from './RecordingButton';
import RecordingResultViewer from './RecordingResultViewer';

export default function InteractiveSession() {
  const { currentSession } = useContext(SessionContext);

  // Recording state
  const [recordingResult, setRecordingResult] = useLocalStorage<null | RecordingResultResponse>(
    `recording-result-${currentSession?.id}`,
    null,
  );

  // Analyze state
  const [analyzeResult, setAnalyzeResult] = useLocalStorage<null | AnalyzeVideoAiAnalyzePostResult>(
    `analyze-result-${currentSession?.id}`,
    null,
  );
  const [analyzeError, setAnalyzeError] = useState<null | string>(null);
  const [analyzeProgress, setAnalyzeProgress] = useState(false);

  const handleAnalyzeRecording = async (recording: RecordingResultResponse) => {
    setAnalyzeProgress(true);
    setAnalyzeError(null);

    try {
      const videoFile = base64ToVideoFile(
        recording.base64_video,
        `recording_${recording.recording_id}.mp4`,
      );

      const analysisResult = await analyzeVideo(videoFile);

      setAnalyzeResult(analysisResult);
      setAnalyzeProgress(false);
      setAnalyzeError(null);
    } catch (err) {
      console.error('Error analyzing recording:', err);
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setAnalyzeError(`Failed to analyze recording: ${errorMessage}`);
      setAnalyzeProgress(false);
    }
  };

  const onRecordingStopped = (recordingResult: RecordingResultResponse) => {
    setRecordingResult(recordingResult);
    handleAnalyzeRecording(recordingResult);
  };

  if (!currentSession || currentSession.is_archived || currentSession.state !== 'ready') {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">
          Please select a session which is ready to use recording features.
        </Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Interactive Session
      </Typography>

      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Record your interactions to generate automation workflows and teach legacy-use your use
        cases.
      </Typography>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 2 }}>
            {analyzeResult ? (
              <>
                <Button
                  onClick={() => {
                    setRecordingResult(null);
                    setAnalyzeResult(null);
                  }}
                  variant="outlined"
                  color="warning"
                  startIcon={<RestoreFromTrash />}
                >
                  Start over
                </Button>
                <Button
                  onClick={() => {
                    if (recordingResult) {
                      setAnalyzeResult(null);
                      handleAnalyzeRecording(recordingResult);
                    }
                  }}
                  color="primary"
                  disabled={!recordingResult || analyzeProgress}
                  startIcon={analyzeProgress ? <CircularProgress size={16} /> : <Replay />}
                >
                  {analyzeProgress ? 'Re-analyzing...' : 'Analyze'}
                </Button>
              </>
            ) : recordingResult ? (
              <>
                <Button
                  variant="contained"
                  color="primary"
                  onClick={() => handleAnalyzeRecording(recordingResult)}
                  disabled={analyzeProgress}
                  startIcon={analyzeProgress ? <CircularProgress size={16} /> : <Circle />}
                >
                  {analyzeProgress ? 'Analyzing...' : 'Analyze'}
                </Button>
                <Button
                  color="warning"
                  onClick={() => {
                    setRecordingResult(null);
                    setAnalyzeError(null);
                    setAnalyzeProgress(false);
                  }}
                >
                  <Cancel />
                </Button>
              </>
            ) : (
              <RecordingButton
                sessionId={currentSession.id}
                onRecordingStopped={onRecordingStopped}
              />
            )}

            {recordingResult && <RecordingResultViewer recordingResult={recordingResult} />}
          </Box>
        </CardContent>
      </Card>

      {analyzeError && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {analyzeError}
        </Alert>
      )}

      {analyzeResult && (
        <InteractiveBuilder currentSession={currentSession} analyzeResult={analyzeResult} />
      )}
    </Box>
  );
}
