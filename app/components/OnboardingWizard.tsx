import {
  Box,
  Button,
  Dialog,
  DialogContent,
  Stack,
  Typography,
} from '@mui/material';
import { useMemo, useState } from 'react';

type OnboardingWizardProps = {
  open: boolean;
  onComplete: () => void;
  onSkip: () => void;
};

const OnboardingWizard = ({ open, onComplete, onSkip }: OnboardingWizardProps) => {
  const mediaStyles = {
    width: '100%',
    maxWidth: 420,
    borderRadius: 2,
    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.35)',
    objectFit: 'cover',
  } as const;

  const steps = useMemo(
    () => [
      {
        title: 'Welcome to Legacy Use',
        content: (
          <Stack spacing={2.5} alignItems="center" sx={{ maxWidth: 520, mx: 'auto' }}>
            <Typography variant="body1" fontWeight="bold">
              Legacy Use helps you automate workflows on any computer through a few core building blocks.
            </Typography>
            <Stack spacing={2}>
              <Box>
                <Typography variant="subtitle1" textAlign={'center'} fontWeight={600}>
                  🖥️ Target
                </Typography>
                <Typography variant="body2" color="text.secondary" textAlign={'center'}>
                  A computer you want to automate a workflow on.
                </Typography>
              </Box>
              <Box>
                <Typography variant="subtitle1" fontWeight={600} textAlign={'center'}>
                  ⚡ API
                </Typography>
                <Typography variant="body2" color="text.secondary" textAlign={'center'}>
                  A prompt describing the workflow you want to run.
                </Typography>
              </Box>
              <Box>
                <Typography variant="subtitle1" fontWeight={600} textAlign={'center'}>
                  🗂️ Session
                </Typography>
                <Typography variant="body2" color="text.secondary" textAlign={'center'}>
                  An instance of legacy-use running on a target.
                </Typography>
              </Box>
              <Box>
                <Typography variant="subtitle1" fontWeight={600} textAlign={'center'}>
                  🏃 Job
                </Typography>
                <Typography variant="body2" color="text.secondary" textAlign={'center'}>
                  A running execution of an API on a session.
                </Typography>
              </Box>
            </Stack>
          </Stack>
        ),
      },
      {
        title: 'Setting Up Your First Target',
        content: (
          <Stack
            spacing={{ xs: 2.5, md: 4 }}
            direction={{ xs: 'column', md: 'row' }}
            alignItems={{ xs: 'center', md: 'flex-start' }}
            sx={{ maxWidth: 920, mx: 'auto', width: '100%' }}
          >
            <Stack spacing={1.5} sx={{ flex: 1, width: '100%' }}>
              <Typography variant="body1">
                Targets need remote access configured so legacy-use can operate them securely.
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Capture these details when you create a target:
              </Typography>
              <Stack
                component="ul"
                spacing={1}
                sx={{
                  pl: 2,
                  m: 0,
                  listStyleType: 'disc',
                  '& > li': { display: 'list-item' },
                }}
              >
                <Typography component="li" variant="body2" color="text.secondary">
                  Name – add whatever label helps you recognize the machine.
                </Typography>
                <Typography component="li" variant="body2" color="text.secondary">
                  Type – select the screen sharing protocol, and note if it is paired with a VPN.
                </Typography>
                <Typography component="li" variant="body2" color="text.secondary">
                  VPN Config – include details such as your Tailscale auth key when you connect via VPN.
                </Typography>
                <Typography component="li" variant="body2" color="text.secondary">
                  VNC/RDP Username – provide the username required by the screen sharing protocol.
                </Typography>
                <Typography component="li" variant="body2" color="text.secondary">
                  VNC/RDP Password – enter the password the protocol uses.
                </Typography>
                <Typography component="li" variant="body2" color="text.secondary">
                  Width/Height – specify the screen resolution exposed over VNC or RDP.
                </Typography>
              </Stack>
              <Stack spacing={1.5} pt={4}>
                <Typography variant="body2" color="text.secondary">
                  These guides show you how to setup a target with VNC and Tailscale:
                </Typography>
                <Stack spacing={1.5} direction={{ xs: 'column', sm: 'row' }} flexWrap="wrap" useFlexGap>
                  <Button
                    component="a"
                    href="https://docs.google.com/document/d/14FuYaEbZLvMHW0FzXbrlaPgjwleD_kTB9ATG5krFlDU/"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Installing UltraVNC
                  </Button>
                  <Button
                    component="a"
                    href="https://docs.google.com/document/d/1s-9Qc75tlVaWu1sCExr5-WTUgrRB4hCJFYSYiV_Wp_0/"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Setting up Tailscale
                  </Button>
                </Stack>
              </Stack>
            </Stack>
            <Box
              component="img"
              src="https://onboarding-gif.s3.eu-central-1.amazonaws.com/Target.gif"
              alt="Target setup walkthrough"
              sx={{ ...mediaStyles, alignSelf: { xs: 'center', md: 'flex-start' } }}
            />
          </Stack>
        ),
      },
      {
        title: 'Creating Your First API',
        content: (
          <Stack
            spacing={{ xs: 2.5, md: 4 }}
            direction={{ xs: 'column', md: 'row' }}
            alignItems={{ xs: 'center', md: 'flex-start' }}
            sx={{ maxWidth: 920, mx: 'auto', width: '100%' }}
          >
            <Stack spacing={1.5} sx={{ flex: 1, width: '100%' }}>
              <Typography variant="body1">
                APIs define what should happen when your automation runs.
              </Typography>
              <Stack spacing={1.5}>
                <Box>
                  <Typography variant="subtitle1" fontWeight={600}>
                    Parameters
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Insert dynamic values with {'{{parameter_name}}'} placeholders.
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle1" fontWeight={600}>
                    Response Example
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Describe the structure of the data you expect back.
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle1" fontWeight={600}>
                    Prompt
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Provide step-by-step instructions. Follow HOW_TO_PROMPT guidelines.
                  </Typography>
                </Box>
              </Stack>
              <Box>
                <Typography variant="subtitle2" fontWeight={600}>
                  Prompt best practices
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Keep one action per step, describe expected UI before actions, and prefer keyboard
                  shortcuts when possible.
                </Typography>
              </Box>
            </Stack>
            <Box
              component="img"
              src="https://onboarding-gif.s3.eu-central-1.amazonaws.com/API.gif"
              alt="API creation walkthrough"
              sx={{ ...mediaStyles, alignSelf: { xs: 'center', md: 'flex-start' } }}
            />
          </Stack>
        ),
      },
      {
        title: 'Triggering Your API',
        content: (
          <Stack
            spacing={{ xs: 2.5, md: 4 }}
            direction={{ xs: 'column', md: 'row' }}
            alignItems={{ xs: 'center', md: 'flex-start' }}
            sx={{ maxWidth: 920, mx: 'auto', width: '100%' }}
          >
            <Stack spacing={1.5} sx={{ flex: 1, width: '100%' }}>
              <Typography variant="body1">
                Run your API once you have a target and prompt ready.
              </Typography>
              <Stack spacing={1.5}>
                <Typography variant="body2" color="text.secondary">
                  1. Open the APIs page and choose your API.
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  2. Select a target from the dropdown.
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  3. Click execute to start a job.
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  4. The job runs on a session instance on that target.
                </Typography>
              </Stack>
              <Typography variant="body1" fontWeight={600}>
                You're all set! Start automating your workflows.
              </Typography>
            </Stack>
            <Box
              component="img"
              src="https://onboarding-gif.s3.eu-central-1.amazonaws.com/Job.gif"
              alt="Job execution walkthrough"
              sx={{ ...mediaStyles, alignSelf: { xs: 'center', md: 'flex-start' } }}
            />
          </Stack>
        ),
      },
    ],
    [],
  );

  const [activeStep, setActiveStep] = useState(0);
  const totalSteps = steps.length;
  const isLastStep = activeStep === totalSteps - 1;

  const handleNext = () => {
    if (isLastStep) {
      onComplete();
      setActiveStep(0);
      return;
    }
    setActiveStep(prev => Math.min(prev + 1, totalSteps - 1));
  };

  const handleBack = () => {
    setActiveStep(prev => Math.max(prev - 1, 0));
  };

  const handleSkip = () => {
    onSkip();
    setActiveStep(0);
  };

  return (
    <Dialog
      open={open}
      fullScreen
      onClose={(_, reason) => {
        if (reason === 'backdropClick') {
          return;
        }
        handleSkip();
      }}
      slotProps={{
        paper: {
          sx: {
            backgroundColor: '#121212',
            color: 'common.white',
          },
        },
      }}
    >
      <DialogContent
        sx={{
          display: 'flex',
          flexDirection: 'column',
          minHeight: '100vh',
          p: { xs: 3, sm: 6 },
          background: 'radial-gradient(circle at top, rgba(255,255,255,0.08), transparent 55%)',
        }}
      >
        <Stack spacing={3.5} sx={{ flexGrow: 1 }}>
          <Box textAlign="center">
            <Typography variant="overline" color="text.secondary">
              Step {activeStep + 1} of {totalSteps}
            </Typography>
            <Typography variant="h4" sx={{ mt: 1, fontWeight: 600 }}>
              {steps[activeStep].title}
            </Typography>
          </Box>
          <Box
            sx={{
              flexGrow: 1,
              backgroundColor: 'rgba(20, 24, 29, 0.92)',
              borderRadius: 3,
              // maxWidth: '75%',
              p: { xs: 3, sm: 4 },
              overflowY: 'auto',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              boxShadow: '0 20px 45px rgba(0, 0, 0, 0.35)',
            }}
          >
            {steps[activeStep].content}
          </Box>
        </Stack>

        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 3 }}>
          <Button color="inherit" onClick={handleSkip} sx={{ color: 'text.secondary' }}>
            Skip Wizard
          </Button>
          <Stack direction="row" spacing={2}>
            <Button
              onClick={handleBack}
              disabled={activeStep === 0}
              variant="outlined"
              sx={{ minWidth: 120 }}
            >
              Previous
            </Button>
            <Button
              variant="contained"
              color="primary"
              onClick={handleNext}
              sx={{ minWidth: 140 }}
            >
              {isLastStep ? 'Get Started' : 'Next'}
            </Button>
          </Stack>
        </Stack>
      </DialogContent>
    </Dialog>
  );
};

export default OnboardingWizard;
