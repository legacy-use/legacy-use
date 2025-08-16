import asyncio
import logging
from typing import Literal, cast, Dict, Any

import httpx
from anthropic.types.beta import (
    BetaToolComputerUse20241022Param,
    BetaToolComputerUse20250124Param,
)

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
    api_type: Literal['computer_20241022', 'computer_20250124'] = 'computer_20241022'

    @property
    def options(self):
        return {
            'display_width_px': self.width,
            'display_height_px': self.height,
            'display_number': self.display_num,
        }

    def to_params(
        self,
    ) -> BetaToolComputerUse20241022Param | BetaToolComputerUse20250124Param:
        # redundant return type to satisfy type checker :(
        if self.api_type == 'computer_20241022':
            return BetaToolComputerUse20241022Param(
                name=self.name,
                type=self.api_type,
                display_width_px=self.width,
                display_height_px=self.height,
                display_number=self.display_num,
            )
        elif self.api_type == 'computer_20250124':
            return BetaToolComputerUse20250124Param(
                name=self.name,
                type=self.api_type,
                display_width_px=self.width,
                display_height_px=self.height,
                display_number=self.display_num,
            )
        raise ValueError(f'Invalid API type: {self.api_type}')

    def internal_spec(self) -> dict:
        return {
            'name': 'computer',
            'version': self.api_type,
            'description': 'Remote computer control tool',
            'actions': [
                # Base actions
                {'name': 'screenshot', 'params': {}},
                {
                    'name': 'left_click',
                    'params': {
                        'coordinate': {
                            'type': 'array',
                            'items': {'type': 'integer'},
                            'minItems': 2,
                            'maxItems': 2,
                        }
                    },
                    'required': ['coordinate'],
                },
                {
                    'name': 'mouse_move',
                    'params': {
                        'coordinate': {
                            'type': 'array',
                            'items': {'type': 'integer'},
                            'minItems': 2,
                            'maxItems': 2,
                        }
                    },
                    'required': ['coordinate'],
                },
                {
                    'name': 'type',
                    'params': {'text': {'type': 'string'}},
                    'required': ['text'],
                    'description': 'Type the given text',
                },
                {
                    'name': 'key',
                    'params': {'text': {'type': 'string'}},
                    'required': ['text'],
                    'description': 'Press the given key. This can be a single key or a combination of keys. For example, "ctrl+c" or "ctrl+shift+c".',
                },
                # Enhanced actions
                {
                    'name': 'scroll',
                    'params': {
                        'scroll_direction': {'enum': ['up', 'down', 'left', 'right']},
                        'scroll_amount': {'type': 'integer', 'minimum': 0},
                    },
                    'required': ['scroll_direction', 'scroll_amount'],
                    'description': 'Scroll the screen in the given direction',
                },
                {
                    'name': 'left_click_drag',
                    'params': {
                        'coordinate': {
                            'type': 'array',
                            'items': {'type': 'integer'},
                            'minItems': 2,
                            'maxItems': 2,
                        },
                        'to': {
                            'type': 'array',
                            'items': {'type': 'integer'},
                            'minItems': 2,
                            'maxItems': 2,
                        },
                    },
                    'required': ['coordinate', 'to'],
                    'description': 'Drag the mouse from the given coordinate to the given coordinate with the mouse button held down',
                },
                {
                    'name': 'right_click',
                    'params': {
                        'coordinate': {
                            'type': 'array',
                            'items': {'type': 'integer'},
                            'minItems': 2,
                            'maxItems': 2,
                        }
                    },
                    'required': ['coordinate'],
                    'description': 'Click the right mouse button at the given coordinate',
                },
                {
                    'name': 'middle_click',
                    'params': {
                        'coordinate': {
                            'type': 'array',
                            'items': {'type': 'integer'},
                            'minItems': 2,
                            'maxItems': 2,
                        }
                    },
                    'required': ['coordinate'],
                    'description': 'Click the middle mouse button at the given coordinate',
                },
                {
                    'name': 'double_click',
                    'params': {
                        'coordinate': {
                            'type': 'array',
                            'items': {'type': 'integer'},
                            'minItems': 2,
                            'maxItems': 2,
                        }
                    },
                    'required': ['coordinate'],
                },
                {
                    'name': 'triple_click',
                    'params': {
                        'coordinate': {
                            'type': 'array',
                            'items': {'type': 'integer'},
                            'minItems': 2,
                            'maxItems': 2,
                        }
                    },
                    'required': ['coordinate'],
                },
                {
                    'name': 'left_mouse_down',
                    'params': {
                        'coordinate': {
                            'type': 'array',
                            'items': {'type': 'integer'},
                            'minItems': 2,
                            'maxItems': 2,
                        }
                    },
                    'required': ['coordinate'],
                },
                {
                    'name': 'left_mouse_up',
                    'params': {
                        'coordinate': {
                            'type': 'array',
                            'items': {'type': 'integer'},
                            'minItems': 2,
                            'maxItems': 2,
                        }
                    },
                    'required': ['coordinate'],
                },
                {
                    'name': 'hold_key',
                    'params': {
                        'text': {'type': 'string'},
                        'duration': {'type': 'number'},
                    },
                    'required': ['text', 'duration'],
                },
                {
                    'name': 'wait',
                    'params': {'duration': {'type': 'number'}},
                    'required': ['duration'],
                    'description': 'Wait for the given duration in seconds',
                },
            ],
            'options': self.options,
            'normalization': {
                'key_aliases': True,
                'scroll_units': 'wheel_notches',
            },
        }

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
        payload: Dict[str, Any] = {'api_type': self.api_type}
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

        response = None

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(api_url, json=payload)

                if not response.is_success:
                    result = None
                    try:
                        result = response.json()
                    except Exception:
                        result = response.text or f'HTTP {response.status_code}'

                    return ToolResult(
                        output=None,
                        error=result,
                        base64_image=None,
                    )

                result = response.json()
                if isinstance(result, dict):
                    return ToolResult(
                        output=result.get('output'),
                        error=result.get('error'),
                        base64_image=result.get('base64_image'),
                    )

                return ToolResult(output=response.text)

        except Exception as e:
            logger.error(f'Unexpected error in _forward_request for {action}: {str(e)}')
            if response is not None:
                logger.error(
                    f"API error response for action '{action}' with status: {response.status_code} and content: {response.text}"
                )
                return ToolResult(output=None, error=response.text)
            logger.error(
                f"Exception in _forward_request for action '{action}' with error: {type(e).__name__}: {e}"
            )
            raise ToolError(f'Unexpected error: {str(e)}') from e


class ComputerTool20241022(BaseComputerTool, BaseAnthropicTool):
    api_type = 'computer_20241022'

    def to_params(self) -> BetaToolComputerUse20241022Param:
        return BetaToolComputerUse20241022Param(
            name=self.name,
            type=cast(Literal['computer_20241022'], self.api_type),
            display_width_px=self.width,
            display_height_px=self.height,
            display_number=self.display_num,
        )


class ComputerTool20250124(BaseComputerTool, BaseAnthropicTool):
    api_type = 'computer_20250124'

    def to_params(self) -> BetaToolComputerUse20250124Param:
        return BetaToolComputerUse20250124Param(
            name=self.name,
            type=cast(Literal['computer_20250124'], self.api_type),
            display_width_px=self.width,
            display_height_px=self.height,
            display_number=self.display_num,
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
