import {
  CheckCircle as CheckCircleIcon,
  Close as CloseIcon,
  Email as EmailIcon,
  Key as KeyIcon,
  PlayArrow as PlayArrowIcon,
  Rocket as RocketIcon,
} from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Chip,
  Container,
  Dialog,
  DialogContent,
  Divider,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
} from '@mui/material';
import posthog from 'posthog-js';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getProviders, getTargets, updateProviderSettings } from '../services/apiService';

const OnboardingWizard = ({ open, onClose, onComplete }) => {
  const navigate = useNavigate();
  const [activeStep, setActiveStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [providers, setProviders] = useState([]);
  const [selectedProvider, setSelectedProvider] = useState('');
  const [signupCompleted, setSignupCompleted] = useState(false);
  const [activationCode, setActivationCode] = useState('');
  const [resendTimer, setResendTimer] = useState(0);
  const [targets, setTargets] = useState([]);

  // Signup form state
  const [signupData, setSignupData] = useState({
    email: '',
    description: '',
    referralCode: '',
  });

  // Provider configuration state
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [awsCredentials, setAwsCredentials] = useState({
    accessKeyId: '',
    secretAccessKey: '',
    region: 'us-east-1',
  });
  const [vertexCredentials, setVertexCredentials] = useState({
    projectId: '',
    region: 'us-central1',
  });

  const steps = ['Welcome', 'Get Started', 'Configure Provider', 'Run First Job'];

  // Timer effect for resend countdown
  useEffect(() => {
    let interval;
    if (resendTimer > 0) {
      interval = setInterval(() => {
        setResendTimer(prev => prev - 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [resendTimer]);

  const signupOrResend = async () => {
    // Start the resend timer (60 seconds)
    setResendTimer(60);

    const response = await fetch(`${import.meta.env.VITE_LEGACYUSE_PROXY_BASE_URL}/signup`, {
      method: 'POST',
      body: JSON.stringify(signupData),
    });
    console.log('signup', response);
  };

  // Fetch providers and targets on component mount and reset state
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [providersData, targetsData] = await Promise.all([getProviders(), getTargets()]);

        setProviders(providersData.providers || []);
        setTargets(targetsData || []);

        // Set default provider to first available one
        const availableProvider = providersData.providers?.find(p => p.available);
        if (availableProvider) {
          setSelectedProvider(availableProvider.provider);
        } else if (providersData.providers?.length > 0) {
          setSelectedProvider(providersData.providers[0].provider);
        }
      } catch (err) {
        console.error('Error fetching data:', err);
        setError('Failed to load provider configurations');
      }
    };

    if (open) {
      fetchData();
      // Reset signup state when dialog opens
      setSignupCompleted(false);
      setActivationCode('');
      setError('');
      setResendTimer(0);
    }
  }, [open]);

  const handleNext = () => {
    setActiveStep(prev => prev + 1);
  };

  const handleBack = () => {
    setActiveStep(prev => prev - 1);
  };

  const handleSignupSubmit = async () => {
    if (!signupData.email || !signupData.description) {
      setError('Please fill in all required fields');
      return;
    }

    setLoading(true);
    setError('');

    try {
      // Here you would typically make an API call to your signup endpoint
      // For now, we'll simulate success and move to the next step
      console.log('Signup data:', signupData);

      await signupOrResend();

      // identify the user
      posthog.identify(signupData.email, { email: signupData.email });
      posthog.capture('signup', {
        email: signupData.email,
        description: signupData.description,
        referralCode: signupData.referralCode,
      });

      // Mark signup as completed to show success message
      setSignupCompleted(true);
    } catch (_err) {
      setError('Failed to process signup. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleActivationSubmit = async () => {
    if (!activationCode.trim()) {
      setError('Please enter your activation code');
      return;
    }

    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const isValidUuid = uuidRegex.test(activationCode.trim());
    if (!isValidUuid) {
      setError('Please enter a valid activation code');
      return;
    }

    setLoading(true);
    setError('');

    try {
      // Here you would typically validate the activation code with your API
      console.log('Activation code:', activationCode);

      // Simulate API call delay
      await new Promise(resolve => setTimeout(resolve, 1000));

      // TODO: validate activation code

      // Call backend (server) and setup legacyuse provider with the entered activation code as legacy use cloud api key
      await updateProviderSettings('legacyuse', {
        proxy_api_key: activationCode.trim(),
      });

      // Complete the onboarding
      onComplete();
    } catch (_err) {
      setError('Invalid activation code. Please check your email and try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleProviderSetup = async () => {
    if (!selectedProvider) {
      setError('Please select a provider');
      return;
    }

    setLoading(true);
    setError('');

    try {
      let credentials = {};

      if (selectedProvider === 'anthropic') {
        if (!apiKeyInput.trim()) {
          setError('Please enter your Anthropic API key');
          return;
        }
        credentials.api_key = apiKeyInput;
      } else if (selectedProvider === 'bedrock') {
        if (!awsCredentials.accessKeyId || !awsCredentials.secretAccessKey) {
          setError('Please enter your AWS credentials');
          return;
        }
        credentials = {
          access_key_id: awsCredentials.accessKeyId,
          secret_access_key: awsCredentials.secretAccessKey,
          region: awsCredentials.region,
        };
      } else if (selectedProvider === 'vertex') {
        if (!vertexCredentials.projectId) {
          setError('Please enter your Google Cloud Project ID');
          return;
        }
        credentials = {
          project_id: vertexCredentials.projectId,
          region: vertexCredentials.region,
        };
      } else if (selectedProvider === 'legacyuse') {
        if (!apiKeyInput.trim()) {
          setError('Please enter your legacy-use API key');
          return;
        }
        credentials.proxy_api_key = apiKeyInput;
      }

      // Use the new backend logic to configure the provider
      await updateProviderSettings(selectedProvider, credentials);

      // Move to next step instead of completing onboarding
      handleNext();
    } catch (_err) {
      setError('Failed to configure provider. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleRunFirstJob = () => {
    // Navigate to API page with first target selected
    if (targets.length > 0) {
      const firstTarget = targets[0];
      navigate(`/apis?target=${firstTarget.id}`);
    } else {
      navigate('/apis');
    }

    // Complete the onboarding
    onComplete();
  };

  const renderWelcomeStep = () => (
    <Box sx={{ textAlign: 'center', py: 4 }}>
      <img src="/logo-white-logotop.svg" alt="legacy-use" style={{ height: '100px' }} />
      <Typography variant="h5" color="text.secondary" sx={{ mt: 3, mb: 2 }}>
        Automate any legacy application with AI
      </Typography>
      <Typography variant="body1" color="text.secondary">
        legacy-use allows to expose legacy applications with REST-APIs, enabling you to build
        reliable solutions and automate workflows where it was not possible before.
      </Typography>
      <Box sx={{ mt: 4 }}>
        <Button variant="contained" size="large" onClick={handleNext} sx={{ mr: 2 }}>
          Get Started
        </Button>
      </Box>
    </Box>
  );

  const renderSignupSuccessMessage = () => (
    <Box sx={{ py: 4, textAlign: 'center' }}>
      <CheckCircleIcon sx={{ fontSize: 80, color: 'success.main', mb: 2 }} />
      <Typography variant="h4" component="h2" gutterBottom>
        Welcome to legacy-use!
      </Typography>
      <Typography variant="h6" color="text.secondary" paragraph>
        Your signup was successful
      </Typography>

      <Paper elevation={2} sx={{ p: 3, mb: 3, bgcolor: 'success.50' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', mb: 2 }}>
          <EmailIcon sx={{ mr: 1, color: 'success.main' }} />
          <Typography variant="h6" color="success.main">
            Check Your Email
          </Typography>
        </Box>

        <Typography variant="body1" paragraph>
          We've sent an email to <strong>{signupData.email}</strong> with your $5 credit activation
          code and instructions on how to get started.
        </Typography>

        <Typography variant="body2" color="text.secondary">
          Don't see the email? Check your spam folder or{' '}
          <Button
            variant="text"
            size="small"
            onClick={signupOrResend}
            disabled={loading || resendTimer > 0}
          >
            {resendTimer > 0 ? `resend in ${resendTimer}s` : 'resend the email'}
          </Button>
          .
        </Typography>
      </Paper>

      <Paper elevation={1} sx={{ p: 3, mb: 2 }}>
        <Typography variant="h6" gutterBottom>
          Enter Activation Code
        </Typography>
        <Typography variant="body2" color="text.secondary" paragraph>
          Enter the activation code from your email to claim your $5 credits and continue.
        </Typography>

        <TextField
          fullWidth
          label="Activation Code"
          value={activationCode}
          onChange={e => setActivationCode(e.target.value)}
          variant="outlined"
          placeholder="Enter your activation code"
          sx={{ mb: 2 }}
          onKeyPress={e => {
            if (e.key === 'Enter' && !loading && activationCode.trim()) {
              handleActivationSubmit();
            }
          }}
        />

        <Button
          fullWidth
          variant="contained"
          size="large"
          onClick={handleActivationSubmit}
          disabled={loading || !activationCode.trim()}
        >
          {loading ? 'Verifying...' : 'Activate Credits & Continue'}
        </Button>
      </Paper>
    </Box>
  );

  const renderSignupStep = () => {
    // Show success message if signup is completed
    if (signupCompleted) {
      return renderSignupSuccessMessage();
    }

    return (
      <Box sx={{ py: 2 }}>
        <Typography variant="h4" component="h2" gutterBottom align="center">
          Get Started with $5 Credits for free
        </Typography>
        <Typography variant="body1" color="text.secondary" paragraph align="center" sx={{ mb: 4 }}>
          Sign up with your email to receive $5 in credits for free to explore legacy-use's
          automation capabilities.
        </Typography>

        {/* Main signup section */}
        <Paper elevation={2} sx={{ p: 3, mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
            <RocketIcon sx={{ mr: 1, color: 'primary.main' }} />
            <Typography variant="h6">Signup for free</Typography>
          </Box>

          <Grid container spacing={2}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Email Address"
                type="email"
                required
                value={signupData.email}
                onChange={e => setSignupData(prev => ({ ...prev, email: e.target.value }))}
                variant="outlined"
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="What software do you want to automate?"
                multiline
                rows={3}
                required
                value={signupData.description}
                onChange={e => setSignupData(prev => ({ ...prev, description: e.target.value }))}
                variant="outlined"
                placeholder="e.g., DATEV, SAP, Lexware, Navision, ..."
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Referral Code (Optional)"
                value={signupData.referralCode}
                onChange={e => setSignupData(prev => ({ ...prev, referralCode: e.target.value }))}
                variant="outlined"
                placeholder="Enter referral code if you have one"
              />
            </Grid>
          </Grid>

          <Button
            fullWidth
            variant="contained"
            size="large"
            onClick={handleSignupSubmit}
            disabled={loading}
            sx={{ mt: 3 }}
          >
            {loading ? 'Processing...' : 'Get $5 Credits for free'}
          </Button>
        </Paper>

        {/* Divider */}
        <Divider sx={{ my: 3 }}>
          <Typography variant="body2" color="text.secondary">
            OR
          </Typography>
        </Divider>

        {/* Secondary option */}
        <Typography variant="body2" color="text.secondary" paragraph align="center">
          Already have API keys? Skip the credits and configure your own provider credentials.
        </Typography>
        <Button variant="outlined" onClick={handleNext} startIcon={<KeyIcon />} fullWidth>
          Configure Custom Provider
        </Button>
      </Box>
    );
  };

  const renderProviderStep = () => (
    <Box sx={{ py: 2 }}>
      <Typography variant="h4" component="h2" gutterBottom align="center">
        Configure AI Provider
      </Typography>
      <Typography variant="body1" color="text.secondary" paragraph align="center" sx={{ mb: 4 }}>
        Select and configure your preferred AI provider to power legacy-use
      </Typography>

      <FormControl fullWidth sx={{ mb: 3 }}>
        <InputLabel>AI Provider</InputLabel>
        <Select
          value={selectedProvider}
          onChange={e => setSelectedProvider(e.target.value)}
          label="AI Provider"
        >
          {providers
            .filter(provider => provider.provider !== 'legacyuse')
            .map(provider => (
              <MenuItem key={provider.provider} value={provider.provider}>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    width: '100%',
                  }}
                >
                  <Box>
                    <Typography variant="body1">{provider.name}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {provider.description}
                    </Typography>
                  </Box>
                  {provider.available && <Chip label="Configured" color="success" size="small" />}
                </Box>
              </MenuItem>
            ))}
        </Select>
      </FormControl>

      {/* Provider-specific configuration */}
      {selectedProvider === 'anthropic' && (
        <Paper elevation={1} sx={{ p: 3, mb: 2 }}>
          <Typography variant="h6" gutterBottom>
            Anthropic Configuration
          </Typography>
          <TextField
            fullWidth
            label="API Key"
            type="password"
            value={apiKeyInput}
            onChange={e => setApiKeyInput(e.target.value)}
            variant="outlined"
            placeholder="Enter your Anthropic API key"
            helperText="You can get your API key from the Anthropic Console"
          />
        </Paper>
      )}

      {selectedProvider === 'bedrock' && (
        <Paper elevation={1} sx={{ p: 3, mb: 2 }}>
          <Typography variant="h6" gutterBottom>
            AWS Bedrock Configuration
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Access Key ID"
                value={awsCredentials.accessKeyId}
                onChange={e =>
                  setAwsCredentials(prev => ({ ...prev, accessKeyId: e.target.value }))
                }
                variant="outlined"
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Secret Access Key"
                type="password"
                value={awsCredentials.secretAccessKey}
                onChange={e =>
                  setAwsCredentials(prev => ({ ...prev, secretAccessKey: e.target.value }))
                }
                variant="outlined"
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Region"
                value={awsCredentials.region}
                onChange={e => setAwsCredentials(prev => ({ ...prev, region: e.target.value }))}
                variant="outlined"
              />
            </Grid>
          </Grid>
        </Paper>
      )}

      {selectedProvider === 'vertex' && (
        <Paper elevation={1} sx={{ p: 3, mb: 2 }}>
          <Typography variant="h6" gutterBottom>
            Google Vertex AI Configuration
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Project ID"
                value={vertexCredentials.projectId}
                onChange={e =>
                  setVertexCredentials(prev => ({ ...prev, projectId: e.target.value }))
                }
                variant="outlined"
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Region"
                value={vertexCredentials.region}
                onChange={e => setVertexCredentials(prev => ({ ...prev, region: e.target.value }))}
                variant="outlined"
              />
            </Grid>
          </Grid>
        </Paper>
      )}

      <Button
        fullWidth
        variant="contained"
        size="large"
        onClick={handleProviderSetup}
        disabled={loading}
        sx={{ mt: 2 }}
      >
        {loading ? 'Configuring...' : 'Continue to Next Step'}
      </Button>
    </Box>
  );

  const renderRunFirstJobStep = () => (
    <Box sx={{ py: 2 }}>
      <Typography variant="h4" component="h2" gutterBottom align="center">
        Run Your First Job
      </Typography>
      <Typography variant="body1" color="text.secondary" paragraph align="center" sx={{ mb: 4 }}>
        You're all set! Now let's run your first automation job.
      </Typography>

      {/* Legacy App Screenshot - Placeholder for now */}
      <Paper elevation={2} sx={{ p: 3, mb: 3, textAlign: 'center' }}>
        <Box
          sx={{
            width: '100%',
            height: 300,
            backgroundColor: 'grey.100',
            borderRadius: 2,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            mb: 2,
          }}
        >
          <Typography variant="h6" color="text.secondary">
            Legacy App Screenshot
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            (Image will be provided)
          </Typography>
        </Box>
        <Typography variant="body1" paragraph>
          This is what your legacy application will look like when automated with legacy-use.
        </Typography>
      </Paper>

      <Paper elevation={1} sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <PlayArrowIcon sx={{ mr: 1, color: 'primary.main' }} />
          <Typography variant="h6">Ready to Start</Typography>
        </Box>

        {targets.length > 0 ? (
          <Typography variant="body1" paragraph>
            We found <strong>{targets.length}</strong> target{targets.length > 1 ? 's' : ''}{' '}
            available. Click the button below to go to the API page and execute your first
            automation job.
          </Typography>
        ) : (
          <Typography variant="body1" paragraph>
            You'll need to create a target first, then you can start running automation jobs. Click
            the button below to go to the API page.
          </Typography>
        )}

        <Button
          fullWidth
          variant="contained"
          size="large"
          onClick={handleRunFirstJob}
          startIcon={<PlayArrowIcon />}
          sx={{ mt: 2 }}
        >
          {targets.length > 0 ? 'Go to APIs & Run First Job' : 'Go to APIs'}
        </Button>
      </Paper>

      <Typography variant="body2" color="text.secondary" align="center">
        You can always access the API page from the navigation menu to run more jobs.
      </Typography>
    </Box>
  );

  const renderStepContent = step => {
    switch (step) {
      case 0:
        return renderWelcomeStep();
      case 1:
        return renderSignupStep();
      case 2:
        return renderProviderStep();
      case 3:
        return renderRunFirstJobStep();
      default:
        return null;
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: { minHeight: '80vh' },
      }}
    >
      <DialogContent sx={{ p: 0 }}>
        <Box sx={{ position: 'relative' }}>
          <IconButton
            onClick={onClose}
            sx={{
              position: 'absolute',
              right: 8,
              top: 8,
              zIndex: 1,
            }}
          >
            <CloseIcon />
          </IconButton>

          <Container maxWidth="sm" sx={{ py: 4 }}>
            {/* Stepper */}
            <Stepper activeStep={activeStep} alternativeLabel sx={{ mb: 4 }}>
              {steps.map(label => (
                <Step key={label}>
                  <StepLabel>{label}</StepLabel>
                </Step>
              ))}
            </Stepper>

            {/* Error Alert */}
            {error && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {error}
              </Alert>
            )}

            {/* Step Content */}
            {renderStepContent(activeStep)}

            {/* Navigation */}
            {activeStep > 0 && activeStep < steps.length - 1 && (
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 4 }}>
                <Button onClick={handleBack} disabled={loading}>
                  Back
                </Button>
                <Box /> {/* Spacer */}
              </Box>
            )}
            {activeStep === steps.length - 1 && (
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 4 }}>
                <Button onClick={handleBack} disabled={loading}>
                  Back
                </Button>
                <Box /> {/* Spacer */}
              </Box>
            )}
          </Container>
        </Box>
      </DialogContent>
    </Dialog>
  );
};

export default OnboardingWizard;
