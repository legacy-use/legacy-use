from dataclasses import dataclass
from typing import Literal

from server.computer_use.tools.custom_action import CustomActionTool

from .base import BaseAnthropicTool
from .computer import ComputerTool20241022, ComputerTool20250124
from .extraction import ExtractionTool
from .ui_not_as_expected import UINotAsExpectedTool

ToolVersion = Literal['computer_use_20250124', 'computer_use_20241022']
BetaFlag = Literal['computer-use-2024-10-22', 'computer-use-2025-01-24']


@dataclass(frozen=True, kw_only=True)
class ToolGroup:
    version: ToolVersion
    tools: list[type[BaseAnthropicTool | CustomActionTool]]
    beta_flag: BetaFlag | None = None


TOOL_GROUPS: list[ToolGroup] = [
    ToolGroup(
        version='computer_use_20241022',
        tools=[
            ComputerTool20241022,
            ExtractionTool,
            UINotAsExpectedTool,
            CustomActionTool,
        ],
        beta_flag='computer-use-2024-10-22',
    ),
    ToolGroup(
        version='computer_use_20250124',
        tools=[
            ComputerTool20250124,
            ExtractionTool,
            UINotAsExpectedTool,
            CustomActionTool,
        ],
        beta_flag='computer-use-2025-01-24',
    ),
]

TOOL_GROUPS_BY_VERSION = {tool_group.version: tool_group for tool_group in TOOL_GROUPS}
