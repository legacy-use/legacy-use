import { PlayArrow } from '@mui/icons-material';
import { Box, Button, Typography } from '@mui/material';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type {
  ActionStep,
  AnalyzeVideoTeachingModeAnalyzeVideoPostResult,
  JobCreateParameters,
  Parameter,
  Session,
} from '../gen/endpoints';
import { createJob, importApiDefinition } from '../services/apiService';
import ActionStepCard from './TeachingModeActionCard';
import ParameterCard from './TeachingModeParameterCard';

export default function TeachingModeBuilder({
  currentSession,
  analyzeResult,
}: {
  currentSession: Session;
  analyzeResult: AnalyzeVideoTeachingModeAnalyzeVideoPostResult;
}) {
  const navigate = useNavigate();
  const [executeProgress, setExecuteProgress] = useState(false);
  const [actions, setActions] = useState<ActionStep[]>(analyzeResult?.actions ?? []);
  const [parameters, setParameters] = useState<Parameter[]>(analyzeResult?.parameters ?? []);

  const handleTeachingExecute = async () => {
    setExecuteProgress(true);

    const timestamp = new Date().toISOString().split('.')[0];

    const prompt = analyzeResult.actions
      .map((action, index) => `Step ${index + 1}: ${action.title}\n${action.instruction}`)
      .join('\n---\n\n');

    const apiDefinition = await importApiDefinition({
      name: `teaching-${timestamp}`,
      description: `Teaching API definition from ${timestamp}`,
      prompt: prompt,
      prompt_cleanup: analyzeResult.prompt_cleanup,
      response_example: analyzeResult.response_example,
      parameters: parameters,
    });

    const result = await createJob(currentSession.target_id, {
      api_name: apiDefinition.name,
      parameters: parameters.reduce((acc, parameter) => {
        acc[parameter.name] = parameter.default ?? '';
        return acc;
      }, {} as JobCreateParameters),
    });

    // Navigate to the job details page with the logs tab active
    navigate(`/jobs/${currentSession.target_id}/${result.id}`);

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
          onClick={handleTeachingExecute}
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
