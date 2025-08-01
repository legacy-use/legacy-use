import { keyframes } from '@emotion/react';
import { FiberManualRecord } from '@mui/icons-material';

// Keyframes for pulsing record dot
const pulse = keyframes`
  0% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.2);
    opacity: 0.7;
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
`;

export default function RecordIcon() {
  return (
    <FiberManualRecord
      sx={{
        animation: `${pulse} 1.5s ease-in-out infinite`,
        color: '#ff0000',
      }}
    />
  );
}
