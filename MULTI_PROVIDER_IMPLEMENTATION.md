# Simplified Multi-Provider Sampling Loop Implementation

## Overview

This simplified implementation extends the existing Anthropic-based sampling loop to support multiple model providers with minimal code modifications. The solution provides a lightweight abstraction layer that maintains full compatibility with the existing sampling loop.

## Supported Providers

1. **Anthropic** (existing) - Claude models via Anthropic API
2. **OpenAI** (new) - GPT models via OpenAI API  
3. **UI-TARS 1.5** (new) - UI-TARS models via custom API
4. **Bedrock** (existing) - Claude models via AWS Bedrock
5. **Vertex** (existing) - Claude models via Google Cloud Vertex AI
6. **LegacyUse Proxy** (existing) - Custom proxy implementation

## Key Components

### 1. Simplified Multi-Provider Client (`server/computer_use/multi_provider_client.py`)

This is a lightweight abstraction layer that provides:

- **MultiProviderClient**: Single client class supporting all providers
- **BetaInterface**: Compatibility wrapper for existing sampling loop
- **Format Conversion**: Simple message/tool format conversion for OpenAI/UI-TARS
- **Mock Response Classes**: Minimal compatibility layer for non-Anthropic providers

#### Key Features:

- **Single Client Class**: One class handles all providers with simple initialization
- **Format Conversion**: Automatic conversion between Anthropic and OpenAI/UI-TARS message formats
- **Tool Support**: Full tool calling support across all providers
- **Minimal Dependencies**: Uses only essential libraries (anthropic, openai, httpx)
- **Drop-in Compatibility**: Works seamlessly with existing sampling loop

### 2. Updated Configuration (`server/computer_use/config.py`)

Added new provider types and default models:

```python
class APIProvider(StrEnum):
    ANTHROPIC = 'anthropic'
    BEDROCK = 'bedrock'
    VERTEX = 'vertex'
    LEGACYUSE_PROXY = 'legacyuse'
    OPENAI = 'openai'          # New
    UITARS = 'uitars'          # New

PROVIDER_TO_DEFAULT_MODEL_NAME = {
    # ... existing providers ...
    APIProvider.OPENAI: 'gpt-4o',
    APIProvider.UITARS: 'uitars-1.5',
}
```

### 3. Enhanced Sampling Loop (`server/computer_use/sampling_loop.py`)

Minimal changes to support multi-provider clients:

- Added import for MultiProviderClient
- Enhanced client initialization logic to use MultiProviderClient for new providers
- Maintained full backward compatibility with existing providers

### 4. Simplified Tests (`server/computer_use/test_multi_provider_sampling.py`)

Streamlined test suite including:

- **Client Creation Tests**: Verify MultiProviderClient initialization for all providers
- **OpenAI Provider Tests**: Mock OpenAI API responses and tool calling
- **UI-TARS Provider Tests**: Mock HTTP-based API interactions
- **Error Handling Tests**: API error scenarios
- **Mock Infrastructure**: Essential mocking of external dependencies

## Dependencies Added

Updated `pyproject.toml` with:

```toml
dependencies = [
    # ... existing dependencies ...
    "openai>=1.0.0",      # OpenAI API client
]
```

## Usage Examples

### OpenAI Provider

```python
# Usage is identical to existing Anthropic usage
from server.computer_use.sampling_loop import sampling_loop
from server.computer_use.config import APIProvider

result, exchanges = await sampling_loop(
    job_id=job_id,
    db=db,
    model='gpt-4o',
    provider=APIProvider.OPENAI,
    system_prompt_suffix='',
    messages=messages,
    output_callback=output_callback,
    tool_output_callback=tool_output_callback,
    max_tokens=1000,
    tool_version='computer_use_20241022',
    api_key='your-openai-api-key',
    session_id=session_id
)
```

### UI-TARS Provider

```python
result, exchanges = await sampling_loop(
    job_id=job_id,
    db=db,
    model='uitars-1.5',
    provider=APIProvider.UITARS,
    system_prompt_suffix='',
    messages=messages,
    output_callback=output_callback,
    tool_output_callback=tool_output_callback,
    max_tokens=1000,
    tool_version='computer_use_20241022',
    api_key='your-uitars-api-key',
    session_id=session_id
)
```

## Implementation Benefits

1. **Minimal Code Changes**: Existing sampling loop required only ~10 lines of changes
2. **Full Backward Compatibility**: All existing functionality preserved
3. **Unified Tool Support**: All providers support the same tool calling interface
4. **Lightweight Design**: Single client class with minimal dependencies
5. **Extensible Design**: Easy to add new providers in the future
6. **Simple Testing**: Streamlined test coverage with essential mocking

## Architecture Decisions

### Message Format Conversion

The implementation automatically converts between different message formats:

- **Anthropic Format**: Native `BetaMessageParam` with content blocks
- **OpenAI Format**: Standard chat completion format with tool calls
- **UI-TARS Format**: OpenAI-compatible format (common standard)

### Tool Calling Abstraction

All providers expose tools in the same format, with automatic conversion:

- **Input**: Anthropic-style tool schemas
- **Output**: Standardized tool use/result format
- **Execution**: Unified tool collection interface

### Error Handling

Consistent error handling across providers:

- API errors mapped to common exception types
- Health checks maintained for all providers
- Graceful fallbacks and error reporting

## Future Enhancements

1. **Streaming Support**: Add streaming response support for all providers
2. **Rate Limiting**: Provider-specific rate limiting and retry logic
3. **Cost Tracking**: Usage and cost tracking across providers
4. **Model Routing**: Intelligent routing based on task type and cost
5. **A/B Testing**: Framework for comparing provider performance

## Testing

The implementation includes comprehensive tests that can be run with:

```bash
python -m pytest server/computer_use/test_multi_provider_sampling.py -v
```

Tests cover:
- Provider client creation
- Message format conversion
- Tool calling functionality
- Error scenarios
- Health check integration
- Mock API interactions

## Configuration

### Environment Variables

For OpenAI:
- `OPENAI_API_KEY`: OpenAI API key
- `OPENAI_BASE_URL`: Optional custom base URL

For UI-TARS:
- `UITARS_API_KEY`: UI-TARS API key  
- `UITARS_BASE_URL`: UI-TARS API base URL (default: https://api.uitars.com)

### Settings Integration

The implementation integrates with the existing settings system and can be configured through environment variables or settings files.

## Conclusion

This implementation successfully extends the sampling loop to support multiple providers while maintaining the existing architecture and requiring minimal code changes. The instructor library provides a solid foundation for structured outputs and the abstraction layer ensures consistent behavior across all providers.