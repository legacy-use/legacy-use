"""Simplified sampling loop routed through the Agent abstraction."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional, cast
from uuid import UUID

from anthropic.types.beta import BetaContentBlockParam, BetaMessageParam

from server.computer_use.agent import Agent
from server.computer_use.guidelines import (
    ExtractionGuideline,
    HealthCheckGuideline,
    UIMismatchGuideline,
)
from server.computer_use.session import Event, Session
from server.computer_use.tools import TOOL_GROUPS_BY_VERSION, ToolCollection, ToolResult, ToolVersion
from server.computer_use.tools.custom_action import CustomActionTool
from server.computer_use.handlers.registry import get_handler
from server.computer_use.utils import _load_system_prompt
from server.database.service import DatabaseService

ApiResponseCallback = Callable[[Any, Any, Optional[Exception]], None]


async def sampling_loop(
    *,
    job_id: UUID,
    db_tenant: DatabaseService,
    model: str,
    provider,
    system_prompt_suffix: str,
    messages: list[BetaMessageParam],
    output_callback: Callable[[BetaContentBlockParam], None],
    tool_output_callback: Callable[[ToolResult, str], None],
    api_response_callback: Optional[ApiResponseCallback] = None,
    max_tokens: int = 4096,
    tool_version: ToolVersion,
    token_efficient_tools_beta: bool = False,
    api_key: str = '',
    only_n_most_recent_images: Optional[int] = None,
    session_id: str = '',
    tenant_schema: str = '',
    job_data: dict[str, Any] | None = None,
) -> tuple[Any, list[dict[str, Any]]]:
    """Run the agentic loop and return the final result and exchanges."""

    job_data = job_data or {}

    # Build tools and handler as before
    tool_group = TOOL_GROUPS_BY_VERSION[tool_version]
    tools = []
    for ToolCls in tool_group.tools:
        if ToolCls == CustomActionTool:
            custom_actions = db_tenant.get_custom_actions(
                job_data.get('api_definition_version_id')
            )
            tools.append(ToolCls(custom_actions, job_data.get('parameters')))
        else:
            tools.append(ToolCls())
    tool_collection = ToolCollection(*tools)

    handler = get_handler(
        provider=provider,
        model=model,
        tool_beta_flag=tool_group.beta_flag,
        token_efficient_tools_beta=token_efficient_tools_beta,
        only_n_most_recent_images=only_n_most_recent_images,
        tenant_schema=tenant_schema,
    )

    system_prompt = _load_system_prompt(system_prompt_suffix)

    # Initialize session and seed initial messages
    session = Session(tenant_schema, job_id, db_tenant)
    for init_message in messages:
        session.add_event(
            Event(
                role=cast(str, init_message.get('role', 'user')),
                content=init_message.get('content'),
                event_type='message',
                ts=datetime.utcnow(),
            )
        )

    guidelines = [
        HealthCheckGuideline(db_tenant, session_id),
        UIMismatchGuideline(),
        ExtractionGuideline(),
    ]

    agent = Agent(
        session=session,
        tools=tool_collection,
        handler=handler,
        system_prompt=system_prompt,
        model=model,
        api_key=api_key,
        max_tokens=max_tokens,
        output_callback=output_callback,
        tool_output_callback=tool_output_callback,
        api_response_callback=api_response_callback,
        guidelines=guidelines,
    )

    return await agent.run()
