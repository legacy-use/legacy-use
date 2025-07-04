import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Collapse,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormHelperText,
  Grid,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  TextField,
  Typography,
} from '@mui/material';
import {
  Cloud as CloudIcon,
  ExpandLess,
  ExpandMore,
  Key as KeyIcon,
  Rocket as RocketIcon,
  Security as SecurityIcon,
} from '@mui/icons-material';
import { useState } from 'react';
import { AIProviderType, useAIProvider } from '../contexts/AIProviderContext';
import { signupForCredits, validateAIProvider } from '../services/apiService';

const AIProviderSetup = ({ open, onClose }) => {
  const { setProvider, setProviderConfig, setHasSignedUp } = useAIProvider();
  
  // State for signup form
  const [signupForm, setSignupForm] = useState({
    email: '',
    description: '',
  });
  const [signupLoading, setSignupLoading] = useState(false);
  const [signupError, setSignupError] = useState('');

  // State for BYOK form
  const [byokProvider, setByokProvider] = useState(AIProviderType.ANTHROPIC);
  const [byokForm, setByokForm] = useState({
    anthropic: {
      apiKey: '',
    },
    bedrock: {
      awsAccessKey: '',
      awsSecretKey: '',
      awsRegion: 'us-east-1',
      awsSessionToken: '',
    },
    vertex: {
      projectId: '',
      region: 'us-central1',
    },
  });
  const [byokLoading, setByokLoading] = useState(false);
  const [byokError, setByokError] = useState('');

  // State for UI control
  const [showByok, setShowByok] = useState(false);

  // Handle signup form changes
  const handleSignupChange = (field, value) => {
    setSignupForm(prev => ({ ...prev, [field]: value }));
    setSignupError('');
  };

  // Handle BYOK form changes
  const handleByokChange = (field, value) => {
    setByokForm(prev => ({
      ...prev,
      [byokProvider]: {
        ...prev[byokProvider],
        [field]: value,
      },
    }));
    setByokError('');
  };

  // Handle provider selection
  const handleProviderChange = (event) => {
    setByokProvider(event.target.value);
    setByokError('');
  };

  // Handle signup submission
  const handleSignupSubmit = async () => {
    if (!signupForm.email || !signupForm.description) {
      setSignupError('Please fill in all fields');
      return;
    }

    setSignupLoading(true);
    setSignupError('');

    try {
      await signupForCredits(signupForm.email, signupForm.description);
      
      // Mark as signed up
      setHasSignedUp(true);
      onClose();
    } catch (error) {
      setSignupError(error.response?.data?.message || 'Failed to sign up. Please try again.');
    } finally {
      setSignupLoading(false);
    }
  };

  // Handle BYOK submission
  const handleByokSubmit = async () => {
    const config = byokForm[byokProvider];
    
    // Validate required fields
    if (byokProvider === AIProviderType.ANTHROPIC && !config.apiKey) {
      setByokError('Please enter your Anthropic API key');
      return;
    }
    
    if (byokProvider === AIProviderType.BEDROCK && (!config.awsAccessKey || !config.awsSecretKey || !config.awsRegion)) {
      setByokError('Please enter your AWS credentials');
      return;
    }
    
    if (byokProvider === AIProviderType.VERTEX && (!config.projectId || !config.region)) {
      setByokError('Please enter your Google Cloud project details');
      return;
    }

    setByokLoading(true);
    setByokError('');

    try {
      await validateAIProvider(byokProvider, config);
      
      // Save provider configuration
      setProvider(byokProvider);
      setProviderConfig(config);
      onClose();
    } catch (error) {
      setByokError(error.response?.data?.message || 'Failed to validate provider configuration. Please check your credentials.');
    } finally {
      setByokLoading(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: {
          minHeight: '80vh',
          maxHeight: '90vh',
        },
      }}
    >
      <DialogTitle sx={{ textAlign: 'center', pb: 1 }}>
        <RocketIcon sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
        <Typography variant="h4" component="h1" gutterBottom>
          Welcome to AI Automation
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Configure your AI provider to start automating your legacy software
        </Typography>
      </DialogTitle>
      
      <DialogContent sx={{ pt: 2 }}>
        {/* Signup Section */}
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <RocketIcon sx={{ mr: 1, color: 'primary.main' }} />
              <Typography variant="h6">
                Get Started with Free Credits
              </Typography>
            </Box>
            
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Sign up for free credits to try our AI automation platform. Perfect for getting started quickly.
            </Typography>

            {signupError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {signupError}
              </Alert>
            )}

            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Email Address"
                  type="email"
                  value={signupForm.email}
                  onChange={(e) => handleSignupChange('email', e.target.value)}
                  disabled={signupLoading}
                  required
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Legacy Software Description"
                  multiline
                  rows={1}
                  value={signupForm.description}
                  onChange={(e) => handleSignupChange('description', e.target.value)}
                  disabled={signupLoading}
                  placeholder="e.g., Old CRM system, mainframe application..."
                  required
                />
              </Grid>
            </Grid>

            <Button
              fullWidth
              variant="contained"
              size="large"
              onClick={handleSignupSubmit}
              disabled={signupLoading}
              sx={{ mt: 2 }}
            >
              {signupLoading ? 'Signing up...' : 'Sign Up for Free Credits'}
            </Button>
          </CardContent>
        </Card>

        {/* Divider */}
        <Box sx={{ display: 'flex', alignItems: 'center', my: 3 }}>
          <Divider sx={{ flexGrow: 1 }} />
          <Typography variant="body2" color="text.secondary" sx={{ mx: 2 }}>
            OR
          </Typography>
          <Divider sx={{ flexGrow: 1 }} />
        </Box>

        {/* BYOK Section */}
        <Card>
          <CardContent>
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                cursor: 'pointer',
              }}
              onClick={() => setShowByok(!showByok)}
            >
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <KeyIcon sx={{ mr: 1, color: 'secondary.main' }} />
                <Typography variant="h6">
                  Bring Your Own API Keys
                </Typography>
              </Box>
              <IconButton>
                {showByok ? <ExpandLess /> : <ExpandMore />}
              </IconButton>
            </Box>

            <Collapse in={showByok}>
              <Box sx={{ mt: 2 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                  Use your own API keys from supported providers for maximum control and usage flexibility.
                </Typography>

                {byokError && (
                  <Alert severity="error" sx={{ mb: 2 }}>
                    {byokError}
                  </Alert>
                )}

                {/* Provider Selection */}
                <FormControl fullWidth sx={{ mb: 3 }}>
                  <InputLabel>AI Provider</InputLabel>
                  <Select
                    value={byokProvider}
                    onChange={handleProviderChange}
                    label="AI Provider"
                    disabled={byokLoading}
                  >
                    <MenuItem value={AIProviderType.ANTHROPIC}>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <CloudIcon sx={{ mr: 1 }} />
                        Anthropic (Direct API)
                      </Box>
                    </MenuItem>
                    <MenuItem value={AIProviderType.BEDROCK}>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <SecurityIcon sx={{ mr: 1 }} />
                        Anthropic via AWS Bedrock
                      </Box>
                    </MenuItem>
                    <MenuItem value={AIProviderType.VERTEX}>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <CloudIcon sx={{ mr: 1 }} />
                        Google Vertex AI
                      </Box>
                    </MenuItem>
                  </Select>
                </FormControl>

                {/* Provider-specific configuration */}
                {byokProvider === AIProviderType.ANTHROPIC && (
                  <Box>
                    <TextField
                      fullWidth
                      label="Anthropic API Key"
                      type="password"
                      value={byokForm.anthropic.apiKey}
                      onChange={(e) => handleByokChange('apiKey', e.target.value)}
                      disabled={byokLoading}
                      placeholder="sk-ant-..."
                      required
                    />
                    <FormHelperText>
                      Get your API key from the Anthropic Console
                    </FormHelperText>
                  </Box>
                )}

                {byokProvider === AIProviderType.BEDROCK && (
                  <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="AWS Access Key ID"
                        type="password"
                        value={byokForm.bedrock.awsAccessKey}
                        onChange={(e) => handleByokChange('awsAccessKey', e.target.value)}
                        disabled={byokLoading}
                        required
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="AWS Secret Access Key"
                        type="password"
                        value={byokForm.bedrock.awsSecretKey}
                        onChange={(e) => handleByokChange('awsSecretKey', e.target.value)}
                        disabled={byokLoading}
                        required
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="AWS Region"
                        value={byokForm.bedrock.awsRegion}
                        onChange={(e) => handleByokChange('awsRegion', e.target.value)}
                        disabled={byokLoading}
                        required
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="AWS Session Token (Optional)"
                        type="password"
                        value={byokForm.bedrock.awsSessionToken}
                        onChange={(e) => handleByokChange('awsSessionToken', e.target.value)}
                        disabled={byokLoading}
                      />
                    </Grid>
                    <Grid item xs={12}>
                      <FormHelperText>
                        Ensure your AWS account has access to Anthropic Claude models in Bedrock
                      </FormHelperText>
                    </Grid>
                  </Grid>
                )}

                {byokProvider === AIProviderType.VERTEX && (
                  <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Google Cloud Project ID"
                        value={byokForm.vertex.projectId}
                        onChange={(e) => handleByokChange('projectId', e.target.value)}
                        disabled={byokLoading}
                        required
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Region"
                        value={byokForm.vertex.region}
                        onChange={(e) => handleByokChange('region', e.target.value)}
                        disabled={byokLoading}
                        required
                      />
                    </Grid>
                    <Grid item xs={12}>
                      <FormHelperText>
                        Ensure your Google Cloud project has Vertex AI API enabled and proper authentication configured
                      </FormHelperText>
                    </Grid>
                  </Grid>
                )}

                <Button
                  fullWidth
                  variant="outlined"
                  size="large"
                  onClick={handleByokSubmit}
                  disabled={byokLoading}
                  sx={{ mt: 3 }}
                >
                  {byokLoading ? 'Validating...' : 'Configure Provider'}
                </Button>
              </Box>
            </Collapse>
          </CardContent>
        </Card>
      </DialogContent>
    </Dialog>
  );
};

export default AIProviderSetup;