from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, List, Optional, Tuple, cast

from anthropic.types.beta import BetaContentBlockParam, BetaMessageParam

from server.computer_use.session import Event, Session
from server.computer_use.utils import _make_api_tool_result
from server.computer_use.tools import ToolCollection, ToolResult
from server.computer_use.guidelines import Guideline, GuidelineAbort


class Agent:
    """Agent orchestrating the sampling loop via Session and Guidelines."""

    def __init__(
        self,
        session: Session,
        tools: ToolCollection,
        handler,
        system_prompt: str,
        *,
        model: str,
        api_key: str = '',
        max_tokens: int = 4096,
        output_callback: Optional[Callable[[BetaContentBlockParam], None]] = None,
        tool_output_callback: Optional[Callable[[ToolResult, str], None]] = None,
        api_response_callback: Optional[Callable[[Any, Any, Any], None]] = None,
        guidelines: Optional[List[Guideline]] = None,
    ) -> None:
        self.session = session
        self.tools = tools
        self.handler = handler
        self.system_prompt = system_prompt
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.output_callback = output_callback
        self.tool_output_callback = tool_output_callback
        self.api_response_callback = api_response_callback
        self.guidelines = guidelines or []

    async def handle_user_message(self, text: str) -> Tuple[Any, List[dict[str, Any]]]:
        self.session.add_event(Event('user', text, 'message', datetime.utcnow()))
        return await self._loop()

    async def run(self) -> Tuple[Any, List[dict[str, Any]]]:
        return await self._loop()

    async def _loop(self) -> Tuple[Any, List[dict[str, Any]]]:
        exchanges: List[dict[str, Any]] = []
        while True:
            messages = self.session.get_history_for_api()
            for g in self.guidelines:
                g.before_llm_call(messages, self.session)
            client = await self.handler.initialize_client(api_key=self.api_key)
            response_params, stop_reason, request, raw_response = await self.handler.execute(
                client=client,
                messages=messages,
                system=self.system_prompt,
                tools=self.tools,
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=0.0,
            )
            if self.api_response_callback:
                self.api_response_callback(request, raw_response, None)
            exchanges.append({'request': request, 'response': raw_response})
            self.session.add_event(
                Event('assistant', response_params, 'message', datetime.utcnow())
            )
            for g in self.guidelines:
                g.after_llm_response(response_params, self.session)
            for block in response_params:
                if self.output_callback:
                    self.output_callback(block)
            tool_uses = [
                b for b in response_params if isinstance(b, dict) and b.get('type') == 'tool_use'
            ]
            if not tool_uses:
                completed = stop_reason == 'end_turn'
                for g in self.guidelines:
                    result = g.on_completion(completed, self.session)
                    if result is not None:
                        return result, exchanges
                if completed:
                    return self._final_answer(), exchanges
                continue
            for tool_use in tool_uses:
                name = cast(str, tool_use.get('name'))
                tool_input = cast(dict[str, Any], tool_use.get('input') or {})
                tool_id = cast(str, tool_use.get('id') or tool_use.get('tool_use_id'))
                try:
                    for g in self.guidelines:
                        before = getattr(g, 'before_tool_execution')
                        if callable(before):
                            res = before(name, tool_input, self.session)
                            if hasattr(res, '__await__'):
                                await res  # type: ignore[func-returns-value]
                except GuidelineAbort as e:
                    return e.payload, exchanges
                result = await self.tools.run(name=name, tool_input=tool_input)
                if self.tool_output_callback:
                    self.tool_output_callback(result, tool_id)
                try:
                    for g in self.guidelines:
                        after = getattr(g, 'after_tool_execution')
                        if callable(after):
                            res = after(name, tool_input, result, self.session)
                            if hasattr(res, '__await__'):
                                await res  # type: ignore[func-returns-value]
                except GuidelineAbort as e:
                    return e.payload, exchanges
                api_result = _make_api_tool_result(result, tool_id)
                self.session.add_event(
                    Event('assistant', [api_result], 'tool_result', datetime.utcnow())
                )
        # unreachable

    def _final_answer(self) -> str:
        history = self.session.get_history_for_api()
        if not history:
            return ''
        last = history[-1]
        content = last.get('content', [])
        texts = [b.get('text', '') for b in content if b.get('type') == 'text']
        return '\n'.join(texts)
