# Multi-Provider Handler System

This directory contains the handler system for supporting multiple LLM providers in the sampling loop while maintaining a consistent database schema tied to Anthropic's message format.

## Architecture Overview

The handler system follows a protocol-based design pattern where each provider implements a common interface (`ProviderHandler`) that handles provider-specific logic while the main sampling loop remains generic.

### Key Components

1. **Base Protocol (`base.py`)**: Defines the `ProviderHandler` protocol that all handlers must implement
2. **Handler Registry (`registry.py`)**: Manages handler registration and instantiation
3. **Provider Handlers**: Provider-specific implementations (e.g., `anthropic.py`, `openai.py`)
4. **Sampling Loop**: Generic loop that delegates to handlers for provider-specific operations

## Handler Protocol Methods

Each handler must implement the following methods:

- `initialize_client(api_key, **kwargs)`: Initialize the provider's client
- `prepare_system(system_prompt)`: Format system prompt for the provider
- `convert_to_provider_messages(messages)`: Convert Anthropic format to provider format
- `prepare_tools(tool_collection)`: Format tools for the provider's API
- `call_api(...)`: Make the API call to the provider
- `convert_from_provider_response(response)`: Convert provider response to Anthropic format
- `parse_tool_use(content_block)`: Parse tool use from content blocks
- `make_tool_result(result, tool_use_id)`: Create tool result in Anthropic format

## Adding a New Provider

To add support for a new LLM provider:

### 1. Add Provider to Config

Update `server/computer_use/config.py`:

```python
class APIProvider(StrEnum):
    # ... existing providers ...
    YOUR_PROVIDER = 'your_provider'

PROVIDER_TO_DEFAULT_MODEL_NAME[APIProvider.YOUR_PROVIDER] = 'your-default-model'
```

### 2. Create Handler Implementation

Create `server/computer_use/handlers/your_provider.py`:

```python
from server.computer_use.handlers.base import BaseProviderHandler

class YourProviderHandler(BaseProviderHandler):
    async def initialize_client(self, api_key: str, **kwargs):
        # Initialize your provider's client
        pass
    
    def convert_to_provider_messages(self, messages):
        # Convert Anthropic format to your provider's format
        pass
    
    # ... implement other required methods ...
```

### 3. Register Handler

Update `server/computer_use/handlers/registry.py`:

```python
from server.computer_use.handlers.your_provider import YourProviderHandler

# In get_handler() function:
register_handler(APIProvider.YOUR_PROVIDER, YourProviderHandler)
```

## Message Format Mapping

All messages are stored in the database using Anthropic's `BetaMessageParam` format. Handlers are responsible for:

1. **Input**: Converting from Anthropic format to provider-specific format before API calls
2. **Output**: Converting from provider-specific format back to Anthropic format after API calls

This ensures database consistency while allowing flexibility in provider implementations.

## Example: OpenAI Handler

The `openai.py` file provides a complete example of how to implement a handler for a non-Anthropic provider:

- Maps Anthropic's message structure to OpenAI's chat format
- Converts tool definitions between formats
- Handles response mapping including tool calls
- Maintains compatibility with the database schema

## Current Supported Providers

- **Anthropic** (Direct API)
- **AWS Bedrock** (Anthropic models)
- **Google Vertex AI** (Anthropic models)
- **Legacy Use Proxy**
- **OpenAI** (Example implementation, requires completion)

## Benefits

1. **Minimal Changes**: The main sampling loop remains largely unchanged
2. **DRY Code**: Provider-specific logic is encapsulated in handlers
3. **Easy Expansion**: New providers can be added by implementing the protocol
4. **Database Consistency**: All data is stored in a single format regardless of provider
5. **Type Safety**: Protocol-based design ensures all required methods are implemented