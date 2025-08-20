"""Message conversion utilities for Anthropic handler."""

from typing import Any, Dict, cast

from anthropic.types.beta import (
    BetaCacheControlEphemeralParam,
    BetaMessageParam,
)


def _inject_prompt_caching(
    messages: list[BetaMessageParam],
):
    """
    Set cache breakpoints for the 3 most recent turns.
    One cache breakpoint is left for tools/system prompt, to be shared across sessions.
    """

    breakpoints_remaining = 3
    for message in reversed(messages):
        if message['role'] == 'user' and isinstance(
            content := message['content'], list
        ):
            if breakpoints_remaining:
                breakpoints_remaining -= 1
                cast(Dict[str, Any], content[-1])['cache_control'] = (
                    BetaCacheControlEphemeralParam({'type': 'ephemeral'})
                )
            else:
                cast(Dict[str, Any], content[-1]).pop('cache_control', None)
                break
