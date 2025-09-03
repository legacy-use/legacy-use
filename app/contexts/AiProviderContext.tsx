import { createContext, useContext, useEffect, useState } from 'react';
import type { ProviderConfiguration } from '@/gen/endpoints';
import { getProviders } from '../services/apiService';

// Create the context
export const AiProviderContext = createContext({
  providers: [] as ProviderConfiguration[],
  currentProvider: null as string | null,
  hasConfiguredProvider: false,
  isProviderValid: false,
  loading: false,
  refreshProviders: async () => {},
});

// Create a provider component
export const AiProvider = ({ children }) => {
  const [providers, setProviders] = useState<ProviderConfiguration[]>([]);
  const [currentProvider, setCurrentProvider] = useState<string | null>(null);
  const [hasConfiguredProvider, setHasConfiguredProvider] = useState<boolean>(false);
  const [isProviderValid, setIsProviderValid] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);

  // Function to refresh provider data
  const refreshProviders = async () => {
    setLoading(true);
    try {
      const providersData = await getProviders();
      setProviders(providersData.providers || []);
      setCurrentProvider(providersData.current_provider || null);

      // Check if any provider is configured
      const configuredProviders = providersData.providers.filter(provider => provider.available);
      const hasConfigured = configuredProviders.length > 0;
      setHasConfiguredProvider(hasConfigured);
      // Make sure the active provider is configured
      const activeProviderConfigured = configuredProviders.find(
        provider => provider.provider === providersData.current_provider,
      );
      setIsProviderValid(hasConfigured && !!activeProviderConfigured);
    } catch (error) {
      console.error('Error refreshing providers:', error);
      setProviders([]);
      setCurrentProvider(null);
      setHasConfiguredProvider(false);
      setIsProviderValid(false);
    } finally {
      setLoading(false);
    }
  };

  // Initial load of providers
  useEffect(() => {
    refreshProviders();
  }, []);

  // Context value
  const value = {
    providers,
    currentProvider,
    hasConfiguredProvider,
    isProviderValid,
    loading,
    refreshProviders,
  };

  return <AiProviderContext.Provider value={value}>{children}</AiProviderContext.Provider>;
};

// Custom hook for using the provider context
export const useAiProvider = () => {
  const context = useContext(AiProviderContext);
  if (context === undefined) {
    throw new Error('useAiProvider must be used within an AiProvider');
  }
  return context;
};
