"""
Test script demonstrating multi-provider handler usage.

This script shows how the handler system works with different providers
without modifying the core sampling loop logic.
"""

import asyncio

from anthropic.types.beta import BetaMessageParam, BetaTextBlockParam

from server.computer_use.config import APIProvider
from server.computer_use.handlers import get_handler
from server.computer_use.logging import logger


async def test_handler_initialization():
    """Test that handlers can be initialized for different providers."""

    providers_to_test = [
        (APIProvider.ANTHROPIC, 'claude-sonnet-4-20250514'),
        (APIProvider.BEDROCK, 'eu.anthropic.claude-sonnet-4-20250514-v1:0'),
        (APIProvider.VERTEX, 'claude-sonnet-4@20250514'),
    ]

    for provider, model in providers_to_test:
        try:
            # Get handler for the provider
            handler = get_handler(
                provider=provider,
                model=model,
                token_efficient_tools_beta=False,
                only_n_most_recent_images=None,
            )

            logger.info(f'✓ Successfully created handler for {provider}')

            # Test system prompt preparation
            system_prompt = 'You are a helpful assistant.'
            system = handler.prepare_system(system_prompt)
            logger.info(f'  - System prompt prepared: {type(system)}')

            # Test message conversion (using Anthropic format as input)
            test_messages = [
                BetaMessageParam(
                    role='user',
                    content=[
                        BetaTextBlockParam(type='text', text='Hello, how are you?')
                    ],
                )
            ]

            converted_messages = handler.convert_to_provider_messages(test_messages)
            logger.info(f'  - Messages converted: {len(converted_messages)} messages')

        except NotImplementedError as e:
            logger.warning(f'⚠ Handler for {provider} not fully implemented: {e}')
        except Exception as e:
            logger.error(f'✗ Error with {provider} handler: {e}')


def demonstrate_message_conversion():
    """Demonstrate how messages are converted between formats."""

    # Example Anthropic format message (as stored in DB)
    anthropic_message = BetaMessageParam(
        role='assistant',
        content=[
            BetaTextBlockParam(type='text', text="I'll help you with that."),
            {
                'type': 'tool_use',
                'id': 'tool_123',
                'name': 'screenshot',
                'input': {},
            },
        ],
    )

    logger.info('Original Anthropic format message:')
    logger.info(f'  Role: {anthropic_message["role"]}')
    logger.info(f'  Content blocks: {len(anthropic_message["content"])}')

    # This would be converted by each handler to their specific format
    # For example, OpenAI would convert tool_use to tool_calls
    # The handler ensures bidirectional conversion


def demonstrate_provider_addition():
    """Show how easy it is to add a new provider."""

    print('\n' + '=' * 60)
    print('Adding a New Provider - Step by Step')
    print('=' * 60)

    steps = [
        ('1. Update config.py', 'Add YOUR_PROVIDER to APIProvider enum'),
        (
            '2. Create handler class',
            'Implement YourProviderHandler with all protocol methods',
        ),
        (
            '3. Register handler',
            'Add to registry.py: register_handler(APIProvider.YOUR_PROVIDER, YourProviderHandler)',
        ),
        (
            '4. Use in sampling_loop',
            'No changes needed! Just pass provider=APIProvider.YOUR_PROVIDER',
        ),
    ]

    for step, description in steps:
        print(f'\n{step}')
        print(f'  → {description}')

    print('\n' + '=' * 60)
    print("That's it! The sampling loop automatically uses the new handler.")
    print('=' * 60)


async def main():
    """Run all test demonstrations."""

    print('\n' + '=' * 60)
    print('Multi-Provider Handler System Test')
    print('=' * 60)

    # Test handler initialization
    print('\n--- Testing Handler Initialization ---')
    await test_handler_initialization()

    # Demonstrate message conversion
    print('\n--- Message Format Conversion ---')
    demonstrate_message_conversion()

    # Show how to add new providers
    demonstrate_provider_addition()

    print('\n✅ Test demonstrations complete!')


if __name__ == '__main__':
    # Note: This is a demonstration script.
    # Actual usage would be within the sampling_loop.py
    asyncio.run(main())
