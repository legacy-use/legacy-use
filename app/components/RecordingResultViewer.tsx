import { VideoFile } from '@mui/icons-material';
import { Box, Button, Popover } from '@mui/material';
import PopupState, { bindPopover, bindTrigger } from 'material-ui-popup-state';
import type { RecordingResultResponse } from '../gen/endpoints';

export default function RecordingResultViewer({
  recordingResult,
}: {
  recordingResult: RecordingResultResponse;
}) {
  return (
    <PopupState variant="popover" popupId="demo-popup-popover">
      {popupState => (
        <Box>
          <Button {...bindTrigger(popupState)}>
            <VideoFile />
          </Button>
          <Popover
            {...bindPopover(popupState)}
            anchorOrigin={{
              vertical: 'bottom',
              horizontal: 'left',
            }}
          >
            <video
              controls
              style={{ maxWidth: '100%', maxHeight: '200px' }}
              src={`data:video/mp4;base64,${recordingResult.base64_video}`}
            >
              <track kind="captions" srcLang="en" label="English captions" />
              Your browser does not support the video tag.
            </video>
          </Popover>
        </Box>
      )}
    </PopupState>
  );
}
