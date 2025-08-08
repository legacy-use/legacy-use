import asyncio
import logging
from typing import Literal, cast, Dict, Any

import httpx
from anthropic.types.beta import BetaToolComputerUse20241022Param, BetaToolUnionParam

from .base import BaseAnthropicTool, ToolError, ToolResult

Action_20241022 = Literal[
    'key',
    'type',
    'mouse_move',
    'left_click',
    'left_click_drag',
    'right_click',
    'middle_click',
    'double_click',
    'screenshot',
    'cursor_position',
]

Action_20250124 = (
    Action_20241022
    | Literal[
        'left_mouse_down',
        'left_mouse_up',
        'scroll',
        'hold_key',
        'wait',
        'triple_click',
    ]
)

ScrollDirection = Literal['up', 'down', 'left', 'right']


class BaseComputerTool(BaseAnthropicTool):
    """
    A tool that allows the agent to interact with the screen, keyboard, and mouse of a remote computer.
    All actions are forwarded to the target container via HTTP requests.
    """

    name: Literal['computer'] = 'computer'
    width: int = 1024  # Default width
    height: int = 768  # Default height
    display_num: int = 1  # Default display number

    @property
    def options(self):
        return {
            'display_width_px': self.width,
            'display_height_px': self.height,
            'display_number': self.display_num,
        }

    def to_params(self) -> BetaToolComputerUse20241022Param:
        return {'name': self.name, 'type': self.api_type, **self.options}

    async def __call__(
        self,
        *,
        session_id: str,
        action: Action_20241022,
        text: str | None = None,
        coordinate: tuple[int, int] | None = None,
        **kwargs,
    ):
        return await self._forward_request(
            session_id, action, text, coordinate, **kwargs
        )

    async def _forward_request(
        self,
        session_id: str,
        action: Action_20241022 | Action_20250124,
        text: str | None = None,
        coordinate: tuple[int, int] | None = None,
        scroll_direction: ScrollDirection | None = None,
        scroll_amount: int | None = None,
        duration: int | float | None = None,
        key: str | None = None,
        session: Dict[str, Any] | None = None,
        **kwargs,
    ):
        """Forward the request to the target container."""
        # Set up logger
        logger = logging.getLogger(__name__)

        # Check for cancellation
        await asyncio.sleep(0)

        # Use provided session object or fall back to session_id for backward compatibility
        if session is None:
            raise ToolError('Session object is required')

        # Get the container ID
        container_id = session.get('container_id')
        if not container_id:
            raise ToolError(f'Container ID not found for session {session_id}')

        # Get the container IP address
        container_ip = session.get('container_ip')
        if not container_ip:
            raise ToolError(f'Container IP not found for session {session_id}')

        # Construct the API URL using container IP and the standard port (8088)
        api_url = f'http://{container_ip}:8088/tool_use/{action}'

        # Create an HTTP client with a longer timeout
        timeout = httpx.Timeout(60.0, connect=10.0)

        # Construct the payload with only non-None parameters
        payload = {'api_type': self.api_type}
        if text is not None:
            payload['text'] = text
        if coordinate is not None:
            payload['coordinate'] = coordinate
        if scroll_direction is not None:
            payload['scroll_direction'] = scroll_direction
        if scroll_amount is not None:
            payload['scroll_amount'] = scroll_amount
        if duration is not None:
            payload['duration'] = duration
        if key is not None:
            payload['key'] = key

        # Add any additional parameters from kwargs
        for k, v in kwargs.items():
            if v is not None:
                payload[k] = v

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(api_url, json=payload)

                # Parse the response
                result = response.json()

                # Convert the response to a ToolResult
                return ToolResult(
                    output=result.get('output'),
                    error=result.get('error'),
                    base64_image=result.get('base64_image'),
                )

        except Exception as e:
            logger.error(f'Unexpected error in _forward_request for {action}: {str(e)}')
            raise ToolError(f'Unexpected error: {str(e)}') from e


class ComputerTool20241022(BaseComputerTool, BaseAnthropicTool):
    api_type: Literal['computer_20241022'] = 'computer_20241022'

    def to_params(self) -> BetaToolComputerUse20241022Param:
        return {'name': self.name, 'type': self.api_type, **self.options}


class ComputerTool20250124(BaseComputerTool, BaseAnthropicTool):
    api_type: Literal['computer_20250124'] = 'computer_20250124'

    def to_params(self):
        return cast(
            BetaToolUnionParam,
            {'name': self.name, 'type': self.api_type, **self.options},
        )

    async def __call__(
        self,
        *,
        session_id: str,
        action: Action_20250124,
        text: str | None = None,
        coordinate: tuple[int, int] | None = None,
        scroll_direction: ScrollDirection | None = None,
        scroll_amount: int | None = None,
        duration: int | float | None = None,
        key: str | None = None,
        **kwargs,
    ):
        return await self._forward_request(
            session_id=session_id,
            action=action,
            text=text,
            coordinate=coordinate,
            scroll_direction=scroll_direction,
            scroll_amount=scroll_amount,
            duration=duration,
            key=key,
            **kwargs,
        )
