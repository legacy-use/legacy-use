import {
  CheckCircle as CheckCircleIcon,
  Close as CloseIcon,
  Email as EmailIcon,
  Key as KeyIcon,
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
  Link,
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
import type { ProviderConfiguration } from '@/gen/endpoints';
import { useAiProvider } from '../contexts/AiProviderContext';
import { getProviders, getTargets, updateProviderSettings } from '../services/apiService';
import { API_BASE_URL } from '../utils/apiConstants';

const OnboardingWizard = ({ open, onClose, onComplete }) => {
  const navigate = useNavigate();
  const [activeStep, setActiveStep] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [providers, setProviders] = useState<ProviderConfiguration[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>('');
  const [signupCompleted, setSignupCompleted] = useState<boolean>(false);
  const [activationCode, setActivationCode] = useState<string>('');
  const [resendTimer, setResendTimer] = useState<number>(0);
  const { refreshProviders } = useAiProvider();

  // Signup form state
  const [signupData, setSignupData] = useState<{
    email: string;
    description: string;
    referralCode: string;
  }>({
    email: '',
    description: '',
    referralCode: '',
  });

  // Provider configuration state
  const [apiKeyInput, setApiKeyInput] = useState<string>('');
  const [awsCredentials, setAwsCredentials] = useState({
    accessKeyId: '',
    secretAccessKey: '',
    region: 'us-east-1',
  });
  const [vertexCredentials, setVertexCredentials] = useState({
    projectId: '',
    region: 'us-central1',
  });
  const [openaiCredentials, setOpenaiCredentials] = useState({
    apiKey: '',
  });

  const steps = ['Welcome', 'Get Started', 'Configure Provider'];

  // Timer effect for resend countdown
  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
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

    const response = await fetch(
      `${import.meta.env.VITE_LEGACYUSE_PROXY_BASE_URL}${API_BASE_URL}/signup`,
      {
        method: 'POST',
        body: JSON.stringify(signupData),
      },
    );
    console.log('signup', response);
  };

  // Fetch providers on component mount and reset state
  useEffect(() => {
    const fetchProviders = async () => {
      try {
        const providersData = await getProviders();
        setProviders(providersData.providers || []);

        // Set default provider to first available one
        const availableProvider = providersData.providers?.find(p => p.available);
        if (availableProvider) {
          setSelectedProvider(availableProvider.provider);
        } else if (providersData.providers?.length > 0) {
          setSelectedProvider(providersData.providers[0].provider);
        }
      } catch (err) {
        console.error('Error fetching providers:', err);
        setError('Failed to load provider configurations');
      }
    };

    if (open) {
      fetchProviders();
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

      // TODO: validate activation code

      // Call backend (server) and setup legacyuse provider with the entered activation code as legacy use cloud api key
      await updateProviderSettings('legacyuse', {
        proxy_api_key: activationCode.trim(),
      });

      // Load targets and redirect to first one
      try {
        const targets = await getTargets();
        if (targets.length > 0) {
          const firstTarget = targets[0];
          navigate(`/apis?target=${firstTarget.id}`);
        }
      } catch (err) {
        console.error('Error loading targets:', err);
      }

      // refresh providers
      await refreshProviders();

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
      let credentials: any = {};

      if (selectedProvider === 'anthropic') {
        if (!apiKeyInput.trim()) {
          setError('Please enter your Anthropic API key');
          return;
        }
        credentials.api_key = apiKeyInput;
      } else if (selectedProvider === 'bedrock') {
        if (
          !awsCredentials.accessKeyId ||
          !awsCredentials.secretAccessKey ||
          !awsCredentials.region
        ) {
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
      } else if (selectedProvider === 'openai') {
        if (!openaiCredentials.apiKey.trim()) {
          setLoading(false);
          setError('Please enter your OpenAI API key');
          return;
        }
        credentials.api_key = openaiCredentials.apiKey.trim();
      } else if (selectedProvider === 'opencua') {
        if (
          !awsCredentials.accessKeyId ||
          !awsCredentials.secretAccessKey ||
          !awsCredentials.region
        ) {
          setError('Please enter your AWS credentials to use opencua');
          return;
        }
        credentials = {
          access_key_id: awsCredentials.accessKeyId,
          secret_access_key: awsCredentials.secretAccessKey,
          region: awsCredentials.region,
        };
      }

      // Use the new backend logic to configure the provider
      await updateProviderSettings(selectedProvider, credentials);

      // Load targets and redirect to first one
      try {
        const targets = await getTargets();
        if (targets.length > 0) {
          const firstTarget = targets[0];
          navigate(`/apis?target=${firstTarget.id}`);
        }
      } catch (err) {
        console.error('Error loading targets:', err);
      }

      await refreshProviders();

      // Complete the onboarding
      onComplete();
    } catch (_err) {
      setError('Failed to configure provider. Please check your credentials.');
    } finally {
      setLoading(false);
    }
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
            <Grid size={12}>
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
            <Grid size={12}>
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
            <Grid size={12}>
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
        {/* Activation key option */}
        <Typography
          variant="caption"
          color="text.secondary"
          align="center"
          sx={{ mt: 1, display: 'block', mb: 1 }}
        >
          Already have an activation key?{' '}
          <Link
            href="#"
            onClick={e => {
              e.preventDefault();
              setSignupCompleted(true);
            }}
          >
            Enter it here
          </Link>
        </Typography>
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
            <Grid size={12}>
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
            <Grid size={12}>
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
            <Grid size={12}>
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
            <Grid size={12}>
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
            <Grid size={12}>
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

      {selectedProvider === 'openai' && (
        <Paper elevation={1} sx={{ p: 3, mb: 2 }}>
          <Typography variant="h6" gutterBottom>
            OpenAI Configuration
          </Typography>
          <TextField
            fullWidth
            label="API Key"
            type="password"
            value={openaiCredentials.apiKey}
            onChange={e => setOpenaiCredentials(prev => ({ ...prev, apiKey: e.target.value }))}
            variant="outlined"
            placeholder="Enter your OpenAI API key"
            helperText="You can get your API key from the OpenAI Console"
          />
        </Paper>
      )}

      {selectedProvider === 'opencua' && (
        <Paper elevation={1} sx={{ p: 3, mb: 2 }}>
          <Typography variant="h6" gutterBottom>
            OpenCua Configuration
          </Typography>
          <Grid container spacing={2}>
            <Grid size={12}>
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
            <Grid size={12}>
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
            <Grid size={12}>
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

      <Button
        fullWidth
        variant="contained"
        size="large"
        onClick={handleProviderSetup}
        disabled={loading}
        sx={{ mt: 2 }}
      >
        {loading ? 'Configuring...' : 'Complete Setup'}
      </Button>
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
            {activeStep > 0 && activeStep < steps.length && (
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
