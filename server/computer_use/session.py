from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List
from uuid import UUID

from anthropic.types.beta import BetaMessageParam

from server.computer_use.utils import (
    _beta_message_param_to_job_message_content,
    _job_message_to_beta_message_param,
)
from server.database.service import DatabaseService


@dataclass
class Event:
    role: str
    content: Any
    event_type: str
    ts: datetime


class Session:
    """Lightweight wrapper around job message storage."""

    def __init__(self, tenant_id: str, job_id: UUID, db: DatabaseService):
        self.tenant_id = tenant_id
        self.job_id = job_id
        self.db = db

    # -- persistence -------------------------------------------------
    def add_event(self, event: Event) -> None:
        """Persist an event to the database."""
        beta_param: BetaMessageParam = {
            'role': event.role,
            'content': event.content,
        }
        serialized = _beta_message_param_to_job_message_content(beta_param)
        seq = self.db.get_next_message_sequence(self.job_id)
        self.db.add_job_message(self.job_id, seq, event.role, serialized)

    # -- retrieval ---------------------------------------------------
    def get_history(self) -> List[Event]:
        events: List[Event] = []
        for msg in self.db.get_job_messages(self.job_id):
            events.append(
                Event(
                    role=msg['role'],
                    content=msg['message_content'],
                    event_type='message',
                    ts=msg.get('created_at', datetime.utcnow()),
                )
            )
        return events

    def get_history_for_api(self) -> List[BetaMessageParam]:
        db_messages = self.db.get_job_messages(self.job_id)
        return [_job_message_to_beta_message_param(m) for m in db_messages]
