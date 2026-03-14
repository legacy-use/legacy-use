from server.computer_use.handlers.openai.responses_system_prompt import (
    build_openai_responses_system_prompt,
)


def test_openai_system_prompt_adds_file_flow_and_batching_guidance():
    base_prompt = """
<SYSTEM_CAPABILITY>
1. Always prioritize tool calls over text. Keep text replies short, clear, and concise.
2. First step: take a screenshot. Use only one tool per step.
</SYSTEM_CAPABILITY>
""".strip()

    prompt = build_openai_responses_system_prompt(base_prompt)

    assert 'take a screenshot if you need visual context' in prompt
    assert (
        'For file creation, renaming, opening, or editor-launch flows, take a screenshot before acting'
        in prompt
    )
    assert (
        'In desktop explorer or file-manager workflows, keep batches short.' in prompt
    )
