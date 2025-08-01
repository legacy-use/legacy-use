import { PlayArrow } from '@mui/icons-material';
import { Box, Button, Typography } from '@mui/material';
import { useState } from 'react';
import type {
  ActionStep,
  AnalyzeVideoAiAnalyzePostResult,
  Parameter,
  Session,
} from '../gen/endpoints';
import { importApiDefinition } from '../services/apiService';
import ActionStepCard from './InteractiveBuilderActionStepCard';
import ParameterCard from './InteractiveBuilderParameterCard';

export default function InteractiveBuilder({
  currentSession,
  analyzeResult,
}: {
  currentSession: Session;
  analyzeResult: AnalyzeVideoAiAnalyzePostResult;
}) {
  const [executeProgress, setExecuteProgress] = useState(false);
  const [actions, setActions] = useState<ActionStep[]>(analyzeResult?.actions ?? []);
  const [parameters, setParameters] = useState<Parameter[]>(analyzeResult?.parameters ?? []);

  const handleInteractiveExecute = async () => {
    setExecuteProgress(true);

    const timestamp = new Date().toISOString().split('.')[0];

    const prompt = analyzeResult.actions
      .map((action, index) => `Step ${index + 1}: ${action.title}\n${action.instruction}`)
      .join('---\n\n');

    const apiDefinition = await importApiDefinition({
      api_definition: {
        name: `interactive-${timestamp}`,
        description: `Interactive API definition from ${timestamp}`,
        prompt: prompt,
        prompt_cleanup: analyzeResult.prompt_cleanup,
        response_example: analyzeResult.response_example,
        parameters: parameters,
      },
    });

    console.log(apiDefinition.name);
    console.log(currentSession.id);

    setExecuteProgress(false);
  };

  const handleActionUpdate = (index: number, updatedAction: ActionStep) => {
    const newActions = [...actions];
    newActions[index] = updatedAction;
    setActions(newActions);
  };

  const handleParameterUpdate = (index: number, updatedParameter: Parameter) => {
    const newParameters = [...parameters];
    newParameters[index] = updatedParameter;
    setParameters(newParameters);
  };

  return (
    <Box>
      <Box
        sx={{
          mb: 2,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <Typography variant="h5">Actions</Typography>
        <Button
          variant="contained"
          color="success"
          startIcon={<PlayArrow />}
          onClick={handleInteractiveExecute}
          disabled={executeProgress}
        >
          {executeProgress ? 'Executing...' : 'Execute'}
        </Button>
      </Box>

      {actions.map((action, index) => (
        <ActionStepCard
          key={`${action.title}-${index}`}
          action={action}
          onUpdate={updatedAction => handleActionUpdate(index, updatedAction)}
        />
      ))}

      <Typography variant="h5" sx={{ mb: 2 }}>
        Parameters
      </Typography>
      {parameters.map((parameter, index) => (
        <ParameterCard
          key={`${parameter.name}-${index}`}
          parameter={parameter}
          onUpdate={updatedParameter => handleParameterUpdate(index, updatedParameter)}
        />
      ))}
    </Box>
  );
}
