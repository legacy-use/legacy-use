from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

from server.database.service import DatabaseService
from server.utils.docker_manager import check_target_container_health


class GuidelineAbort(Exception):
    """Raised by guidelines to stop the agent loop."""

    def __init__(self, payload: Any):
        super().__init__('Guideline abort')
        self.payload = payload


class Guideline:
    """Base no-op guideline hooks."""

    def on_user_message(self, text: str, session) -> None:  # noqa: D401
        pass

    def before_llm_call(self, messages, session) -> None:
        pass

    def after_llm_response(self, response, session) -> None:
        pass

    def before_tool_execution(self, tool_name: str, tool_input: Any, session) -> None:
        pass

    def after_tool_execution(self, tool_name: str, tool_input: Any, result, session) -> None:
        pass

    def on_completion(self, completed: bool, session) -> Optional[Any]:
        return None


class HealthCheckGuideline(Guideline):
    """Run a VM health check before executing tools."""

    def __init__(self, db: DatabaseService, session_id: str):
        self.db = db
        self.session_id = session_id

    async def before_tool_execution(self, tool_name: str, tool_input: Any, session) -> None:  # type: ignore[override]
        if not self.session_id:
            return
        try:
            session_details = self.db.get_session(UUID(self.session_id))
            if not session_details or not session_details.get('container_ip'):
                raise GuidelineAbort(
                    {
                        'success': False,
                        'error': 'Target Health Check Failed',
                        'error_description': 'Could not retrieve container_ip for session.',
                    }
                )
            health = await check_target_container_health(session_details['container_ip'])
            if not health.get('healthy'):
                raise GuidelineAbort(
                    {
                        'success': False,
                        'error': 'Target Health Check Failed',
                        'error_description': health.get('reason', 'Unknown'),
                    }
                )
        except GuidelineAbort:
            raise
        except Exception as e:  # pragma: no cover - safety net
            raise GuidelineAbort(
                {
                    'success': False,
                    'error': 'Target Health Check Failed',
                    'error_description': str(e),
                }
            ) from e


class UIMismatchGuideline(Guideline):
    """Abort when the ui_not_as_expected tool is used."""

    def after_tool_execution(self, tool_name: str, tool_input: Any, result, session) -> None:  # type: ignore[override]
        if tool_name == 'ui_not_as_expected':
            raise GuidelineAbort(
                {
                    'success': False,
                    'error': 'UI Mismatch Detected',
                    'error_description': result.output,
                }
            )


class ExtractionGuideline(Guideline):
    """Collect extraction tool results."""

    def __init__(self) -> None:
        self.last_extraction: Optional[Any] = None

    def after_tool_execution(self, tool_name: str, tool_input: Any, result, session) -> None:  # type: ignore[override]
        if tool_name == 'extraction' and result.output:
            try:
                data = json.loads(result.output)
                if isinstance(data, dict) and 'result' in data:
                    self.last_extraction = data['result']
                else:
                    self.last_extraction = data
            except json.JSONDecodeError:
                pass

    def on_completion(self, completed: bool, session) -> Optional[Any]:  # type: ignore[override]
        if completed and self.last_extraction is not None:
            return self.last_extraction
        return None
