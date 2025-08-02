"""
Tests for multi-provider sampling loop functionality.
Tests Anthropic, OpenAI, and UI-TARS providers with mocked requests.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
from typing import Any, Dict, List

from anthropic.types.beta import BetaMessageParam, BetaTextBlockParam

from server.computer_use.config import APIProvider
from server.computer_use.tools import ToolResult


class MockDatabaseService:
    """Mock database service for testing"""
    
    def __init__(self):
        self.messages = []
        self.sequence_counter = 1
    
    def get_next_message_sequence(self, job_id):
        return self.sequence_counter
    
    def add_job_message(self, job_id, sequence, role, content):
        self.messages.append({
            'job_id': job_id,
            'sequence': sequence,
            'role': role,
            'content': content
        })
        self.sequence_counter += 1
    
    def get_job_messages(self, job_id):
        return [msg for msg in self.messages if msg['job_id'] == job_id]
    
    def get_session(self, session_id):
        return {'container_ip': '127.0.0.1'}


class MockToolCollection:
    """Mock tool collection for testing"""
    
    def to_params(self):
        return [
            {
                'name': 'computer',
                'description': 'Use computer to perform actions',
                'input_schema': {
                    'type': 'object',
                    'properties': {
                        'action': {'type': 'string'},
                        'coordinate': {'type': 'array'}
                    }
                }
            }
        ]
    
    async def run(self, name: str, tool_input: Dict[str, Any], session_id: str = None):
        """Mock tool execution"""
        if name == 'computer':
            return ToolResult(
                output=f"Executed {tool_input.get('action', 'unknown')} action",
                error=None,
                base64_image="mock_screenshot_data"
            )
        elif name == 'extraction':
            return ToolResult(
                output='{"result": {"extracted_data": "test_value"}}',
                error=None,
                base64_image=None
            )
        else:
            return ToolResult(
                output=f"Mock result for {name}",
                error=None,
                base64_image=None
            )


@pytest.fixture
def mock_db():
    return MockDatabaseService()


@pytest.fixture
def mock_tool_collection():
    return MockToolCollection()


@pytest.fixture
def job_id():
    return uuid4()


@pytest.fixture
def sample_messages():
    return [
        BetaMessageParam(
            role='user',
            content=[BetaTextBlockParam(type='text', text='Take a screenshot')]
        )
    ]


class TestAnthropicProvider:
    """Test Anthropic provider functionality"""
    
    @pytest.mark.asyncio
    async def test_anthropic_text_response(self, mock_db, mock_tool_collection, job_id, sample_messages):
        """Test Anthropic provider with text-only response"""
        
        # Mock Anthropic response
        mock_response_data = {
            'content': [{'type': 'text', 'text': 'I understand you want me to take a screenshot.'}],
            'stop_reason': 'end_turn',
            'usage': {'input_tokens': 100, 'output_tokens': 50}
        }
        
        mock_raw_response = Mock()
        mock_raw_response.parse.return_value = Mock(
            content=[Mock(type='text', text='I understand you want me to take a screenshot.', model_dump=lambda: {'type': 'text', 'text': 'I understand you want me to take a screenshot.'})],
            stop_reason='end_turn'
        )
        mock_raw_response.http_response = Mock(request=Mock(), status_code=200)
        
        with patch('server.computer_use.sampling_loop.AsyncAnthropic') as mock_anthropic_class:
            mock_client = AsyncMock()
            mock_client.beta.messages.with_raw_response.create.return_value = mock_raw_response
            mock_anthropic_class.return_value = mock_client
            
            with patch('server.computer_use.sampling_loop.ToolCollection', return_value=mock_tool_collection):
                with patch('server.computer_use.sampling_loop.check_target_container_health', return_value={'healthy': True, 'reason': 'OK'}):
                    from server.computer_use.sampling_loop import sampling_loop
                    
                    output_callback = Mock()
                    tool_output_callback = Mock()
                    
                    # This should raise ValueError since no extraction was provided
                    with pytest.raises(ValueError, match="Model ended its turn without providing any extractions"):
                        await sampling_loop(
                            job_id=job_id,
                            db=mock_db,
                            model='claude-3-5-sonnet-20241022',
                            provider=APIProvider.ANTHROPIC,
                            system_prompt_suffix='',
                            messages=sample_messages,
                            output_callback=output_callback,
                            tool_output_callback=tool_output_callback,
                            max_tokens=1000,
                            tool_version='computer_use_20241022',
                            api_key='test-key',
                            session_id=str(uuid4())
                        )
    
    @pytest.mark.asyncio
    async def test_anthropic_tool_use_response(self, mock_db, mock_tool_collection, job_id, sample_messages):
        """Test Anthropic provider with tool use response"""
        
        # Mock Anthropic response with tool use
        mock_tool_response = Mock()
        mock_tool_response.parse.return_value = Mock(
            content=[Mock(
                type='tool_use',
                name='computer',
                id='tool_123',
                input={'action': 'screenshot'},
                model_dump=lambda: {
                    'type': 'tool_use',
                    'name': 'computer',
                    'id': 'tool_123',
                    'input': {'action': 'screenshot'}
                }
            )],
            stop_reason='tool_use'
        )
        mock_tool_response.http_response = Mock(request=Mock(), status_code=200)
        
        # Mock follow-up response after tool use
        mock_extraction_response = Mock()
        mock_extraction_response.parse.return_value = Mock(
            content=[Mock(
                type='tool_use',
                name='extraction',
                id='tool_456',
                input={'data': 'screenshot_taken'},
                model_dump=lambda: {
                    'type': 'tool_use',
                    'name': 'extraction',
                    'id': 'tool_456',
                    'input': {'data': 'screenshot_taken'}
                }
            )],
            stop_reason='tool_use'
        )
        mock_extraction_response.http_response = Mock(request=Mock(), status_code=200)
        
        # Final response after extraction
        mock_final_response = Mock()
        mock_final_response.parse.return_value = Mock(
            content=[Mock(
                type='text',
                text='Screenshot completed successfully.',
                model_dump=lambda: {'type': 'text', 'text': 'Screenshot completed successfully.'}
            )],
            stop_reason='end_turn'
        )
        mock_final_response.http_response = Mock(request=Mock(), status_code=200)
        
        with patch('server.computer_use.sampling_loop.AsyncAnthropic') as mock_anthropic_class:
            mock_client = AsyncMock()
            mock_client.beta.messages.with_raw_response.create.side_effect = [
                mock_tool_response,
                mock_extraction_response,
                mock_final_response
            ]
            mock_anthropic_class.return_value = mock_client
            
            with patch('server.computer_use.sampling_loop.ToolCollection', return_value=mock_tool_collection):
                with patch('server.computer_use.sampling_loop.check_target_container_health', return_value={'healthy': True, 'reason': 'OK'}):
                    from server.computer_use.sampling_loop import sampling_loop
                    
                    output_callback = Mock()
                    tool_output_callback = Mock()
                    
                    result, exchanges = await sampling_loop(
                        job_id=job_id,
                        db=mock_db,
                        model='claude-3-5-sonnet-20241022',
                        provider=APIProvider.ANTHROPIC,
                        system_prompt_suffix='',
                        messages=sample_messages,
                        output_callback=output_callback,
                        tool_output_callback=tool_output_callback,
                        max_tokens=1000,
                        tool_version='computer_use_20241022',
                        api_key='test-key',
                        session_id=str(uuid4())
                    )
                    
                    # Verify the result contains extracted data
                    assert result == {"extracted_data": "test_value"}
                    assert len(exchanges) == 3
                    
                    # Verify callbacks were called
                    assert output_callback.call_count >= 3
                    assert tool_output_callback.call_count >= 2


class TestMultiProviderAbstraction:
    """Test multi-provider abstraction layer"""
    
    def test_provider_factory_creation(self):
        """Test that provider factory creates correct clients"""
        from server.computer_use.multi_provider_client import MultiProviderClientFactory
        from server.computer_use.config import APIProvider
        
        # Test Anthropic client creation
        anthropic_client = MultiProviderClientFactory.create_client(
            APIProvider.ANTHROPIC, 'test-key'
        )
        assert anthropic_client is not None
        
        # Test OpenAI client creation
        openai_client = MultiProviderClientFactory.create_client(
            APIProvider.OPENAI, 'test-key'
        )
        assert openai_client is not None
        
        # Test UI-TARS client creation
        uitars_client = MultiProviderClientFactory.create_client(
            APIProvider.UITARS, 'test-key', base_url='https://test.uitars.com'
        )
        assert uitars_client is not None
    
    @pytest.mark.asyncio
    async def test_openai_provider_mock(self, mock_db, mock_tool_collection, job_id, sample_messages):
        """Test OpenAI provider with mocked responses"""
        
        # Mock OpenAI response with tool use
        mock_tool_response = Mock()
        mock_tool_response.parse.return_value = Mock(
            content=[Mock(
                type='tool_use',
                name='computer',
                id='tool_123',
                input={'action': 'screenshot'},
                model_dump=lambda: {
                    'type': 'tool_use',
                    'name': 'computer',
                    'id': 'tool_123',
                    'input': {'action': 'screenshot'}
                }
            )],
            stop_reason='tool_use'
        )
        mock_tool_response.http_response = Mock(request=Mock(), status_code=200)
        
        # Mock extraction response
        mock_extraction_response = Mock()
        mock_extraction_response.parse.return_value = Mock(
            content=[Mock(
                type='tool_use',
                name='extraction',
                id='tool_456',
                input={'data': 'screenshot_taken'},
                model_dump=lambda: {
                    'type': 'tool_use',
                    'name': 'extraction',
                    'id': 'tool_456',
                    'input': {'data': 'screenshot_taken'}
                }
            )],
            stop_reason='tool_use'
        )
        mock_extraction_response.http_response = Mock(request=Mock(), status_code=200)
        
        # Final response
        mock_final_response = Mock()
        mock_final_response.parse.return_value = Mock(
            content=[Mock(
                type='text',
                text='Screenshot completed successfully.',
                model_dump=lambda: {'type': 'text', 'text': 'Screenshot completed successfully.'}
            )],
            stop_reason='end_turn'
        )
        mock_final_response.http_response = Mock(request=Mock(), status_code=200)
        
        with patch('server.computer_use.multi_provider_client.AsyncOpenAI') as mock_openai_class:
            mock_openai_client = AsyncMock()
            
            # Mock OpenAI completion responses
            mock_completion_1 = Mock()
            mock_completion_1.choices = [Mock(
                message=Mock(
                    content=None,
                    tool_calls=[Mock(
                        id='tool_123',
                        function=Mock(
                            name='computer',
                            arguments='{"action": "screenshot"}'
                        )
                    )]
                ),
                finish_reason='tool_calls'
            )]
            mock_completion_1.usage = Mock(prompt_tokens=100, completion_tokens=50)
            
            mock_completion_2 = Mock()
            mock_completion_2.choices = [Mock(
                message=Mock(
                    content=None,
                    tool_calls=[Mock(
                        id='tool_456',
                        function=Mock(
                            name='extraction',
                            arguments='{"data": "screenshot_taken"}'
                        )
                    )]
                ),
                finish_reason='tool_calls'
            )]
            mock_completion_2.usage = Mock(prompt_tokens=150, completion_tokens=30)
            
            mock_completion_3 = Mock()
            mock_completion_3.choices = [Mock(
                message=Mock(
                    content='Screenshot completed successfully.',
                    tool_calls=None
                ),
                finish_reason='stop'
            )]
            mock_completion_3.usage = Mock(prompt_tokens=200, completion_tokens=20)
            
            mock_openai_client.chat.completions.create.side_effect = [
                mock_completion_1,
                mock_completion_2,
                mock_completion_3
            ]
            mock_openai_class.return_value = mock_openai_client
            
            with patch('server.computer_use.sampling_loop.ToolCollection', return_value=mock_tool_collection):
                with patch('server.computer_use.sampling_loop.check_target_container_health', return_value={'healthy': True, 'reason': 'OK'}):
                    from server.computer_use.sampling_loop import sampling_loop
                    
                    output_callback = Mock()
                    tool_output_callback = Mock()
                    
                    result, exchanges = await sampling_loop(
                        job_id=job_id,
                        db=mock_db,
                        model='gpt-4o',
                        provider=APIProvider.OPENAI,
                        system_prompt_suffix='',
                        messages=sample_messages,
                        output_callback=output_callback,
                        tool_output_callback=tool_output_callback,
                        max_tokens=1000,
                        tool_version='computer_use_20241022',
                        api_key='test-key',
                        session_id=str(uuid4())
                    )
                    
                    # Verify the result contains extracted data
                    assert result == {"extracted_data": "test_value"}
                    assert len(exchanges) == 3
    
    @pytest.mark.asyncio
    async def test_uitars_provider_mock(self, mock_db, mock_tool_collection, job_id, sample_messages):
        """Test UI-TARS provider with mocked responses"""
        
        # Mock UI-TARS HTTP responses
        mock_responses = [
            # Tool use response
            {
                'choices': [
                    {
                        'message': {
                            'content': None,
                            'tool_calls': [
                                {
                                    'id': 'tool_123',
                                    'function': {
                                        'name': 'computer',
                                        'arguments': '{"action": "screenshot"}'
                                    }
                                }
                            ]
                        },
                        'finish_reason': 'tool_calls'
                    }
                ],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 50}
            },
            # Extraction response
            {
                'choices': [
                    {
                        'message': {
                            'content': None,
                            'tool_calls': [
                                {
                                    'id': 'tool_456',
                                    'function': {
                                        'name': 'extraction',
                                        'arguments': '{"data": "screenshot_taken"}'
                                    }
                                }
                            ]
                        },
                        'finish_reason': 'tool_calls'
                    }
                ],
                'usage': {'prompt_tokens': 150, 'completion_tokens': 30}
            },
            # Final response
            {
                'choices': [
                    {
                        'message': {
                            'content': 'Screenshot completed successfully.',
                            'tool_calls': None
                        },
                        'finish_reason': 'stop'
                    }
                ],
                'usage': {'prompt_tokens': 200, 'completion_tokens': 20}
            }
        ]
        
        with patch('httpx.AsyncClient') as mock_httpx_class:
            mock_client = AsyncMock()
            mock_httpx_class.return_value.__aenter__.return_value = mock_client
            
            # Create mock responses
            mock_http_responses = []
            for response_data in mock_responses:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = response_data
                mock_response.raise_for_status.return_value = None
                mock_http_responses.append(mock_response)
            
            mock_client.post.side_effect = mock_http_responses
            
            with patch('server.computer_use.sampling_loop.ToolCollection', return_value=mock_tool_collection):
                with patch('server.computer_use.sampling_loop.check_target_container_health', return_value={'healthy': True, 'reason': 'OK'}):
                    from server.computer_use.sampling_loop import sampling_loop
                    
                    output_callback = Mock()
                    tool_output_callback = Mock()
                    
                    result, exchanges = await sampling_loop(
                        job_id=job_id,
                        db=mock_db,
                        model='uitars-1.5',
                        provider=APIProvider.UITARS,
                        system_prompt_suffix='',
                        messages=sample_messages,
                        output_callback=output_callback,
                        tool_output_callback=tool_output_callback,
                        max_tokens=1000,
                        tool_version='computer_use_20241022',
                        api_key='test-key',
                        session_id=str(uuid4())
                    )
                    
                    # Verify the result contains extracted data
                    assert result == {"extracted_data": "test_value"}
                    assert len(exchanges) == 3


class TestErrorHandling:
    """Test error handling across providers"""
    
    @pytest.mark.asyncio
    async def test_api_error_handling(self, mock_db, mock_tool_collection, job_id, sample_messages):
        """Test API error handling"""
        
        with patch('server.computer_use.sampling_loop.AsyncAnthropic') as mock_anthropic_class:
            mock_client = AsyncMock()
            mock_client.beta.messages.with_raw_response.create.side_effect = Exception("API Error")
            mock_anthropic_class.return_value = mock_client
            
            with patch('server.computer_use.sampling_loop.ToolCollection', return_value=mock_tool_collection):
                with patch('server.computer_use.sampling_loop.check_target_container_health', return_value={'healthy': True, 'reason': 'OK'}):
                    from server.computer_use.sampling_loop import sampling_loop
                    
                    output_callback = Mock()
                    tool_output_callback = Mock()
                    
                    with pytest.raises(Exception, match="API Error"):
                        await sampling_loop(
                            job_id=job_id,
                            db=mock_db,
                            model='claude-3-5-sonnet-20241022',
                            provider=APIProvider.ANTHROPIC,
                            system_prompt_suffix='',
                            messages=sample_messages,
                            output_callback=output_callback,
                            tool_output_callback=tool_output_callback,
                            max_tokens=1000,
                            tool_version='computer_use_20241022',
                            api_key='test-key',
                            session_id=str(uuid4())
                        )
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self, mock_db, mock_tool_collection, job_id, sample_messages):
        """Test health check failure handling"""
        
        # Mock tool use response
        mock_tool_response = Mock()
        mock_tool_response.parse.return_value = Mock(
            content=[Mock(
                type='tool_use',
                name='computer',
                id='tool_123',
                input={'action': 'screenshot'},
                model_dump=lambda: {
                    'type': 'tool_use',
                    'name': 'computer',
                    'id': 'tool_123',
                    'input': {'action': 'screenshot'}
                }
            )],
            stop_reason='tool_use'
        )
        mock_tool_response.http_response = Mock(request=Mock(), status_code=200)
        
        with patch('server.computer_use.sampling_loop.AsyncAnthropic') as mock_anthropic_class:
            mock_client = AsyncMock()
            mock_client.beta.messages.with_raw_response.create.return_value = mock_tool_response
            mock_anthropic_class.return_value = mock_client
            
            with patch('server.computer_use.sampling_loop.ToolCollection', return_value=mock_tool_collection):
                with patch('server.computer_use.sampling_loop.check_target_container_health', return_value={'healthy': False, 'reason': 'Container not responding'}):
                    from server.computer_use.sampling_loop import sampling_loop
                    
                    output_callback = Mock()
                    tool_output_callback = Mock()
                    
                    result, exchanges = await sampling_loop(
                        job_id=job_id,
                        db=mock_db,
                        model='claude-3-5-sonnet-20241022',
                        provider=APIProvider.ANTHROPIC,
                        system_prompt_suffix='',
                        messages=sample_messages,
                        output_callback=output_callback,
                        tool_output_callback=tool_output_callback,
                        max_tokens=1000,
                        tool_version='computer_use_20241022',
                        api_key='test-key',
                        session_id=str(uuid4())
                    )
                    
                    # Should return error result
                    assert result['success'] is False
                    assert result['error'] == 'Target Health Check Failed'
                    assert 'Container not responding' in result['error_description']


if __name__ == '__main__':
    pytest.main([__file__])