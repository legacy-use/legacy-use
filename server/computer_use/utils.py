"""
Utility functions for Computer Use API Gateway.
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional, cast

from anthropic.types.beta import (
    BetaCacheControlEphemeralParam,
    BetaContentBlockParam,
    BetaImageBlockParam,
    BetaMessage,
    BetaMessageParam,
    BetaTextBlock,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
    BetaToolUseBlockParam,
)

from server.computer_use.logging import logger
from server.computer_use.tools import ToolResult


def _load_system_prompt(system_prompt_suffix: str = '') -> str:
    """
    Load and format the system prompt with current values.

    Args:
        system_prompt_suffix: Optional additional text to append to the system prompt
    """
    # Define the system prompt directly in the code
    system_prompt = """<SYSTEM_CAPABILITY>
* IMPORTANT BEHAVIOUR: If you want to click a button, make sure you click it right in the center of the button. If you want to type the Windows key, use Super_L instead.
* IMPORTANT UI CHECKING: After most computer function calls, you receive a screenshot back. Do verify that the screenshot is what you expected.
* IMPORTANT TOOL INPUT VALIDATION: If a tool call fails, the tool will return a ToolResult with an error message. Always check the ToolResult for an error message and fix the input before calling the tool again. IF THE ERROR PERSISTS FOR MORE THAN 2 TURNS, CALL THE ui_not_as_expected TOOL!
* If the UI doesn't match your expectations or looks different, use the ui_not_as_expected tool to report it with a clear explanation. The user has written the prompt with an UI in mind and the UI might be different.
* If that is the case, call the ui_not_as_expected tool to ask the user how to proceed <ui_not_as_expected tool>{{'reason':'...'}}</ui_not_as_expected tool>. Do not proceed if the UI is different from what the prompt lets you expect.
* Be especially careful when you are asked to enter text, that the field you enter has focus. If the field does not have focus, call ui_not_as_expected with the reason that the field does not have focus.
* DO NOT PROCEED IF THE UI IS DIFFERENT FROM WHAT THE PROMPT LETS YOU EXPECT. DO NOT TRY TO RECTIFY IT YOURSELF. IF IN DOUBT, ASK THE USER HOW TO PROCEED VIA THE ui_not_as_expected tool.
* IMPORTANT EXTRACTION: When you've found the information requested by the user, ALWAYS use the extraction tool to return the result as structured JSON data. NEVER output JSON directly in text.
* The extraction tool should be used like this: <extraction tool>{{"name": "API_NAME", "result": {{...}}}}</extraction tool>
* When using your computer function calls, they take a while to run and send back to you. Where possible/feasible, try to chain multiple of these calls all into one function calls request.
* The current date is {current_date}.
* IMPORTANT PRIORITY: Always priotize a tool call over a text response. To send an extraction back to the user, always use the extraction tool, do not respond in a JSON format in the message.
</SYSTEM_CAPABILITY>"""

    # Format the prompt with current values
    formatted_prompt = system_prompt.format(
        current_date=datetime.today().strftime('%A, %B %-d, %Y')
    )

    # Append suffix if provided
    if system_prompt_suffix:
        formatted_prompt = f'{formatted_prompt} {system_prompt_suffix}'

    return formatted_prompt


def _response_to_params(
    response: BetaMessage,
) -> list[BetaContentBlockParam]:
    res: list[BetaContentBlockParam] = []
    for block in response.content:
        if isinstance(block, BetaTextBlock):
            if block.text:
                res.append(BetaTextBlockParam(type='text', text=block.text))
            elif getattr(block, 'type', None) == 'thinking':
                # Handle thinking blocks - include signature field
                thinking_block = {
                    'type': 'thinking',
                    'thinking': getattr(block, 'thinking', None),
                }
                if hasattr(block, 'signature'):
                    thinking_block['signature'] = getattr(block, 'signature', None)
                res.append(cast(BetaContentBlockParam, thinking_block))
        else:
            # Handle tool use blocks normally
            res.append(cast(BetaToolUseBlockParam, block.model_dump()))
    return res


def _inject_prompt_caching(
    messages: list[BetaMessageParam],
):
    """
    Set cache breakpoints for the 3 most recent turns
    one cache breakpoint is left for tools/system prompt, to be shared across sessions
    """

    breakpoints_remaining = 3
    for message in reversed(messages):
        if message['role'] == 'user' and isinstance(
            content := message['content'], list
        ):
            if breakpoints_remaining:
                breakpoints_remaining -= 1
                from typing import cast as _cast

                _cast(Dict[str, Any], content[-1])['cache_control'] = (
                    BetaCacheControlEphemeralParam({'type': 'ephemeral'})
                )
            else:
                from typing import cast as _cast

                _cast(Dict[str, Any], content[-1]).pop('cache_control', None)
                # we'll only every have one extra turn per loop
                break


def _maybe_filter_to_n_most_recent_images(
    messages: list[BetaMessageParam],
    images_to_keep: int,
    min_removal_threshold: int,
):
    """
    With the assumption that images are screenshots that are of diminishing value as
    the conversation progresses, remove all but the final `images_to_keep` tool_result
    images in place, with a chunk of min_removal_threshold to reduce the amount we
    break the implicit prompt cache.
    """
    if images_to_keep is None:
        return messages

    tool_result_blocks = cast(
        list[BetaToolResultBlockParam],
        [
            item
            for message in messages
            for item in (
                message['content'] if isinstance(message['content'], list) else []
            )
            if isinstance(item, dict) and item.get('type') == 'tool_result'
        ],
    )

    total_images = sum(
        1
        for tool_result in tool_result_blocks
        for content in tool_result.get('content', [])
        if isinstance(content, dict) and content.get('type') == 'image'
    )

    images_to_remove = total_images - images_to_keep
    # for better cache behavior, we want to remove in chunks
    images_to_remove -= images_to_remove % min_removal_threshold

    for tool_result in tool_result_blocks:
        if isinstance(tool_result.get('content'), list):
            new_content = []
            for content in tool_result.get('content', []):
                if isinstance(content, dict) and content.get('type') == 'image':
                    if images_to_remove > 0:
                        images_to_remove -= 1
                        continue
                new_content.append(content)
            tool_result['content'] = new_content


def _make_api_tool_result(
    result: ToolResult, tool_use_id: str
) -> BetaToolResultBlockParam:
    """Convert an agent ToolResult to an API ToolResultBlockParam."""
    # Check if this is an extraction tool result
    is_extraction = 'extraction' in tool_use_id

    if result.error:
        # For error case, return the error in the expected format
        from typing import cast as _cast

        return _cast(
            BetaToolResultBlockParam,
            {
                'type': 'tool_result',
                'tool_use_id': tool_use_id,
                'content': [],
                'error': _maybe_prepend_system_tool_result(result, result.error),
            },
        )

    # For success case, prepare the content
    content: list[BetaTextBlockParam | BetaImageBlockParam] = []

    if result.output:
        # Special handling for extraction tool results
        if is_extraction:
            logger.info(f'Processing extraction tool output: {result.output}')
            # Ensure proper JSON formatting for extraction results
            try:
                # Parse and validate the JSON
                json_data = json.loads(result.output)
                logger.info(f'Valid JSON extraction data: {json_data}')

                # Extract just the result field from the extraction data
                if isinstance(json_data, dict) and 'result' in json_data:
                    result_data = json_data['result']
                    # Return the formatted JSON as text
                    formatted_output = json.dumps(
                        result_data, indent=2, ensure_ascii=False
                    )
                    content.append(
                        {
                            'type': 'text',
                            'text': _maybe_prepend_system_tool_result(
                                result, formatted_output
                            ),
                        }
                    )
                else:
                    # If no result field, return the whole data
                    formatted_output = json.dumps(
                        json_data, indent=2, ensure_ascii=False
                    )
                    content.append(
                        {
                            'type': 'text',
                            'text': _maybe_prepend_system_tool_result(
                                result, formatted_output
                            ),
                        }
                    )
            except json.JSONDecodeError as e:
                logger.error(f'Invalid JSON in extraction tool output: {e}')
                # Return error message when JSON is invalid
                from typing import cast as _cast

                return _cast(
                    BetaToolResultBlockParam,
                    {
                        'type': 'tool_result',
                        'tool_use_id': tool_use_id,
                        'content': [],
                        'error': f'Error: Invalid JSON in extraction tool output: {e}',
                    },
                )
        else:
            # Standard handling for non-extraction tools
            content.append(
                {
                    'type': 'text',
                    'text': _maybe_prepend_system_tool_result(result, result.output),
                }
            )

    if result.base64_image:
        content.append(
            {
                'type': 'image',
                'source': {
                    'type': 'base64',
                    'media_type': 'image/png',
                    'data': result.base64_image,
                },
            }
        )

    # If there's no content, add a default message
    if not content:
        content.append({'type': 'text', 'text': 'system: Tool returned no output.'})

    # Return the properly formatted tool result for success case
    return {'type': 'tool_result', 'tool_use_id': tool_use_id, 'content': content}


def _maybe_prepend_system_tool_result(result: ToolResult, result_text: str):
    if result.system:
        result_text = f'<system>{result.system}</system>\n{result_text}'
    return result_text


def _job_message_to_beta_message_param(job_message: Dict[str, Any]) -> BetaMessageParam:
    """Converts a JobMessage dictionary (or model instance) to a BetaMessageParam TypedDict."""
    # Deserialize from JSON to plain dict
    restored = {
        'role': job_message.get('role'),
        'content': job_message.get('message_content'),
    }
    # Optional: cast for type checkers (runtime it's still just a dict)
    restored = cast(BetaMessageParam, restored)

    return restored


def _beta_message_param_to_job_message_content(
    beta_param: BetaMessageParam,
) -> list[Dict[str, Any]]:
    """
    Converts a BetaMessageParam TypedDict into components needed for a JobMessage
    (role and serialized message_content). Does not create a JobMessage DB model instance.
    """
    content = beta_param.get('content')
    if isinstance(content, list):
        return cast(list[Dict[str, Any]], content)
    if isinstance(content, str):
        return cast(list[Dict[str, Any]], [{'type': 'text', 'text': content}])
    return []


# Shared helpers for handlers
def normalize_key_combo(combo: str) -> str:
    """Normalize key-combination strings into a canonical form joined by '+'.

    Examples:
    - "ctrl c" -> "ctrl+c"
    - "Ctrl+Shift+del" -> "ctrl+shift+Delete"
    - "win+e" -> "Super_L+e"
    """
    if not isinstance(combo, str):
        return combo  # type: ignore[return-value]

    # Accept both separators; collapse to spaces first
    compact = combo.replace('\n', ' ').replace('\t', ' ').strip()
    compact = compact.replace('+', ' ')
    parts = [p for p in compact.split(' ') if p]

    # Order modifiers before non-modifiers
    modifier_names = {'ctrl', 'control', 'shift', 'alt', 'cmd', 'win', 'meta', 'super'}
    modifiers: list[str] = []
    keys: list[str] = []
    for p in parts:
        lp = p.lower()
        if lp in modifier_names:
            modifiers.append('ctrl' if lp in {'ctrl', 'control'} else lp)
        else:
            keys.append(p)

    ordered = modifiers + keys

    alias_map = {
        'esc': 'Escape',
        'escape': 'Escape',
        'enter': 'Return',
        'return': 'Return',
        'win': 'Super_L',
        'windows': 'Super_L',
        'super': 'Super_L',
        'meta': 'Super_L',
        'cmd': 'Super_L',
        'backspace': 'BackSpace',
        'del': 'Delete',
        'delete': 'Delete',
        'tab': 'Tab',
        'space': 'space',
        'pageup': 'Page_Up',
        'pagedown': 'Page_Down',
        'home': 'Home',
        'end': 'End',
        'up': 'Up',
        'down': 'Down',
        'left': 'Left',
        'right': 'Right',
        'printscreen': 'Print',
        'prtsc': 'Print',
    }

    def normalize_part(p: str) -> str:
        low = p.lower()
        if low in {'ctrl', 'control'}:
            return 'ctrl'
        if low in {'shift', 'alt'}:
            return low
        if low in alias_map:
            return alias_map[low]
        if low.startswith('f') and low[1:].isdigit():
            return f'F{int(low[1:])}'
        if len(p) == 1:
            return p
        return p

    normalized = [normalize_part(p) for p in ordered]
    return '+'.join(normalized)


def convert_point_resolution(
    point: tuple[int, int],
    *,
    from_resolution: tuple[int, int],
    to_resolution: tuple[int, int],
) -> tuple[int, int]:
    """Convert a coordinate from one resolution to another using independent x/y scales.

    Rounds to nearest integer to produce pixel coordinates.
    """
    print(f'Converting point {point} from {from_resolution} to {to_resolution}')
    from_w, from_h = from_resolution
    to_w, to_h = to_resolution
    if from_w <= 0 or from_h <= 0:
        return point
    scale_x = to_w / float(from_w)
    scale_y = to_h / float(from_h)
    x, y = point
    result_x, result_y = int(round(x * scale_x)), int(round(y * scale_y))
    print(f'Result: {result_x}, {result_y}')
    return result_x, result_y


def derive_center_coordinate(
    val: Any,
    *,
    scale_from: Optional[tuple[int, int]] = None,
    scale_to: Optional[tuple[int, int]] = None,
) -> Optional[tuple[int, int]]:
    """Derive a center coordinate from a point or bounding box-like value.

    Accepts strings like "x y" or "x1 y1 x2 y2", lists/tuples, or any
    value containing digits. Returns (x, y) if derivable, else None.
    """
    if val is None:
        return None
    s = str(val)
    nums = [int(n) for n in __import__('re').findall(r'\d+', s)]
    if not nums:
        return None
    if len(nums) >= 4:
        x1, y1, x2, y2 = nums[:4]
        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
    elif len(nums) >= 2:
        x1, y1 = nums[:2]
        cx, cy = int(x1), int(y1)
    else:
        return None

    # mock for now
    scale_from = (1920, 1080)
    scale_to = (1920, 1080)

    # Optional scaling support. For now, used to convert 1920x1080 → 1024x768.
    if scale_from and scale_to:
        cx, cy = convert_point_resolution(
            (cx, cy), from_resolution=scale_from, to_resolution=scale_to
        )

    return cx, cy


# ----------------------- Logging/Summary Helpers -----------------------


def summarize_beta_messages(messages: list[BetaMessageParam]) -> Dict[str, Any]:
    roles: Dict[str, int] = {}
    total_text = 0
    total_tool_result = 0
    total_images = 0
    total_thinking = 0
    for m in messages:
        r = m.get('role') or 'unknown'
        roles[r] = roles.get(r, 0) + 1
        content = m.get('content')
        if isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                t = b.get('type')
                if t == 'text':
                    total_text += 1
                elif t == 'tool_result':
                    total_tool_result += 1
                    # count images in tool_result content without printing
                    for ci in b.get('content', []) or []:
                        if isinstance(ci, dict) and ci.get('type') == 'image':
                            total_images += 1
                elif t == 'image':
                    total_images += 1
                elif t == 'thinking':
                    total_thinking += 1
    return {
        'num_messages': len(messages),
        'roles': roles,
        'text_blocks': total_text,
        'tool_result_blocks': total_tool_result,
        'images': total_images,
        'thinking_blocks': total_thinking,
    }


def summarize_openai_responses_input(messages: Any) -> Dict[str, Any]:
    # messages: ResponseInputParam (list of dicts)
    num_msgs = 0
    text_parts = 0
    image_parts = 0
    for item in messages or []:
        num_msgs += 1
        if isinstance(item, dict):
            content = item.get('content')
            if isinstance(content, list):
                for p in content:
                    if isinstance(p, dict):
                        t = p.get('type')
                        if t in ('input_text', 'text'):
                            text_parts += 1
                        elif t in ('input_image', 'image_url'):
                            image_parts += 1
    return {
        'num_messages': num_msgs,
        'text_parts': text_parts,
        'image_parts': image_parts,
    }


def summarize_openai_chat(messages: Any) -> Dict[str, Any]:
    # messages: list[ChatCompletionMessageParam]
    try:
        num_msgs = 0
        text_parts = 0
        image_parts = 0
        for m in messages or []:
            num_msgs += 1
            if isinstance(m, dict):
                content = m.get('content')
                if isinstance(content, list):
                    for p in content:
                        if isinstance(p, dict):
                            t = p.get('type')
                            if t == 'text':
                                text_parts += 1
                            elif t == 'image_url':
                                image_parts += 1
                elif isinstance(content, str):
                    text_parts += 1
        return {
            'num_messages': num_msgs,
            'text_parts': text_parts,
            'image_parts': image_parts,
        }
    except Exception:
        return {'num_messages': len(messages or []), 'text_parts': 0, 'image_parts': 0}


def summarize_beta_blocks(blocks: list[BetaContentBlockParam]) -> Dict[str, Any]:
    text_blocks = 0
    tool_use_blocks = 0
    images = 0
    for b in blocks:
        if not isinstance(b, dict):
            continue
        t = b.get('type')
        if t == 'text':
            text_blocks += 1
        elif t == 'tool_use':
            tool_use_blocks += 1
        elif t == 'image':
            images += 1
    return {
        'text_blocks': text_blocks,
        'tool_use_blocks': tool_use_blocks,
        'images': images,
    }
