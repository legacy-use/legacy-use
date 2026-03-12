from server.computer_use.handlers.utils.pyautogui_converter import (
    convert_pyautogui_code_to_tool_use,
    normalize_extraction_data,
    parse_task,
)


def test_click_converted():
    block = convert_pyautogui_code_to_tool_use(
        'pyautogui.click(x=10, y=20)',
        tool_id_prefix='toolu_test',
    )

    assert block['name'] == 'computer'
    assert block['input']['action'] == 'left_click'
    assert block['input']['coordinate'] == [10, 20]


def test_click_with_button_and_clicks_variants():
    double_click = convert_pyautogui_code_to_tool_use(
        'pyautogui.click(x=10, y=20, clicks=2)',
        tool_id_prefix='toolu_test',
    )
    right_click = convert_pyautogui_code_to_tool_use(
        'pyautogui.click(x=10, y=20, button="right")',
        tool_id_prefix='toolu_test',
    )

    assert double_click['input']['action'] == 'double_click'
    assert right_click['input']['action'] == 'right_click'


def test_placeholder_click_coordinate_is_rejected():
    block = convert_pyautogui_code_to_tool_use(
        'pyautogui.click(x=0, y=0)',
        tool_id_prefix='toolu_test',
    )

    assert block['name'] == 'ui_not_as_expected'
    assert 'Placeholder coordinate (0, 0)' in block['input']['reasoning']


def test_normalized_click_coordinates_are_scaled_with_display_metadata():
    block = convert_pyautogui_code_to_tool_use(
        'pyautogui.click(x=0.482, y=0.526)',
        tool_id_prefix='toolu_test',
        computer_options={'display_width_px': 1024, 'display_height_px': 768},
    )

    assert block['input']['action'] == 'left_click'
    assert block['input']['coordinate'] == [494, 404]


def test_scroll_is_sign_aware():
    block = convert_pyautogui_code_to_tool_use(
        'pyautogui.scroll(-5)',
        tool_id_prefix='toolu_test',
    )

    assert block['input']['action'] == 'scroll'
    assert block['input']['scroll_direction'] == 'down'
    assert block['input']['scroll_amount'] == 5


def test_hscroll_is_sign_aware():
    block = convert_pyautogui_code_to_tool_use(
        'pyautogui.hscroll(7)',
        tool_id_prefix='toolu_test',
    )

    assert block['input']['action'] == 'scroll'
    assert block['input']['scroll_direction'] == 'right'
    assert block['input']['scroll_amount'] == 7


def test_hotkey_is_normalized():
    block = convert_pyautogui_code_to_tool_use(
        'pyautogui.hotkey(keys=["ctrl", "l"])',
        tool_id_prefix='toolu_test',
    )

    assert block['input']['action'] == 'key'
    assert block['input']['text'] == 'ctrl+l'


def test_hotkey_supports_positional_arguments():
    block = convert_pyautogui_code_to_tool_use(
        'pyautogui.hotkey("ctrl", "l")',
        tool_id_prefix='toolu_test',
    )

    assert block['input']['action'] == 'key'
    assert block['input']['text'] == 'ctrl+l'


def test_write_supports_text_keyword():
    block = convert_pyautogui_code_to_tool_use(
        'pyautogui.write(text="settings")',
        tool_id_prefix='toolu_test',
    )

    assert block['input']['action'] == 'type'
    assert block['input']['text'] == 'settings'


def test_write_supports_positional_and_keyword_arguments():
    block = convert_pyautogui_code_to_tool_use(
        'pyautogui.write("settings", interval=0.05)',
        tool_id_prefix='toolu_test',
    )

    assert block['input']['action'] == 'type'
    assert block['input']['text'] == 'settings'


def test_wait_defaults_to_20_seconds():
    block = convert_pyautogui_code_to_tool_use(
        'computer.wait()',
        tool_id_prefix='toolu_test',
    )

    assert block['input']['action'] == 'wait'
    assert block['input']['duration'] == 20.0


def test_wait_uses_explicit_duration():
    block = convert_pyautogui_code_to_tool_use(
        'computer.wait(seconds=3)',
        tool_id_prefix='toolu_test',
    )

    assert block['input']['action'] == 'wait'
    assert block['input']['duration'] == 3.0


def test_sleep_alias_maps_to_wait():
    pyautogui_block = convert_pyautogui_code_to_tool_use(
        'pyautogui.sleep(0.5)',
        tool_id_prefix='toolu_test',
    )
    time_block = convert_pyautogui_code_to_tool_use(
        'time.sleep(1.5)',
        tool_id_prefix='toolu_test',
    )

    assert pyautogui_block['input']['action'] == 'wait'
    assert pyautogui_block['input']['duration'] == 0.5
    assert time_block['input']['action'] == 'wait'
    assert time_block['input']['duration'] == 1.5


def test_parse_task_pairs_code_with_nearest_preceding_thought_and_action():
    task = parse_task(
        '## Thought:\nFirst thought.\n'
        '## Action:\nFirst action.\n'
        '## Thought:\nFinal thought.\n'
        '## Action:\nFinal action.\n'
        '## Code:\n```python\ncomputer.terminate(status="success", data="{\\"done\\": true}")\n```'
    )

    assert task['thought'] == 'Final thought.'
    assert task['action'] == 'Final action.'
    assert (
        task['code']
        == 'computer.terminate(status="success", data="{\\"done\\": true}")'
    )


def test_terminate_success_maps_to_extraction():
    block = convert_pyautogui_code_to_tool_use(
        'computer.terminate(status="success", data="{\\"foo\\": \\"bar\\"}")',
        tool_id_prefix='toolu_test',
    )

    assert block['name'] == 'extraction'
    assert block['input']['data']['result'] == {'foo': 'bar'}


def test_terminate_success_uses_existing_name_and_result_without_nesting():
    block = convert_pyautogui_code_to_tool_use(
        'computer.terminate(status="success", data="{\\"name\\": \\"Tool Test but pixel dependent\\", \\"result\\": {\\"result\\": [\\"settings\\"]}}")',
        tool_id_prefix='toolu_test',
        latest_api_definitions={
            'api_name': 'Tool Test but pixel dependent',
            'api_response_example': '{"result": ["settings1", "settings2"]}',
        },
    )

    assert block['name'] == 'extraction'
    assert block['input']['data']['name'] == 'Tool Test but pixel dependent'
    assert block['input']['data']['result'] == {'result': ['settings']}


def test_normalize_extraction_data_wraps_list_to_match_example():
    normalized = normalize_extraction_data(
        {
            'name': 'Tool Test but pixel dependent',
            'result': ['Settings', 'Mouse settings'],
        },
        latest_api_definitions={
            'api_name': 'Tool Test but pixel dependent',
            'api_response_example': '{"result": ["settings1", "settings2"]}',
        },
    )

    assert normalized == {
        'name': 'Tool Test but pixel dependent',
        'result': {'result': ['Settings', 'Mouse settings']},
    }


def test_normalize_extraction_data_prefers_list_field_for_array_schema():
    normalized = normalize_extraction_data(
        {
            'name': 'Tool Test',
            'result': {
                'performance_metrics': {'cpu': '12%'},
                'settings_search_results': ['Settings', 'System settings'],
            },
        },
        latest_api_definitions={
            'api_name': 'Tool Test',
            'api_response_example': '{"results": ["1"]}',
        },
    )

    assert normalized == {
        'name': 'Tool Test',
        'result': {'results': ['Settings', 'System settings']},
    }


def test_terminate_success_name_mismatch_maps_to_ui_not_as_expected():
    block = convert_pyautogui_code_to_tool_use(
        'computer.terminate(status="success", data="{\\"name\\": \\"Wrong Tool\\", \\"result\\": {\\"done\\": true}}")',
        tool_id_prefix='toolu_test',
        latest_api_definitions={
            'api_name': 'Expected Tool',
            'api_response_example': '{"done": true}',
        },
    )

    assert block['name'] == 'ui_not_as_expected'
    assert 'does not match expected API name' in block['input']['reasoning']


def test_terminate_failure_maps_to_ui_not_as_expected():
    block = convert_pyautogui_code_to_tool_use(
        'computer.terminate(status="failure", data="{\\"reasoning\\": \\"blocked\\"}")',
        tool_id_prefix='toolu_test',
    )

    assert block['name'] == 'ui_not_as_expected'
    assert block['input']['reasoning'] == 'blocked'


def test_custom_action_is_supported():
    block = convert_pyautogui_code_to_tool_use(
        'computer.custom_action(action_name="login", input_parameters={"username": "demo"})',
        tool_id_prefix='toolu_test',
    )

    assert block['name'] == 'custom_action'
    assert block['input']['action_name'] == 'login'
    assert block['input']['input_parameters'] == {'username': 'demo'}
