import { Box, TextField, Typography } from '@mui/material';
import type { ChangeEvent } from 'react';

type ApiRecoveryPromptProps = {
  recoveryPrompt: string;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
  isArchived: boolean;
};

const ApiRecoveryPrompt = ({ recoveryPrompt, onChange, isArchived }: ApiRecoveryPromptProps) => {
  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Recovery Prompt
      </Typography>
      <TextField
        label="Recovery Prompt"
        fullWidth
        multiline
        rows={4}
        value={recoveryPrompt}
        onChange={onChange}
        margin="normal"
        helperText="Instructions to run if the API call fails"
        disabled={isArchived}
      />
    </Box>
  );
};

export default ApiRecoveryPrompt;
