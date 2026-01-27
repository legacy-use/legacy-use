import argparse
import base64
import io
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import mss
from openai import OpenAI
from PIL import Image, ImageDraw
from tqdm.auto import tqdm

COMPUTER_USE_TOOL_SPEC: Dict[str, Any] = {
    'type': 'function',
    'function': {
        'name': 'computer_use',
        'description': (
            'Use a mouse and keyboard to interact with a computer, and take screenshots.\n'
            '* This is an interface to a desktop GUI. You do not have access to a terminal or '
            'applications menu. You must click on desktop icons to start applications.\n'
            '* Some applications may take time to start or process actions, so you may need to wait '
            'and take successive screenshots to see the results of your actions. E.g. if you click on '
            "Firefox and a window doesn't open, try wait and taking another screenshot.\n"
            "* The screen's resolution is dynamically detected from the host system.\n"
            '* Whenever you intend to move the cursor to click on an element like an icon, you should consult '
            'a screenshot to determine the coordinates of the element before moving the cursor.\n'
            '* Make sure to click any buttons, links, icons, etc with the cursor tip in the center of the element.'
        ),
        'parameters': {
            'type': 'object',
            'required': ['action'],
            'properties': {
                'action': {
                    'type': 'string',
                    'enum': [
                        'key',
                        'type',
                        'mouse_move',
                        'left_click',
                        'left_click_drag',
                        'right_click',
                        'middle_click',
                        'double_click',
                        'triple_click',
                        'scroll',
                        'hscroll',
                        'wait',
                        'terminate',
                        'answer',
                    ],
                    'description': 'The action to perform.',
                },
                'keys': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'Keys used with action=key.',
                },
                'text': {
                    'type': 'string',
                    'description': 'Text for action=type or action=answer.',
                },
                'coordinate': {
                    'type': 'array',
                    'items': {'type': 'number'},
                    'description': 'Target coordinate [x, y] for mouse actions.',
                },
                'pixels': {
                    'type': 'number',
                    'description': 'Scroll amount for action=scroll or action=hscroll.',
                },
                'time': {
                    'type': 'number',
                    'description': 'Seconds to wait for action=wait.',
                },
                'status': {
                    'type': 'string',
                    'enum': ['success', 'failure'],
                    'description': 'Task status for action=terminate.',
                },
            },
        },
    },
}

SYSTEM_PROMPT = """You are an automation agent with direct access to a GUI computer.
- Be precise and avoid unnecessary movements.
- Always inspect the most recent screenshot before clicking.
- If an application needs time to load, wait before taking more actions.
- You must finish by calling action=answer with the final response and action=terminate with success/failure."""


_pyautogui = None


def _ensure_display() -> None:
    if sys.platform.startswith('linux') and 'DISPLAY' not in os.environ:
        msg = (
            'DISPLAY is not set. pyautogui requires access to an X11 or virtual display '
            '(e.g., Xvfb). Example: `sudo apt install xvfb && '
            'xvfb-run -s "-screen 0 1920x1080x24" uv run python run.py ...`'
        )
        raise RuntimeError(msg)


def _get_pyautogui():
    global _pyautogui
    if _pyautogui is None:
        _ensure_display()
        import pyautogui  # type: ignore

        pyautogui.FAILSAFE = False
        _pyautogui = pyautogui
    return _pyautogui


def _now_ts() -> str:
    return time.strftime('%Y%m%d-%H%M%S')


def _ensure_xy(coordinate: Optional[List[float]]) -> List[int]:
    if not coordinate or len(coordinate) != 2:
        raise ValueError('coordinate=[x, y] is required for this action.')
    return [int(coordinate[0]), int(coordinate[1])]


def _maybe_int(value: Optional[float], default: int = 0) -> int:
    return int(value) if value is not None else default


@dataclass
class ToolResult:
    payload: Dict[str, Any]

    def as_content(self) -> List[Dict[str, Any]]:
        payload = dict(self.payload)
        screenshot = payload.pop('screenshot', None)
        action = payload.pop('_action', None)
        detail = payload.pop('detail', None)
        text_value = payload.pop('text', None)

        meta: Dict[str, Any] = {}
        for key in [
            'cursor',
            'display',
            'downscaled_size',
            'screenshot_path',
            'result',
        ]:
            if key in payload:
                meta[key] = payload.pop(key)

        lines: List[str] = []
        if action:
            lines.append(f'action={action}')
        status = payload.pop('status', None)
        if status:
            lines.append(f'status={status}')
        if detail:
            lines.append(detail)
        if text_value:
            lines.append(f'text: {text_value}')
        if meta:
            lines.append(json.dumps(meta, ensure_ascii=False))
        if payload:
            lines.append(json.dumps(payload, ensure_ascii=False))

        content: List[Dict[str, Any]] = []
        if lines:
            content.append({'type': 'text', 'text': '\n'.join(lines)})
        if screenshot:
            content.append(
                {'type': 'image_url', 'image_url': {'url': screenshot, 'detail': 'low'}}
            )
        if not content:
            content.append({'type': 'text', 'text': 'tool call completed.'})
        return content


class ComputerUseTool:
    def __init__(
        self,
        screenshot_dir: Path,
        monitor_index: int = 1,
        mouse_move_duration: float = 0.0,
        drag_duration: float = 0.15,
        image_min_pixels: int = 4096,
        image_max_pixels: int = 2_000_000,
        image_scale_factor: int = 32,
        image_quality: int = 60,
    ) -> None:
        self.screenshot_dir = screenshot_dir
        self.monitor_index = monitor_index
        self.mouse_move_duration = mouse_move_duration
        self.drag_duration = drag_duration
        self.image_min_pixels = max(1024, image_min_pixels)
        self.image_max_pixels = max(self.image_min_pixels, image_max_pixels)
        self.image_scale_factor = max(1, image_scale_factor)
        self.image_quality = max(1, min(95, image_quality))
        self.pg = _get_pyautogui()
        self.last_viewport: Dict[str, Any] = {}
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def call(self, params: Dict[str, Any]) -> ToolResult:
        action = params['action']
        handler = {
            'mouse_move': self._mouse_move,
            'left_click': self._left_click,
            'right_click': self._right_click,
            'middle_click': self._middle_click,
            'double_click': self._double_click,
            'triple_click': self._triple_click,
            'left_click_drag': self._left_click_drag,
            'scroll': self._scroll,
            'hscroll': self._hscroll,
            'type': self._type,
            'key': self._key,
            'wait': self._wait,
            'answer': self._answer,
            'terminate': self._terminate,
        }.get(action)

        if handler is None:
            raise ValueError(f'Unsupported action: {action}')

        result = handler(params)
        result['_action'] = action
        if action in {'answer', 'terminate'}:
            return ToolResult(payload=result)
        return ToolResult(payload=self._attach_screenshot(result))

    def capture_observation(self) -> Dict[str, Any]:
        """초기 상태 공유용 스크린샷 캡처."""
        return self._attach_screenshot({'status': 'observe'})

    def _mouse_move(self, params: Dict[str, Any]) -> Dict[str, Any]:
        abs_x, abs_y = self._absolute_xy(params.get('coordinate'))
        print(f'[Move] Target=({abs_x}, {abs_y})')
        self.pg.moveTo(abs_x, abs_y, duration=self.mouse_move_duration)
        return {'status': 'ok', 'detail': f'Moved to ({abs_x}, {abs_y}).'}

    def _left_click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        coord = params.get('coordinate')
        if coord:
            abs_x, abs_y = self._absolute_xy(coord)
            before_pos = self.pg.position()
            print(
                f'[Left Click] Target=({abs_x}, {abs_y}) cursor_before=({before_pos.x}, {before_pos.y})'
            )
            self.pg.moveTo(abs_x, abs_y, duration=self.mouse_move_duration)
            after_pos = self.pg.position()
            print(f'[Left Click] cursor_after=({after_pos.x}, {after_pos.y})')
            self.pg.mouseDown(abs_x, abs_y, button='left')
            self.pg.mouseUp(abs_x, abs_y, button='left')
            detail = f'Left click at ({abs_x}, {abs_y}).'
        else:
            self.pg.click(button='left')
            detail = 'Left click at current cursor.'
        return {'status': 'ok', 'detail': detail}

    def _right_click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        coord = params.get('coordinate')
        if coord:
            abs_x, abs_y = self._absolute_xy(coord)
            self.pg.click(abs_x, abs_y, button='right')
            detail = f'Right click at ({abs_x}, {abs_y}).'
        else:
            self.pg.click(button='right')
            detail = 'Right click at current cursor.'
        return {'status': 'ok', 'detail': detail}

    def _middle_click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        coord = params.get('coordinate')
        if coord:
            abs_x, abs_y = self._absolute_xy(coord)
            self.pg.click(abs_x, abs_y, button='middle')
            detail = f'Middle click at ({abs_x}, {abs_y}).'
        else:
            self.pg.click(button='middle')
            detail = 'Middle click at current cursor.'
        return {'status': 'ok', 'detail': detail}

    def _double_click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        abs_x, abs_y = self._absolute_xy(params.get('coordinate'))
        self.pg.doubleClick(abs_x, abs_y)
        return {'status': 'ok', 'detail': f'Double click at ({abs_x}, {abs_y}).'}

    def _triple_click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        abs_x, abs_y = self._absolute_xy(params.get('coordinate'))
        self.pg.tripleClick(abs_x, abs_y)
        return {'status': 'ok', 'detail': f'Triple click at ({abs_x}, {abs_y}).'}

    def _left_click_drag(self, params: Dict[str, Any]) -> Dict[str, Any]:
        abs_x, abs_y = self._absolute_xy(params.get('coordinate'))
        self.pg.mouseDown()
        self.pg.dragTo(abs_x, abs_y, duration=self.drag_duration, button='left')
        self.pg.mouseUp()
        return {'status': 'ok', 'detail': f'Drag to ({abs_x}, {abs_y}).'}

    def _scroll(self, params: Dict[str, Any]) -> Dict[str, Any]:
        pixels = _maybe_int(params.get('pixels'))
        self.pg.scroll(pixels)
        return {'status': 'ok', 'detail': f'Scroll {pixels} vertically.'}

    def _hscroll(self, params: Dict[str, Any]) -> Dict[str, Any]:
        pixels = _maybe_int(params.get('pixels'))
        self.pg.hscroll(pixels)
        return {'status': 'ok', 'detail': f'Scroll {pixels} horizontally.'}

    def _type(self, params: Dict[str, Any]) -> Dict[str, Any]:
        text = params.get('text')
        if text is None:
            raise ValueError('text is required for action=type.')
        self.pg.typewrite(text, interval=0.01)
        return {'status': 'ok', 'detail': f'Typed "{text[:50]}".'}

    def _key(self, params: Dict[str, Any]) -> Dict[str, Any]:
        keys = params.get('keys') or []
        if not keys:
            raise ValueError('keys is required for action=key.')
        for key in keys:
            self.pg.keyDown(key)
        for key in reversed(keys):
            self.pg.keyUp(key)
        return {'status': 'ok', 'detail': f'Pressed keys {keys}.'}

    def _wait(self, params: Dict[str, Any]) -> Dict[str, Any]:
        duration = params.get('time')
        if duration is None:
            raise ValueError('time is required for action=wait.')
        time.sleep(float(duration))
        return {'status': 'ok', 'detail': f'Waited {duration} seconds.'}

    def _answer(self, params: Dict[str, Any]) -> Dict[str, Any]:
        text = params.get('text') or ''
        return {'status': 'answer', 'text': text}

    def _terminate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        status = params.get('status')
        if status not in {'success', 'failure'}:
            raise ValueError('status must be success or failure for action=terminate.')
        return {'status': 'terminate', 'result': status}

    def _attach_screenshot(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with mss.mss() as sct:
            monitor = sct.monitors[self.monitor_index]
            shot = sct.grab(monitor)
            img = Image.frombytes('RGB', shot.size, shot.rgb)

        cursor = self.pg.position()
        rel_x = int(cursor.x - monitor['left'])
        rel_y = int(cursor.y - monitor['top'])
        radius = 18
        highlight = ImageDraw.Draw(img)
        bbox_outer = (rel_x - radius, rel_y - radius, rel_x + radius, rel_y + radius)
        bbox_inner = (rel_x - 4, rel_y - 4, rel_x + 4, rel_y + 4)
        highlight.ellipse(bbox_outer, outline=(255, 0, 0), width=4)
        highlight.ellipse(bbox_inner, fill=(255, 255, 0))

        path = self.screenshot_dir / f'{_now_ts()}.png'
        img.save(path)

        prepared, downscaled = self._prepare_image(img)
        buffer = io.BytesIO()
        prepared.save(
            buffer,
            format='JPEG',
            quality=self.image_quality,
            optimize=True,
        )
        encoded = base64.b64encode(buffer.getvalue()).decode('ascii')

        print(
            f'[Screenshot] {path} cursor=({cursor.x}, {cursor.y}) '
            f'monitor_index={self.monitor_index}',
            flush=True,
        )
        payload.update(
            {
                'screenshot': f'data:image/jpeg;base64,{encoded}',
                'screenshot_path': str(path),
                'cursor': {'x': cursor.x, 'y': cursor.y},
                'display': {
                    'width': monitor['width'],
                    'height': monitor['height'],
                },
                'downscaled_size': {
                    'width': downscaled[0],
                    'height': downscaled[1],
                },
            }
        )
        self.last_viewport = {
            'monitor_left': monitor['left'],
            'monitor_top': monitor['top'],
            'display_width': monitor['width'],
            'display_height': monitor['height'],
            'image_width': downscaled[0],
            'image_height': downscaled[1],
            'raw_width': img.width,
            'raw_height': img.height,
        }
        return payload

    def _prepare_image(self, img: Image.Image) -> Tuple[Image.Image, Tuple[int, int]]:
        """Resize screenshots so Qwen can consume them efficiently."""
        width, height = img.size
        area = width * height
        if area == 0:
            return img, img.size

        clamped_area = min(max(area, self.image_min_pixels), self.image_max_pixels)
        scale = (clamped_area / area) ** 0.5

        def _round_size(value: float) -> int:
            return max(
                self.image_scale_factor,
                int(max(1, value) // self.image_scale_factor * self.image_scale_factor),
            )

        new_w = _round_size(width * scale)
        new_h = _round_size(height * scale)

        # 축소 후에도 픽셀이 범위를 벗어나면 한 번 더 정규화
        new_area = max(1, new_w * new_h)
        if new_area > self.image_max_pixels:
            shrink = (self.image_max_pixels / new_area) ** 0.5
            new_w = _round_size(new_w * shrink)
            new_h = _round_size(new_h * shrink)

        if new_w == width and new_h == height:
            return img, img.size

        resized = img.resize((new_w, new_h), Image.LANCZOS)
        return resized, (new_w, new_h)

    def _absolute_xy(self, coordinate: Optional[List[float]]) -> Tuple[int, int]:
        x, y = _ensure_xy(coordinate)
        viewport = self.last_viewport or {}
        left = viewport.get('monitor_left', 0)
        top = viewport.get('monitor_top', 0)
        display_w = viewport.get('display_width') or 0
        display_h = viewport.get('display_height') or 0
        image_w = viewport.get('image_width')
        image_h = viewport.get('image_height')

        if display_w and display_h:
            if x <= 1000 and y <= 1000:
                norm_x = max(0.0, min(1.0, x / 1000.0))
                norm_y = max(0.0, min(1.0, y / 1000.0))
                abs_x = left + int(norm_x * display_w)
                abs_y = top + int(norm_y * display_h)
                print(
                    f'[Coordinate Transform] relative input=({x}, {y}) '
                    f'display_size=({display_w}x{display_h}) '
                    f'offset=({left}, {top}) → abs=({abs_x}, {abs_y})'
                )
                return abs_x, abs_y

            if image_w and image_h:
                scale_x = display_w / image_w
                scale_y = display_h / image_h
                abs_x = left + int(x * scale_x)
                abs_y = top + int(y * scale_y)
                print(
                    f'[Coordinate Transform] pixel input=({x}, {y}) '
                    f'image_size=({image_w}x{image_h}) display_size=({display_w}x{display_h}) '
                    f'scale=({scale_x:.2f}, {scale_y:.2f}) offset=({left}, {top}) '
                    f'→ abs=({abs_x}, {abs_y})'
                )
                return abs_x, abs_y

        print(
            f'[Coordinate Transform] No viewport/scale, using offset only: '
            f'({left + x}, {top + y})'
        )
        return left + x, top + y


class ComputerUseAgent:
    def __init__(
        self,
        client: OpenAI,
        tool: ComputerUseTool,
        model: str,
        task: str,
        temperature: float,
        max_turns: int,
        history_window: int,
    ) -> None:
        self.client = client
        self.tool = tool
        self.model = model
        self.task = task
        self.temperature = temperature
        self.max_turns = max_turns
        self.history_window = max(1, history_window)
        self.messages: List[Dict[str, Any]] = [
            {'role': 'system', 'content': SYSTEM_PROMPT}
        ]
        self.base_count = len(self.messages)
        self._append_initial_observation()
        self.base_count = len(self.messages)
        self.final_answer: Optional[str] = None
        self.terminated: Optional[str] = None

    def run(self) -> None:
        with tqdm(
            total=self.max_turns,
            desc='Agent',
            unit='turn',
            leave=False,
            disable=self.max_turns <= 1,
        ) as progress:
            for step in range(1, self.max_turns + 1):
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=[COMPUTER_USE_TOOL_SPEC],
                    temperature=self.temperature,
                )
                message = response.choices[0].message
                self.messages.append(message)
                self._trim_messages()
                progress.update(1)

                tool_calls = message.tool_calls or []
                if not tool_calls:
                    content = message.content or ''
                    print(f'[Assistant] {content}')
                    self.final_answer = content
                    break

                for tool_call in tool_calls:
                    arguments = json.loads(tool_call.function.arguments or '{}')
                    result = self.tool.call(arguments)
                    payload = result.payload

                    if payload.get('status') == 'answer':
                        self.final_answer = payload.get('text', '')
                        print(f'[Agent Answer] {self.final_answer}')

                    if payload.get('status') == 'terminate':
                        self.terminated = payload.get('result')
                        print(f'[Terminate] status={self.terminated}')

                    self.messages.append(
                        {
                            'role': 'tool',
                            'tool_call_id': tool_call.id,
                            'name': tool_call.function.name,
                            'content': result.as_content(),
                        }
                    )
                    self._trim_messages()

                if self.terminated:
                    break

    def _append_initial_observation(self) -> None:
        observation = self.tool.capture_observation()
        screenshot = observation.get('screenshot')
        content: List[Dict[str, Any]] = []
        if screenshot:
            content.append(
                {'type': 'image_url', 'image_url': {'url': screenshot, 'detail': 'low'}}
            )
        content.append({'type': 'text', 'text': self.task})
        self.messages.append({'role': 'user', 'content': content})
        self._trim_messages(force=True)

    def _trim_messages(self, force: bool = False) -> None:
        base = self.messages[: self.base_count]
        dynamic = self.messages[self.base_count :]
        max_items = self.history_window * 2  # assistant + tool message pairs
        if not force and len(dynamic) <= max_items:
            return
        self.messages = base + dynamic[-max_items:]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Minimal computer-use agent driver.')
    parser.add_argument('--model', type=str, default='Qwen/Qwen3-VL-30B-A3B-Instruct')
    parser.add_argument(
        '--task',
        type=str,
        required=False,
        default='Open a browser and search for the weather in Seoul',
    )
    parser.add_argument('--api-key', type=str, default='EMPTY')
    parser.add_argument('--base-url', type=str, default='http://localhost:8000/v1')
    parser.add_argument('--timeout', type=float, default=600.0)
    parser.add_argument('--max-turns', type=int, default=200)
    parser.add_argument('--temperature', type=float, default=0.0)
    parser.add_argument('--screenshot-dir', type=Path, default=Path('./screenshots'))
    parser.add_argument('--monitor-index', type=int, default=1)
    parser.add_argument('--mouse-move-duration', type=float, default=0.0)
    parser.add_argument('--drag-duration', type=float, default=0.15)
    parser.add_argument(
        '--history-window',
        type=int,
        default=60,
        help='Number of assistant/tool turn pairs to keep in context.',
    )
    parser.add_argument(
        '--image-min-pixels',
        type=int,
        default=4096,
        help='Minimum pixels when downscaling screenshots.',
    )
    parser.add_argument(
        '--image-max-pixels',
        type=int,
        default=2_000_000,
        help='Maximum pixels when downscaling (e.g., 2M ≈ 1414x1414).',
    )
    parser.add_argument(
        '--image-scale-factor',
        type=int,
        default=32,
        help='Round width/height to this multiple (Qwen recommends 32).',
    )
    parser.add_argument(
        '--image-quality',
        type=int,
        default=60,
        help='JPEG quality (1-95) for screenshots sent to the model.',
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    client = OpenAI(
        api_key=args.api_key,
        base_url=args.base_url,
        timeout=args.timeout,
    )

    tool = ComputerUseTool(
        screenshot_dir=args.screenshot_dir,
        monitor_index=args.monitor_index,
        mouse_move_duration=args.mouse_move_duration,
        drag_duration=args.drag_duration,
        image_min_pixels=args.image_min_pixels,
        image_max_pixels=args.image_max_pixels,
        image_scale_factor=args.image_scale_factor,
        image_quality=args.image_quality,
    )

    agent = ComputerUseAgent(
        client=client,
        tool=tool,
        model=args.model,
        task=args.task,
        temperature=args.temperature,
        max_turns=args.max_turns,
        history_window=args.history_window,
    )
    agent.run()

    if agent.final_answer:
        print(f'[Final Answer] {agent.final_answer}')
    if agent.terminated:
        print(f'[Task Status] {agent.terminated}')


if __name__ == '__main__':
    main()
