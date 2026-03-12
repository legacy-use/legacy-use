from server.computer_use.handlers.kimi.response_converter import (
    convert_kimi_to_anthropic_response,
)


def test_compliant_response_yields_text_and_tool_use():
    response = {
        'choices': [
            {
                'message': {
                    'content': '## Thought:\nInspect the button\n## Action:\nClick the button\n## Code:\n```python\npyautogui.click(x=10, y=20)\n```'
                }
            }
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(response)

    assert stop_reason == 'tool_use'
    assert blocks[0]['type'] == 'text'
    assert '## Thought:' in blocks[0]['text']
    assert blocks[1]['type'] == 'tool_use'
    assert blocks[1]['name'] == 'computer'
    assert blocks[1]['input']['action'] == 'left_click'


def test_terminate_response_is_end_turn():
    response = {
        'choices': [
            {
                'message': {
                    'content': '## Thought:\nDone\n## Action:\nReturn result\n## Code:\n```python\ncomputer.terminate(status="success", data="{\\"done\\": true}")\n```'
                }
            }
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(response)

    assert stop_reason == 'end_turn'
    assert blocks[1]['type'] == 'tool_use'
    assert blocks[1]['name'] == 'extraction'


def test_terminate_response_uses_thought_action_nearest_to_code():
    response = {
        'choices': [
            {
                'message': {
                    'content': '## Thought:\nOld thought\n## Action:\nOld action\n## Thought:\nFinal thought\n## Action:\nFinal action\n## Code:\n```python\ncomputer.terminate(status="success", data="{\\"done\\": true}")\n```'
                }
            }
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(response)

    assert stop_reason == 'end_turn'
    assert blocks[0]['text'] == '## Thought:\nFinal thought\n## Action:\nFinal action'
    assert blocks[1]['name'] == 'extraction'


def test_inline_code_headers_and_keydown_pair_are_normalized():
    response = {
        'choices': [
            {
                'message': {
                    'content': '## Thought:\nNeed to reopen start\n## Action:\nPress the Windows key. </think> ## Code:\n```python\npyautogui.keyDown("win")\npyautogui.keyUp("win")\n```'
                }
            }
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(response)

    assert stop_reason == 'tool_use'
    assert blocks[0]['type'] == 'text'
    assert blocks[1]['type'] == 'tool_use'
    assert blocks[1]['input']['action'] == 'key'
    assert blocks[1]['input']['text'] == 'Super_L'


def test_keydown_modifier_sequence_collapses_to_hotkey():
    response = {
        'choices': [
            {
                'message': {
                    'content': '## Thought:\nOpen security screen\n## Action:\nPress Ctrl+Alt+Delete\n## Code:\n```python\npyautogui.keyDown("ctrl")\npyautogui.keyDown("alt")\npyautogui.keyDown("delete")\npyautogui.keyUp("delete")\npyautogui.keyUp("alt")\npyautogui.keyUp("ctrl")\n```'
                }
            }
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(response)

    assert stop_reason == 'tool_use'
    assert blocks[1]['input']['action'] == 'key'
    assert blocks[1]['input']['text'] == 'ctrl+alt+Delete'


def test_keydown_sequence_with_press_collapses_to_hotkey():
    response = {
        'choices': [
            {
                'message': {
                    'content': '## Thought:\nOpen security screen\n## Action:\nPress Ctrl+Alt+Delete\n## Code:\n```python\npyautogui.keyDown("ctrl")\npyautogui.keyDown("alt")\npyautogui.press("delete")\npyautogui.keyUp("alt")\npyautogui.keyUp("ctrl")\n```'
                }
            }
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(response)

    assert stop_reason == 'tool_use'
    assert blocks[1]['input']['action'] == 'key'
    assert blocks[1]['input']['text'] == 'ctrl+alt+Delete'


def test_semicolon_separated_commands_produce_multiple_tool_uses():
    response = {
        'choices': [
            {
                'message': {
                    'content': '## Thought:\nSearch\n## Action:\nFocus and type\n## Code:\n```python\npyautogui.click(x=10, y=20); pyautogui.write(text="settings")\n```'
                }
            }
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(response)

    assert stop_reason == 'tool_use'
    assert len(blocks) == 3
    assert blocks[1]['input']['action'] == 'left_click'
    assert blocks[2]['input']['action'] == 'type'
    assert blocks[2]['input']['text'] == 'settings'


def test_normalized_coordinates_use_display_metadata():
    response = {
        'choices': [
            {
                'message': {
                    'content': '## Thought:\nClick the item\n## Action:\nClick the item\n## Code:\n```python\npyautogui.click(x=0.482, y=0.526)\n```'
                }
            }
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(
        response,
        computer_options={'display_width_px': 1024, 'display_height_px': 768},
    )

    assert stop_reason == 'tool_use'
    assert blocks[1]['input']['action'] == 'left_click'
    assert blocks[1]['input']['coordinate'] == [494, 404]


def test_duplicate_thought_action_sections_use_latest_pair_without_repetition():
    response = {
        'choices': [
            {
                'message': {
                    'content': '## Thought:\nFirst thought.\n## Action:\nFirst action.\n## Thought:\nRepeated thought.\n## Action:\nRepeated action.'
                }
            }
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(response)

    assert stop_reason == 'end_turn'
    assert len(blocks) == 1
    assert blocks[0]['type'] == 'text'
    assert (
        blocks[0]['text']
        == '## Thought:\nRepeated thought.\n## Action:\nRepeated action.'
    )


def test_raw_json_code_block_maps_to_extraction():
    response = {
        'choices': [
            {
                'message': {
                    'content': '## Thought:\nDone\n## Action:\nReturn the result\n## Code:\n```python\n{\n  "name": "Tool Test but pixel dependent",\n  "result": {\n    "result": ["settings"]\n  }\n}\n```'
                }
            }
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(response)

    assert stop_reason == 'end_turn'
    assert blocks[1]['type'] == 'tool_use'
    assert blocks[1]['name'] == 'extraction'
    assert blocks[1]['input']['data']['name'] == 'Tool Test but pixel dependent'
    assert blocks[1]['input']['data']['result']['result'] == ['settings']


def test_raw_json_list_result_is_wrapped_to_match_expected_shape():
    response = {
        'choices': [
            {
                'message': {
                    'content': '## Thought:\nDone\n## Action:\nReturn the result\n## Code:\n```python\n{\n  "name": "Tool Test but pixel dependent",\n  "result": ["settings"]\n}\n```'
                }
            }
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(
        response,
        latest_api_definitions={
            'api_name': 'Tool Test but pixel dependent',
            'api_response_example': '{"result": ["settings1", "settings2"]}',
        },
    )

    assert stop_reason == 'end_turn'
    assert blocks[1]['name'] == 'extraction'
    assert blocks[1]['input']['data']['result'] == {'result': ['settings']}


def test_raw_json_name_mismatch_maps_to_ui_not_as_expected():
    response = {
        'choices': [
            {
                'message': {
                    'content': '## Thought:\nDone\n## Action:\nReturn the result\n## Code:\n```python\n{\n  "name": "Wrong Tool",\n  "result": {\n    "done": true\n  }\n}\n```'
                }
            }
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(
        response,
        latest_api_definitions={
            'api_name': 'Expected Tool',
            'api_response_example': '{"done": true}',
        },
    )

    assert stop_reason == 'end_turn'
    assert blocks[1]['name'] == 'ui_not_as_expected'
    assert 'does not match expected API name' in blocks[1]['input']['reasoning']


def test_malformed_response_returns_text_only():
    response = {
        'choices': [
            {'message': {'content': 'I am not following the requested format.'}}
        ]
    }

    blocks, stop_reason = convert_kimi_to_anthropic_response(response)

    assert stop_reason == 'end_turn'
    assert len(blocks) == 1
    assert blocks[0]['type'] == 'text'
