import asyncio
import base64
import os
import shlex
import shutil
from enum import StrEnum
from pathlib import Path
from typing import Literal, TypedDict, get_args
from uuid import uuid4

from pydantic import BaseModel

OUTPUT_DIR = '/tmp/outputs'

TYPING_DELAY_MS = 12
TYPING_GROUP_SIZE = 50


class ToolResult(BaseModel):
    """Represents the result of a tool execution."""

    output: str | None = None
    error: str | None = None
    base64_image: str | None = None
    system: str | None = None


class ToolError(Exception):
    """Raised when a tool encounters an error."""

    def __init__(self, message):
        self.message = message


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
        'probe:windows_state',
    ]
)

ScrollDirection = Literal['up', 'down', 'left', 'right']


class Resolution(TypedDict):
    width: int
    height: int


# sizes above XGA/WXGA are not recommended (see README.md)
# scale down to one of these targets if ComputerTool._scaling_enabled is set
MAX_SCALING_TARGETS: dict[str, Resolution] = {
    'XGA': Resolution(width=1024, height=768),  # 4:3
    'WXGA': Resolution(width=1280, height=800),  # 16:10
    'FWXGA': Resolution(width=1366, height=768),  # ~16:9
}

CLICK_BUTTONS = {
    'left_click': 1,
    'right_click': 3,
    'middle_click': 2,
    'double_click': '--repeat 2 --delay 10 1',
    'triple_click': '--repeat 3 --delay 10 1',
}


class ScalingSource(StrEnum):
    COMPUTER = 'computer'
    API = 'api'


class ComputerToolOptions(TypedDict):
    display_height_px: int
    display_width_px: int
    display_number: int | None


def chunks(s: str, chunk_size: int) -> list[str]:
    return [s[i : i + chunk_size] for i in range(0, len(s), chunk_size)]


TRUNCATED_MESSAGE: str = '<response clipped><NOTE>To save on context only part of this file has been shown to you. You should retry this tool after you have searched inside the file with `grep -n` in order to find the line numbers of what you are looking for.</NOTE>'
MAX_RESPONSE_LEN: int = 16000


def maybe_truncate(content: str, truncate_after: int | None = MAX_RESPONSE_LEN):
    """Truncate content and append a notice if content exceeds the specified length."""
    return (
        content
        if not truncate_after or len(content) <= truncate_after
        else content[:truncate_after] + TRUNCATED_MESSAGE
    )


async def run(
    cmd: str,
    timeout: float | None = 120.0,  # seconds
    truncate_after: int | None = MAX_RESPONSE_LEN,
):
    """Run a shell command asynchronously with a timeout."""
    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        return (
            process.returncode or 0,
            maybe_truncate(stdout.decode(), truncate_after=truncate_after),
            maybe_truncate(stderr.decode(), truncate_after=truncate_after),
        )
    except asyncio.TimeoutError as exc:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        raise TimeoutError(
            f"Command '{cmd}' timed out after {timeout} seconds"
        ) from exc


class BaseComputerTool:
    """
    A tool that allows the agent to interact with the screen, keyboard, and mouse of the current computer.
    The tool parameters are defined by Anthropic and are not editable.
    """

    name: Literal['computer'] = 'computer'
    width: int
    height: int
    display_num: int | None

    _screenshot_delay = 2.0
    _scaling_enabled = True

    @property
    def options(self) -> ComputerToolOptions:
        width, height = self.scale_coordinates(
            ScalingSource.COMPUTER, self.width, self.height
        )
        return {
            'display_width_px': width,
            'display_height_px': height,
            'display_number': self.display_num,
        }

    def __init__(self):
        super().__init__()

        self.width = int(os.getenv('WIDTH') or 0)
        self.height = int(os.getenv('HEIGHT') or 0)
        assert self.width and self.height, 'WIDTH, HEIGHT must be set'
        if (display_num := os.getenv('DISPLAY_NUM')) is not None:
            self.display_num = int(display_num)
            self._display_prefix = f'DISPLAY=:{self.display_num} '
        else:
            self.display_num = None
            self._display_prefix = ''

        self.xdotool = f'{self._display_prefix}xdotool'

    async def __call__(
        self,
        *,
        action: Action_20241022,
        text: str | None = None,
        coordinate: tuple[int, int] | None = None,
        **kwargs,
    ):
        if action in ('mouse_move', 'left_click_drag'):
            if coordinate is None:
                raise ToolError(f'coordinate is required for {action}')
            if text is not None:
                raise ToolError(f'text is not accepted for {action}')

            x, y = self.validate_and_get_coordinates(coordinate)

            if action == 'mouse_move':
                command_parts = [self.xdotool, f'mousemove --sync {x} {y}']
                return await self.shell(' '.join(command_parts))
            elif action == 'left_click_drag':
                command = (
                    f'{self.xdotool} '
                    'mousedown --clearmodifiers 1 '  # start drag, dropping any additional modifiers
                    'sleep 0.12 '
                    'mousemove_relative --sync 18 0 '  # threshold to trigger DnD
                    'sleep 0.05 '
                    f'mousemove --sync {x} {y} '
                    'sleep 0.10 '  # brief hover so the target window sees XdndPosition
                    'mouseup 1'
                )
                return await self.shell(command)

        if action in ('key', 'type'):
            if text is None:
                raise ToolError(f'text is required for {action}')
            if coordinate is not None:
                raise ToolError(f'coordinate is not accepted for {action}')
            if not isinstance(text, str):
                # TODO: Dead -> Delete?
                raise ToolError(output=f'{text} must be a string')

            if action == 'key':
                command_parts = [self.xdotool, f'key -- {text}']
                return await self.shell(' '.join(command_parts))
            elif action == 'type':
                results: list[ToolResult] = []
                for chunk in chunks(text, TYPING_GROUP_SIZE):
                    command_parts = [
                        self.xdotool,
                        f'type --delay {TYPING_DELAY_MS} -- {shlex.quote(chunk)}',
                    ]
                    results.append(
                        await self.shell(' '.join(command_parts), take_screenshot=False)
                    )
                # delay to let things settle before taking a screenshot
                await asyncio.sleep(self._screenshot_delay)
                screenshot_base64 = (await self.screenshot()).base64_image
                return ToolResult(
                    output=''.join(result.output or '' for result in results),
                    error=''.join(result.error or '' for result in results),
                    base64_image=screenshot_base64,
                )

        if action in (
            'left_click',
            'right_click',
            'double_click',
            'middle_click',
            'screenshot',
            'cursor_position',
        ):
            if text is not None:
                raise ToolError(f'text is not accepted for {action}')
            if coordinate is not None:
                raise ToolError(f'coordinate is not accepted for {action}')

            if action == 'screenshot':
                return await self.screenshot()
            elif action == 'cursor_position':
                command_parts = [self.xdotool, 'getmouselocation --shell']
                result = await self.shell(
                    ' '.join(command_parts),
                    take_screenshot=False,
                )
                output = result.output or ''
                x, y = self.scale_coordinates(
                    ScalingSource.COMPUTER,
                    int(output.split('X=')[1].split('\n')[0]),
                    int(output.split('Y=')[1].split('\n')[0]),
                )

                return ToolResult(
                    output=f'X={x},Y={y}',
                    error=result.error,
                    base64_image=result.base64_image,
                    system=result.system,
                )
            else:
                command_parts = [self.xdotool, f'click {CLICK_BUTTONS[action]}']
                return await self.shell(' '.join(command_parts))

        raise ToolError(f'Invalid action: {action}')

    def validate_and_get_coordinates(self, coordinate: tuple[int, int] | None = None):
        if not isinstance(coordinate, tuple) or len(coordinate) != 2:
            raise ToolError(f'{coordinate} must be a tuple of length 2')
        if not all(isinstance(i, int) and i >= 0 for i in coordinate):
            raise ToolError(f'{coordinate} must be a tuple of non-negative ints')

        return self.scale_coordinates(ScalingSource.API, coordinate[0], coordinate[1])

    async def screenshot(self):
        """Take a screenshot of the current screen and return the base64 encoded image."""
        output_dir = Path(OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f'screenshot_{uuid4().hex}.png'

        # Try gnome-screenshot first
        if shutil.which('gnome-screenshot'):
            screenshot_cmd = f'{self._display_prefix}gnome-screenshot -f {path} -p'
        else:
            # Fall back to scrot if gnome-screenshot isn't available
            screenshot_cmd = f'{self._display_prefix}scrot -p {path}'

        result = await self.shell(screenshot_cmd, take_screenshot=False)
        if self._scaling_enabled:
            x, y = self.scale_coordinates(
                ScalingSource.COMPUTER, self.width, self.height
            )
            await self.shell(
                f'convert {path} -resize {x}x{y}! {path}', take_screenshot=False
            )

        if path.exists():
            return ToolResult(
                output=result.output,
                error=result.error,
                base64_image=base64.b64encode(path.read_bytes()).decode(),
                system=result.system,
            )
        raise ToolError(f'Failed to take screenshot: {result.error}')

    async def shell(self, command: str, take_screenshot=True) -> ToolResult:
        """Run a shell command and return the output, error, and optionally a screenshot."""
        _, stdout, stderr = await run(command)
        base64_image = None

        if take_screenshot:
            # delay to let things settle before taking a screenshot
            await asyncio.sleep(self._screenshot_delay)
            base64_image = (await self.screenshot()).base64_image

        return ToolResult(output=stdout, error=stderr, base64_image=base64_image)

    def scale_coordinates(self, source: ScalingSource, x: int, y: int):
        """Scale coordinates to a target maximum resolution."""
        if not self._scaling_enabled:
            return x, y
        ratio = self.width / self.height
        target_dimension = None
        for dimension in MAX_SCALING_TARGETS.values():
            # allow some error in the aspect ratio - not ratios are exactly 16:9
            if abs(dimension['width'] / dimension['height'] - ratio) < 0.02:
                if dimension['width'] < self.width:
                    target_dimension = dimension
                break
        if target_dimension is None:
            return x, y
        # should be less than 1
        x_scaling_factor = target_dimension['width'] / self.width
        y_scaling_factor = target_dimension['height'] / self.height
        if source == ScalingSource.API:
            if x > self.width or y > self.height:
                raise ToolError(f'Coordinates {x}, {y} are out of bounds')
            # scale up
            return round(x / x_scaling_factor), round(y / y_scaling_factor)
        # scale down
        return round(x * x_scaling_factor), round(y * y_scaling_factor)


class ComputerTool20241022(BaseComputerTool):
    api_type: Literal['computer_20241022'] = 'computer_20241022'


class ComputerTool20250124(BaseComputerTool):
    api_type: Literal['computer_20250124'] = 'computer_20250124'

    async def __call__(
        self,
        *,
        action: Action_20250124,
        text: str | None = None,
        coordinate: tuple[int, int] | None = None,
        scroll_direction: ScrollDirection | None = None,
        scroll_amount: int | None = None,
        duration: int | float | None = None,
        key: str | None = None,
        **kwargs,
    ):
        if action in ('left_mouse_down', 'left_mouse_up'):
            if coordinate is not None:
                raise ToolError(f'coordinate is not accepted for {action=}.')
            command_parts = [
                self.xdotool,
                f'{"mousedown" if action == "left_mouse_down" else "mouseup"} 1',
            ]
            return await self.shell(' '.join(command_parts))
        if action == 'scroll':
            if scroll_direction is None or scroll_direction not in get_args(
                ScrollDirection
            ):
                raise ToolError(
                    f"{scroll_direction=} must be 'up', 'down', 'left', or 'right'"
                )
            if not isinstance(scroll_amount, int) or scroll_amount < 0:
                raise ToolError(f'{scroll_amount=} must be a non-negative int')
            mouse_move_part = ''
            if coordinate is not None:
                x, y = self.validate_and_get_coordinates(coordinate)
                mouse_move_part = f'mousemove --sync {x} {y}'
            scroll_button = {
                'up': 4,
                'down': 5,
                'left': 6,
                'right': 7,
            }[scroll_direction]

            command_parts = [self.xdotool, mouse_move_part]
            if text:
                command_parts.append(f'keydown {text}')
            command_parts.append(f'click --repeat {scroll_amount} {scroll_button}')
            if text:
                command_parts.append(f'keyup {text}')

            return await self.shell(' '.join(command_parts))

        if action in ('hold_key', 'wait'):
            if duration is None or not isinstance(duration, (int, float)):
                raise ToolError(f'{duration=} must be a number')
            if duration < 0:
                raise ToolError(f'{duration=} must be non-negative')
            if duration > 100:
                raise ToolError(f'{duration=} is too long.')

            if action == 'hold_key':
                if text is None:
                    raise ToolError(f'text is required for {action}')
                escaped_keys = shlex.quote(text)
                command_parts = [
                    self.xdotool,
                    f'keydown {escaped_keys}',
                    f'sleep {duration}',
                    f'keyup {escaped_keys}',
                ]
                return await self.shell(' '.join(command_parts))

            if action == 'wait':
                await asyncio.sleep(duration)
                return await self.screenshot()

        if action in (
            'left_click',
            'right_click',
            'double_click',
            'triple_click',
            'middle_click',
        ):
            if text is not None:
                raise ToolError(f'text is not accepted for {action}')
            mouse_move_part = ''
            if coordinate is not None:
                x, y = self.validate_and_get_coordinates(coordinate)
                mouse_move_part = f'mousemove --sync {x} {y}'

            command_parts = [self.xdotool, mouse_move_part]
            if key:
                command_parts.append(f'keydown {key}')
            command_parts.append(f'click {CLICK_BUTTONS[action]}')
            if key:
                command_parts.append(f'keyup {key}')

            return await self.shell(' '.join(command_parts))

        if action == 'probe:windows_state':
            return await self._probe_windows_state()

        return await super().__call__(
            action=action, text=text, coordinate=coordinate, key=key, **kwargs
        )

    async def _probe_windows_state(self) -> ToolResult:
        """Collect a structured snapshot of open windows and their state.

        If connected via RDP, triggers a remote PowerShell probe that writes a JSON
        file to the redirected drive (\\tsclient\\agent\\windows_state.json) and
        returns its contents. Otherwise, uses local X11 enumeration as a fallback.
        """
        import json

        remote_client_type = (os.getenv('REMOTE_CLIENT_TYPE') or '').lower()
        if remote_client_type == 'rdp':
            share_dir = Path('/tmp/rdp_agent_share')
            share_dir.mkdir(parents=True, exist_ok=True)

            ps_script_path = share_dir / 'windows_state.ps1'

            ps_code = (
                '$cs = @"\n'
                'using System;\nusing System.Text;\nusing System.Runtime.InteropServices;\n'
                'public static class U {\n'
                '  public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);\n'
                '  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lp);\n'
                '  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);\n'
                '  [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr h);\n'
                '  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int m);\n'
                '  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);\n'
                '  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();\n'
                '  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);\n'
                '  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }\n'
                '}\n"@; Add-Type $cs\n'
                '$active = [U]::GetForegroundWindow()\n'
                '$list = New-Object System.Collections.Generic.List[Object]\n'
                '[U]::EnumWindows({ param($h,$l)\n'
                '  if (-not [U]::IsWindowVisible($h)) { return $true }\n'
                '  $len = [U]::GetWindowTextLength($h); if ($len -le 0) { return $true }\n'
                '  $sb = New-Object System.Text.StringBuilder ($len+1); [void][U]::GetWindowText($h,$sb,$sb.Capacity)\n'
                '  $r = New-Object U+RECT; [void][U]::GetWindowRect($h,[ref]$r)\n'
                '  [uint32]$pid=0; [void][U]::GetWindowThreadProcessId($h,[ref]$pid)\n'
                '  try { $p = Get-Process -Id $pid -ErrorAction Stop } catch { $p = $null }\n'
                '  $list.Add([pscustomobject]@{\n'
                '    id     = ("0x{0:X}" -f $h.ToInt64())\n'
                '    title  = $sb.ToString()\n'
                '    app    = @{ pid=$pid; name=$p?.ProcessName; exe=$p?.Path }\n'
                '    bounds = @{ x=$r.Left; y=$r.Top; width=($r.Right-$r.Left); height=($r.Bottom-$r.Top) }\n'
                '    state  = @{ focused=($h -eq $active); visible=$true }\n'
                '  }); $true\n'
                '}, [IntPtr]::Zero) | Out-Null\n'
                '\n'
                '[pscustomobject]@{\n'
                "  probe='windows_state'\n"
                '  captured_at=[int][DateTimeOffset]::Now.ToUnixTimeSeconds()\n'
                '  active_window_id=("0x{0:X}" -f $active.ToInt64())\n'
                '  windows=$list\n'
                '} | ConvertTo-Json -Depth 6 -Compress |\n'
                '  Set-Content \\\\tsclient\\agent\\windows_state.json -Encoding utf8\n'
            )

            try:
                existing = (
                    ps_script_path.read_text(encoding='utf-8')
                    if ps_script_path.exists()
                    else None
                )
            except Exception:
                existing = None
            if existing != ps_code:
                ps_script_path.write_text(ps_code, encoding='utf-8')

            powershell_cmd = r'powershell -NoProfile -ExecutionPolicy Bypass -File \\tsclient\agent\windows_state.ps1'

            command_parts = [
                self.xdotool,
                'key ctrl+esc',
                'sleep 0.20',
                f'type --delay {TYPING_DELAY_MS} -- {shlex.quote(powershell_cmd)}',
                'sleep 0.05',
                'key Return',
            ]
            await self.shell(' '.join(command_parts), take_screenshot=False)

            json_path = share_dir / 'windows_state.json'
            for _ in range(30):
                if json_path.exists():
                    try:
                        content = json_path.read_text(encoding='utf-8')
                        # ensure valid JSON
                        _ = json.loads(content)
                        screenshot_b64 = (await self.screenshot()).base64_image
                        return ToolResult(
                            output=content, error=None, base64_image=screenshot_b64
                        )
                    except Exception:
                        pass
                await asyncio.sleep(0.1)

            raise ToolError('windows_state.json not produced by remote within timeout')

        async def get_active_window_id_decimal() -> int | None:
            try:
                code, out, _ = await run(f'{self.xdotool} getactivewindow', timeout=5.0)
                if code == 0 and out.strip().isdigit():
                    return int(out.strip())
            except Exception:
                pass
            return None

        async def get_current_desktop() -> int | None:
            try:
                code, out, _ = await run(
                    f'{self._display_prefix}wmctrl -d', timeout=5.0
                )
                if code == 0:
                    # line with '*' denotes current desktop; parse first int id
                    for line in out.splitlines():
                        if '*' in line:
                            parts = line.split()
                            if parts and parts[0].isdigit():
                                return int(parts[0])
            except Exception:
                return None
            return None

        async def read_proc_comm(pid: int) -> str | None:
            try:
                with open(
                    f'/proc/{pid}/comm', 'r', encoding='utf-8', errors='ignore'
                ) as f:
                    return f.read().strip() or None
            except Exception:
                return None

        active_dec = await get_active_window_id_decimal()
        current_desktop = await get_current_desktop()

        windows: list[dict] = []

        if shutil.which('wmctrl'):
            code, out, err = await run(
                f'{self._display_prefix}wmctrl -lpGx', timeout=8.0, truncate_after=None
            )
            if code == 0 and out:
                for line in out.splitlines():
                    try:
                        parts = line.split()
                        if len(parts) < 9:
                            continue
                        win_hex = parts[0]
                        desktop = (
                            int(parts[1]) if parts[1].lstrip('-').isdigit() else None
                        )
                        pid = int(parts[2]) if parts[2].isdigit() else None
                        x = int(parts[3])
                        y = int(parts[4])
                        w = int(parts[5])
                        h = int(parts[6])
                        app_class = parts[7]
                        host = parts[8]
                        title = ' '.join(parts[9:]) if len(parts) > 9 else ''

                        # convert hex id to decimal for comparison
                        win_dec = int(win_hex, 16)
                        focused = active_dec is not None and win_dec == active_dec

                        # query xprop for state flags and workspace if needed
                        minimized = False
                        maximized = False
                        fullscreen = False
                        sticky = False
                        workspace = desktop
                        try:
                            _c, xprop_out, _e = await run(
                                f'{self._display_prefix}xprop -id {win_hex} _NET_WM_STATE _NET_WM_DESKTOP',
                                timeout=5.0,
                                truncate_after=None,
                            )
                            for line in (xprop_out or '').splitlines():
                                if line.startswith('_NET_WM_DESKTOP'):
                                    try:
                                        workspace = int(line.split()[-1])
                                    except Exception:
                                        pass
                                if line.startswith('_NET_WM_STATE'):
                                    vals = line.split('=')[-1]
                                    minimized = '_NET_WM_STATE_HIDDEN' in vals
                                    maximized = (
                                        '_NET_WM_STATE_MAXIMIZED_VERT' in vals
                                        or '_NET_WM_STATE_MAXIMIZED_HORZ' in vals
                                    )
                                    fullscreen = '_NET_WM_STATE_FULLSCREEN' in vals
                                    sticky = '_NET_WM_STATE_STICKY' in vals
                        except Exception:
                            pass

                        process_name = await read_proc_comm(pid) if pid else None

                        windows.append(
                            {
                                'id': {
                                    'hex': win_hex,
                                    'dec': win_dec,
                                },
                                'pid': pid,
                                'process_name': process_name,
                                'app_class': app_class,
                                'host': host,
                                'title': title,
                                'bounds': {'x': x, 'y': y, 'width': w, 'height': h},
                                'workspace': workspace,
                                'state': {
                                    'focused': focused,
                                    'visible': not minimized,
                                    'minimized': minimized,
                                    'maximized': maximized,
                                    'fullscreen': fullscreen,
                                    'sticky': sticky,
                                },
                            }
                        )
                    except Exception:
                        continue
        else:
            # Fallback: use xdotool to enumerate windows
            code, out, _ = await run(
                f"{self.xdotool} search --onlyvisible --name ''", timeout=8.0
            )
            if code == 0 and out:
                for line in out.splitlines():
                    if not line.strip().isdigit():
                        continue
                    win_dec = int(line.strip())
                    win_hex = hex(win_dec)
                    title = ''
                    pid = None
                    app_class = None
                    workspace = None
                    minimized = False
                    maximized = False
                    fullscreen = False
                    sticky = False
                    x = y = w = h = 0
                    try:
                        _c, xprop_out, _e = await run(
                            f'{self._display_prefix}xprop -id {win_dec}',
                            timeout=5.0,
                            truncate_after=None,
                        )
                        for line in (xprop_out or '').splitlines():
                            if line.startswith('WM_NAME(') or line.startswith(
                                '_NET_WM_NAME'
                            ):
                                try:
                                    title = line.split('=')[-1].strip().strip(' "')
                                except Exception:
                                    pass
                            if line.startswith('WM_CLASS('):
                                try:
                                    app_class = line.split('=')[-1].strip().strip(' "')
                                except Exception:
                                    pass
                            if line.startswith('_NET_WM_PID'):
                                try:
                                    pid = int(line.split()[-1])
                                except Exception:
                                    pass
                            if line.startswith('_NET_WM_DESKTOP'):
                                try:
                                    workspace = int(line.split()[-1])
                                except Exception:
                                    pass
                            if line.startswith('_NET_WM_STATE'):
                                vals = line.split('=')[-1]
                                minimized = '_NET_WM_STATE_HIDDEN' in vals
                                maximized = (
                                    '_NET_WM_STATE_MAXIMIZED_VERT' in vals
                                    or '_NET_WM_STATE_MAXIMIZED_HORZ' in vals
                                )
                                fullscreen = '_NET_WM_STATE_FULLSCREEN' in vals
                                sticky = '_NET_WM_STATE_STICKY' in vals
                    except Exception:
                        pass
                    try:
                        _c, geo_out, _e = await run(
                            f'{self.xdotool} getwindowgeometry --shell {win_dec}',
                            timeout=5.0,
                        )
                        geo_map: dict[str, str] = {}
                        for part in (geo_out or '').split():
                            if '=' in part:
                                k, v = part.split('=', 1)
                                geo_map[k] = v
                        x = int(geo_map.get('X', '0'))
                        y = int(geo_map.get('Y', '0'))
                        w = int(geo_map.get('WIDTH', '0'))
                        h = int(geo_map.get('HEIGHT', '0'))
                    except Exception:
                        pass

                    process_name = await read_proc_comm(pid) if pid else None

                    windows.append(
                        {
                            'id': {
                                'hex': win_hex,
                                'dec': win_dec,
                            },
                            'pid': pid,
                            'process_name': process_name,
                            'app_class': app_class,
                            'host': None,
                            'title': title,
                            'bounds': {'x': x, 'y': y, 'width': w, 'height': h},
                            'workspace': workspace,
                            'state': {
                                'focused': active_dec is not None
                                and win_dec == active_dec,
                                'visible': not minimized,
                                'minimized': minimized,
                                'maximized': maximized,
                                'fullscreen': fullscreen,
                                'sticky': sticky,
                            },
                        }
                    )

        result_obj = {
            'active_window': {
                'dec': active_dec,
                'hex': hex(active_dec) if isinstance(active_dec, int) else None,
            },
            'current_desktop': current_desktop,
            'windows': windows,
        }
        return ToolResult(output=json.dumps(result_obj), error=None, base64_image=None)
