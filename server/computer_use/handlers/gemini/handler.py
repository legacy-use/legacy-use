"""
Gemini provider handler implementation.

This handler manages all Gemini-specific logic and mapping between Gemini's format
and the Anthropic format used for DB storage.

Supports both Google AI Studio (direct API) and Vertex AI endpoints.
"""

from typing import Any, Optional

import httpx
import instructor
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
)

from server.computer_use.config import APIProvider
from server.computer_use.handlers.base import BaseProviderHandler
from server.computer_use.handlers.utils.converter_utils import (
    internal_specs_to_gemini_functions,
)
from server.computer_use.logging import logger
from server.computer_use.tools.collection import ToolCollection
from server.settings import settings
from server.utils.telemetry import capture_ai_generation

from .message_converter import convert_anthropic_to_gemini_messages
from .response_converter import convert_gemini_to_anthropic_response


class GeminiHandler(BaseProviderHandler):
    """
    Handler for Google Gemini API providers (AI Studio and Vertex AI).
    """

    def __init__(
        self,
        provider: APIProvider,
        model: str,
        tenant_schema: str,
        only_n_most_recent_images: Optional[int] = None,
        max_retries: int = 3,
        **kwargs,
    ):
        """
        Initialize the Gemini handler.

        Args:
            provider: The specific Gemini provider variant (GEMINI or GEMINI_VERTEX)
            model: Model identifier (e.g., 'gemini-3-pro')
            tenant_schema: Tenant schema for settings lookup
            only_n_most_recent_images: Number of recent images to keep
            max_retries: Maximum number of retries for API calls
            **kwargs: Additional provider-specific parameters
        """
        super().__init__(
            tenant_schema=tenant_schema,
            only_n_most_recent_images=only_n_most_recent_images,
            max_retries=max_retries,
            **kwargs,
        )
        self.provider = provider
        self.model = model

    async def initialize_client(
        self, api_key: str, **kwargs
    ) -> instructor.AsyncInstructor:
        """
        Initialize Gemini client using instructor.

        For GEMINI: Uses Google AI Studio with GOOGLE_API_KEY
        For GEMINI_VERTEX: Uses Vertex AI with GCP credentials (ADC)
        """
        if self.provider == APIProvider.GEMINI_VERTEX:
            # Vertex AI uses Application Default Credentials
            # Get project and location from tenant settings or global settings
            project = self.tenant_setting('GOOGLE_CLOUD_PROJECT') or getattr(
                settings, 'GOOGLE_CLOUD_PROJECT', None
            )
            location = self.tenant_setting('GOOGLE_CLOUD_LOCATION') or getattr(
                settings, 'GOOGLE_CLOUD_LOCATION', 'us-central1'
            )

            logger.info(
                f'Initializing Gemini Vertex AI client - '
                f'project: {project}, location: {location}'
            )

            # Use instructor's from_provider with vertexai=True
            client = instructor.from_provider(
                f'google/{self.model}',
                vertexai=True,
                async_client=True,
            )
        else:
            # Google AI Studio - use API key
            tenant_key = self.tenant_setting('GOOGLE_API_KEY')
            final_api_key = tenant_key or api_key

            if not final_api_key:
                raise ValueError(
                    'Google API key is required. Please provide either '
                    'GOOGLE_API_KEY tenant setting or api_key parameter.'
                )

            logger.info('Initializing Gemini AI Studio client')

            # Configure the genai library with the API key
            import google.generativeai as genai

            genai.configure(api_key=final_api_key)

            # Use instructor's from_provider for consistent interface
            client = instructor.from_provider(
                f'google/{self.model}',
                async_client=True,
            )

        return client

    def prepare_system(self, system_prompt: str) -> str:
        """
        Prepare system prompt for Gemini.

        Gemini uses system_instruction parameter, which is a simple string.
        """
        return system_prompt

    def convert_to_provider_messages(
        self, messages: list[BetaMessageParam]
    ) -> list[dict[str, Any]]:
        """
        Convert Anthropic-format messages to Gemini format.
        """
        # Apply common preprocessing (image filtering)
        messages = self.preprocess_messages(messages)
        return convert_anthropic_to_gemini_messages(messages)

    def prepare_tools(self, tool_collection: ToolCollection) -> list[dict[str, Any]]:
        """Convert tool collection to Gemini format."""
        tools = internal_specs_to_gemini_functions(list(tool_collection.tools))
        logger.debug(f'Gemini tools after conversion: {[t.get("name") for t in tools]}')
        return tools

    async def make_ai_request(
        self,
        client: instructor.AsyncInstructor,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs,
    ) -> tuple[Any, httpx.Request, httpx.Response]:
        """Make raw API call to Gemini and return provider-specific response."""
        from google import genai
        from google.genai import types

        # Build the generation config
        generation_config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
            system_instruction=system if system else None,
        )

        # Build tool declarations
        if tools:
            function_declarations = [
                types.FunctionDeclaration(
                    name=tool['name'],
                    description=tool.get('description', ''),
                    parameters=tool.get('parameters'),
                )
                for tool in tools
            ]
            generation_config.tools = [
                types.Tool(function_declarations=function_declarations)
            ]

        # Convert messages to Gemini Content format
        contents = []
        for msg in messages:
            role = msg.get('role', 'user')
            parts_data = msg.get('parts', [])

            # Convert parts
            parts = []
            for part_data in parts_data:
                if 'text' in part_data:
                    parts.append(types.Part.from_text(text=part_data['text']))
                elif 'inline_data' in part_data:
                    inline = part_data['inline_data']
                    parts.append(
                        types.Part.from_bytes(
                            data=inline.get('data', '').encode('utf-8')
                            if isinstance(inline.get('data'), str)
                            else inline.get('data', b''),
                            mime_type=inline.get('mime_type', 'image/png'),
                        )
                    )
                elif 'function_call' in part_data:
                    fc = part_data['function_call']
                    parts.append(
                        types.Part.from_function_call(
                            name=fc.get('name', ''),
                            args=fc.get('args', {}),
                        )
                    )
                elif 'function_response' in part_data:
                    fr = part_data['function_response']
                    parts.append(
                        types.Part.from_function_response(
                            name=fr.get('name', ''),
                            response=fr.get('response', {}),
                        )
                    )

            contents.append(types.Content(role=role, parts=parts))

        # Log debug information
        logger.debug(f'Gemini request - model: {model}, messages: {len(contents)}')
        logger.debug(f'Messages: {self._truncate_for_debug(messages)}')

        # Create client and make request
        # Note: instructor wraps the client, so we need to access the underlying client
        genai_client = genai.Client()

        response = await genai_client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=generation_config,
        )

        logger.debug(f'Gemini response: {response}')

        # For Gemini, we don't have direct access to the HTTP request/response
        # Create placeholder objects
        request = httpx.Request(
            'POST',
            f'https://generativelanguage.googleapis.com/v1/models/{model}:generateContent',
        )
        http_response = httpx.Response(200)

        return response, request, http_response

    def _extract_usage(self, response: Any) -> dict[str, int]:
        """Extract token usage from Gemini response."""
        usage = {
            'input_tokens': 0,
            'output_tokens': 0,
        }

        usage_metadata = getattr(response, 'usage_metadata', None)
        if usage_metadata:
            usage['input_tokens'] = (
                getattr(usage_metadata, 'prompt_token_count', 0) or 0
            )
            usage['output_tokens'] = (
                getattr(usage_metadata, 'candidates_token_count', 0) or 0
            )

        return usage

    def _capture_generation(
        self,
        response: Any,
        job_id: str,
        iteration_count: int,
        temperature: float,
        max_tokens: int,
    ) -> None:
        """Capture telemetry for the generation."""
        usage = self._extract_usage(response)

        capture_ai_generation(
            ai_trace_id=job_id,
            ai_parent_id=str(iteration_count),
            ai_provider=str(self.provider),
            ai_model=self.model,
            ai_input_tokens=usage['input_tokens'],
            ai_output_tokens=usage['output_tokens'],
            ai_cache_read_input_tokens=None,
            ai_cache_creation_input_tokens=None,
            ai_temperature=temperature,
            ai_max_tokens=max_tokens,
        )

    async def execute(
        self,
        job_id: str,
        iteration_count: int,
        client: instructor.AsyncInstructor,
        messages: list[BetaMessageParam],
        system: str,
        tools: ToolCollection,
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        **kwargs,
    ) -> tuple[list[BetaContentBlockParam], str, httpx.Request, httpx.Response]:
        """Make API call to Gemini and return standardized response format."""
        # Convert inputs to provider format
        gemini_messages = self.convert_to_provider_messages(messages)
        system_str = self.prepare_system(system)
        gemini_tools = self.prepare_tools(tools)

        response, request, raw_response = await self.make_ai_request(
            client=client,
            messages=gemini_messages,
            system=system_str,
            tools=gemini_tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        self._capture_generation(
            response=response,
            job_id=job_id,
            iteration_count=iteration_count,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Convert response to standardized format
        content_blocks, stop_reason = self.convert_from_provider_response(response)

        return content_blocks, stop_reason, request, raw_response

    def convert_from_provider_response(
        self, response: Any
    ) -> tuple[list[BetaContentBlockParam], str]:
        """
        Convert Gemini response to Anthropic format blocks and stop reason.
        """
        return convert_gemini_to_anthropic_response(response)
