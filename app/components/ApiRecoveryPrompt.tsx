import { Box, Button, TextField, Typography } from '@mui/material';
import { useEffect, useState } from 'react';
import { getApiDefinitionDetails, updateApiDefinition } from '../services/apiService';

interface ApiRecoveryPromptProps {
  apiName: string;
  isArchived: boolean;
}

const ApiRecoveryPrompt = ({ apiName, isArchived }: ApiRecoveryPromptProps) => {
  const [recoveryPrompt, setRecoveryPrompt] = useState('');

  useEffect(() => {
    const loadPrompt = async () => {
      try {
        const data: any = await getApiDefinitionDetails(apiName);
        setRecoveryPrompt(data?.recovery_prompt || '');
      } catch (err) {
        console.error('Error loading recovery prompt:', err);
      }
    };
    loadPrompt();
  }, [apiName]);

  const handleSave = async () => {
    try {
      await updateApiDefinition(apiName, { recovery_prompt: recoveryPrompt } as any);
    } catch (err) {
      console.error('Error saving recovery prompt:', err);
    }
  };

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Recovery Prompt
      </Typography>
      <TextField
        label="Recovery Prompt"
        fullWidth
        multiline
        rows={6}
        value={recoveryPrompt}
        onChange={e => setRecoveryPrompt(e.target.value)}
        margin="normal"
        disabled={isArchived}
      />
      {!isArchived && (
        <Button variant="outlined" sx={{ mt: 2 }} onClick={handleSave}>
          Save Recovery Prompt
        </Button>
      )}
    </Box>
  );
};

export default ApiRecoveryPrompt;
