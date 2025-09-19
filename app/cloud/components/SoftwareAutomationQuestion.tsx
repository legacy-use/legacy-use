import { Box, Button, Stack, TextField, Typography } from '@mui/material';

type SoftwareAutomationQuestionProps = {
  value: string;
  onValueChange: (value: string) => void;
  onSave: () => void | Promise<void>;
  isSaving: boolean;
};

export function SoftwareAutomationQuestion({
  value,
  onValueChange,
  onSave,
  isSaving,
}: SoftwareAutomationQuestionProps) {
  const isDisabled = !value.trim() || isSaving;

  return (
    <Box
      sx={{
        p: 3,
        borderRadius: 2,
        background: 'white',
        border: '1px solid',
        borderColor: 'divider',
        boxShadow: '0 6px 20px rgba(0,0,0,0.08)',
      }}
    >
      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="h6">What software would you like to automate?</Typography>
      </Stack>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
        <TextField
          fullWidth
          placeholder="e.g., DATEV, SAP, Lexware, Navision, ..."
          variant="outlined"
          value={value}
          onChange={event => onValueChange(event.target.value)}
        />
        <Button variant="contained" disabled={isDisabled} onClick={() => void onSave()}>
          {isSaving ? 'Saving...' : 'Save'}
        </Button>
      </Stack>
    </Box>
  );
}
