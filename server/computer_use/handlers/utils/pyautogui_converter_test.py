from server.computer_use.handlers.utils.pyautogui_converter import (
    convert_pyautogui_code_to_tool_use,
)


def test_click_converted():
    block = convert_pyautogui_code_to_tool_use(
        'pyautogui.click(x=10, y=20)',
        tool_id_prefix='toolu_test',
    )

    assert block['name'] == 'computer'
    assert block['input']['action'] == 'left_click'
    assert block['input']['coordinate'] == [10, 20]


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


def test_terminate_success_maps_to_extraction():
    block = convert_pyautogui_code_to_tool_use(
        'computer.terminate(status="success", data="{\\"foo\\": \\"bar\\"}")',
        tool_id_prefix='toolu_test',
    )

    assert block['name'] == 'extraction'
    assert block['input']['data']['result'] == {'foo': 'bar'}


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
