import { createContext, useContext, useEffect, useState } from 'react';

// Add browser globals for linter
const { localStorage } = globalThis;

// AI Provider types
export const AIProviderType = {
  ANTHROPIC: 'anthropic',
  BEDROCK: 'bedrock',
  VERTEX: 'vertex',
};

// Create the context
export const AIProviderContext = createContext({
  provider: null,
  setProvider: () => {},
  providerConfig: null,
  setProviderConfig: () => {},
  isConfigured: false,
  clearProviderConfig: () => {},
  hasSignedUp: false,
  setHasSignedUp: () => {},
});

// Create a provider component
export const AIProviderProvider = ({ children }) => {
  // Get provider configuration from localStorage
  const [provider, setProviderState] = useState(() => {
    const savedProvider = localStorage.getItem('aiProvider');
    return savedProvider || null;
  });

  const [providerConfig, setProviderConfigState] = useState(() => {
    const savedConfig = localStorage.getItem('aiProviderConfig');
    return savedConfig ? JSON.parse(savedConfig) : null;
  });

  const [hasSignedUp, setHasSignedUpState] = useState(() => {
    const savedSignup = localStorage.getItem('hasSignedUp');
    return savedSignup === 'true';
  });

  // Update localStorage when provider changes
  useEffect(() => {
    if (provider) {
      localStorage.setItem('aiProvider', provider);
    } else {
      localStorage.removeItem('aiProvider');
    }
  }, [provider]);

  // Update localStorage when provider config changes
  useEffect(() => {
    if (providerConfig) {
      localStorage.setItem('aiProviderConfig', JSON.stringify(providerConfig));
    } else {
      localStorage.removeItem('aiProviderConfig');
    }
  }, [providerConfig]);

  // Update localStorage when signup status changes
  useEffect(() => {
    localStorage.setItem('hasSignedUp', hasSignedUp.toString());
  }, [hasSignedUp]);

  // Function to set the provider
  const setProvider = providerType => {
    setProviderState(providerType);
  };

  // Function to set the provider config
  const setProviderConfig = config => {
    setProviderConfigState(config);
  };

  // Function to set signup status
  const setHasSignedUp = status => {
    setHasSignedUpState(status);
  };

  // Function to clear provider configuration
  const clearProviderConfig = () => {
    localStorage.removeItem('aiProvider');
    localStorage.removeItem('aiProviderConfig');
    localStorage.removeItem('hasSignedUp');
    setProviderState(null);
    setProviderConfigState(null);
    setHasSignedUpState(false);
  };

  // Check if provider is configured
  const isConfigured = Boolean(
    hasSignedUp || 
    (provider && providerConfig && (
      (provider === AIProviderType.ANTHROPIC && providerConfig.apiKey) ||
      (provider === AIProviderType.BEDROCK && providerConfig.awsAccessKey && providerConfig.awsSecretKey && providerConfig.awsRegion) ||
      (provider === AIProviderType.VERTEX && providerConfig.projectId && providerConfig.region)
    ))
  );

  // Context value
  const value = {
    provider,
    setProvider,
    providerConfig,
    setProviderConfig,
    isConfigured,
    clearProviderConfig,
    hasSignedUp,
    setHasSignedUp,
  };

  return <AIProviderContext.Provider value={value}>{children}</AIProviderContext.Provider>;
};

// Custom hook for using the AI provider context
export const useAIProvider = () => {
  const context = useContext(AIProviderContext);
  if (context === undefined) {
    throw new Error('useAIProvider must be used within an AIProviderProvider');
  }
  return context;
};