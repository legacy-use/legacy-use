"""Response conversion utilities for Anthropic handler."""

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessage,
)

from server.computer_use.utils import _response_to_params


def convert_from_provider_response(
    response: BetaMessage,
) -> tuple[list[BetaContentBlockParam], str]:
    """Convert Anthropic response to content blocks and stop reason."""
    content_blocks = _response_to_params(response)
    stop_reason = response.stop_reason or 'end_turn'
    return content_blocks, stop_reason
