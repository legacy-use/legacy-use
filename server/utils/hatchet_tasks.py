"""
Simple Hatchet tasks for testing.
"""

from hatchet_sdk import Context
from pydantic import BaseModel

from server.utils.hatchet_client import get_hatchet_client

# Get the shared Hatchet client instance
hatchet = get_hatchet_client()


class SimpleInput(BaseModel):
    message: str


@hatchet.task(name='SimpleTask', input_validator=SimpleInput)
def simple(input: SimpleInput, ctx: Context) -> dict[str, str]:
    """A simple task that transforms a message to lowercase."""
    return {
        'transformed_message': input.message.lower(),
    }
