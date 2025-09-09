import os

from server.img_utils import (
    base64_to_image,
    get_screenshot_from_job,
    same_state_with_ground_truths_per_score,
)


def _is_computer_use_tool_request(tool_invocation):
    is_message = tool_invocation.get('log_type') == 'message'
    is_computer_use = tool_invocation.get('content').get('name') == 'computer'
    return is_message and is_computer_use


def _is_tool_request_of_type(tool_invocation, type=None):
    is_message = tool_invocation.get('log_type') == 'message'
    is_tool_use = tool_invocation.get('content').get('type') == 'tool_use'
    is_of_type = True
    if type:
        is_of_type = tool_invocation.get('content').get('input').get('action') == type
    return is_message and is_tool_use and is_of_type


def _is_tool_response(tool_invocation, with_image):
    is_tool_use_response = tool_invocation.get('log_type') == 'tool_use'
    has_no_error = tool_invocation.get('content').get('error') == ''
    includes_image = True
    if with_image:
        includes_image = tool_invocation.get('content').get('has_image', False)
        includes_image = (
            includes_image and tool_invocation.get('content').get('base64_image') != ''
        )

    return is_tool_use_response and has_no_error and includes_image


def get_next_tool_use(
    tool_invocations, offset=0
) -> tuple[dict | None, str | None, int]:
    """
    Get the next tool_use from the tool_invocations.
    Returns the tool_use, the screenshot before the tool_use, and the offset to the next tool_use.
    """
    # when the last message, calls screenshot, we can safely return the following tool_use response (screenshot) and the following message (the comming tool_use)
    # when the last message was something different, we need to return the screenshot before that tool_use

    # make sure the first element is a message
    if tool_invocations[0].get('log_type') != 'message':
        print('First element is not a message')
        return None, None, offset

    # make sure the first element invoces a screenshot
    first_element_content = tool_invocations[0].get('content')
    if (
        first_element_content.get('name') != 'computer'
        or first_element_content.get('input').get('action') != 'screenshot'
    ):
        print(
            f'First element does not invoke a screenshot: {tool_invocations[0].get("content")}'
        )
        return None, None, offset

    # make sure the offset is even, since, we are only allowed to have tool_request with a tool_response
    if offset % 2 != 0:
        print('Offset is not even')
        return None, None, offset

    # get the next tool_invocations, while dropping the first offset elements
    tool_invocation = tool_invocations[offset]

    # we skip if not a computer_use tool request for now
    # atm this is only UI_NOT_AS_EXPECTED, EXTRACTION and CUSTOM_ACTION
    # UI_NOT_AS_EXPECTED and EXTRACTION shouldn't be autonomously invoked
    # TODO: CUSTOM_ACTION should be able to be invoked autonomously
    if not _is_computer_use_tool_request(tool_invocation):
        print(
            f'Current tool invocation is not a computer_use tool request: {tool_invocation.get("content").get("name")}'
        )
        return None, None, offset + 2

    # if the tool_invocation is a screenshot, we return the screenshot and the next tool_use
    if _is_tool_request_of_type(tool_invocation, 'screenshot'):
        print(
            f'Current tool invocation is a screenshot: {tool_invocation.get("content")}'
        )
        tool_use_invocation, prev_screenshot_response, offset = get_next_tool_use(
            tool_invocations, offset + 2
        )
        return tool_use_invocation, prev_screenshot_response, offset

    # if the invoced tool is not a screenshot, the offset must be >= 2, since we always have to start with a screenshot
    if offset < 2:
        print('Current tool invocation is not a screenshot, but offset is less than 2')
        return None, None, offset + 2

    # make sure the current tool invocation is a tool_use invocation
    if not _is_tool_request_of_type(tool_invocation):
        print('Current tool invocation is not a tool_use invocation')
        return None, None, offset + 2

    # get the type of the tool_use invocation
    tool_use_type = tool_invocation.get('content').get('input').get('action')

    prev_tool_use_response = tool_invocations[offset - 1]

    # check if the tool_use reponse from before has an image
    if not _is_tool_response(prev_tool_use_response, True):
        print('Tool use response from before does not have an image')
        return None, None, offset + 2

    # we have in tool_invocation a tool request and in prev_tool_use_response a screenshot of the inital state, before the tool_use was invoked
    # we return the tool_invocation and the prev_tool_use_response
    tool_use_invocation = tool_invocation.get('content')
    prev_screenshot_response = prev_tool_use_response.get('content').get('base64_image')

    # handle special cases for different tool_use_types
    if tool_use_type == 'wait':
        tool_use_invocation['input']['duration'] += (
            15  # we add 15s, to account for the AI inference time
        )

    return tool_use_invocation, prev_screenshot_response, offset + 2


async def check_and_compare_state(
    tool_invocations_a, tool_invocations_b, tool_use_count, container_ip
) -> tuple[dict | None, int]:
    """
    Return the next tool use and the tool use count, if the states are similar enough to continue.
    """
    next_tool_use_a, last_screenshot_a, offset_a = get_next_tool_use(
        tool_invocations_a, tool_use_count
    )
    next_tool_use_b, last_screenshot_b, offset_b = get_next_tool_use(
        tool_invocations_b, tool_use_count
    )
    print(f'Next tool use a: {next_tool_use_a}, next tool use b: {next_tool_use_b}')

    if offset_a != offset_b:
        print('Offsets are not equal')
        return None, tool_use_count

    tool_use_count = offset_a

    if next_tool_use_a is None or next_tool_use_b is None:
        print('Next tool uses are not equal')
        return None, tool_use_count

    if last_screenshot_a is None:
        print('Last screenshot a is not given')
        return None, tool_use_count

    if last_screenshot_b is None:
        print('Last screenshot b is not given')
        return None, tool_use_count

    # TODO: check if the two tool_uses are similar enough to continue

    last_screenshot_a = base64_to_image(last_screenshot_a)
    last_screenshot_b = base64_to_image(last_screenshot_b)
    current_job_screenshot = await get_screenshot_from_job(container_ip)

    if not current_job_screenshot:
        print('Current job screenshot is not given')
        return None, tool_use_count

    # save the three screenshots in dir
    temp_dir = f'./screenshots/{tool_use_count}'
    print(f'Saving screenshots to dir: {temp_dir}')
    # create dir if not exists
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    last_screenshot_a.save(os.path.join(temp_dir, 'last_screenshot_a.png'))
    last_screenshot_b.save(os.path.join(temp_dir, 'last_screenshot_b.png'))
    current_job_screenshot.save(os.path.join(temp_dir, 'current_job_screenshot.png'))

    result = same_state_with_ground_truths_per_score(
        last_screenshot_a, last_screenshot_b, current_job_screenshot
    )
    print(f'Result with ground truths: {result}')
    if result.get('decision'):
        print('States are similar enough to continue')
        return next_tool_use_a, tool_use_count
    else:
        print('States are not similar enough to continue')
        return None, tool_use_count
