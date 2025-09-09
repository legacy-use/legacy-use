# def is_matching_state(last_two_jobs, container_ip):
#     if len(last_two_jobs) != 2:
#         print('Last two jobs not found')
#         return False

#     if not container_ip:
#         print('Container IP not found')
#         return False

#     images = []
#     for old_job in last_two_jobs:
#         if not old_job:
#             print('Old job is None')
#             continue
#         print(f'Getting first tool use job log for job {old_job.get("id")}')
#         first_tool_use_job_log = db_tenant.get_first_tool_use_job_log(old_job.get('id'))
#         content = first_tool_use_job_log.get('content')
#         if content and content.get('has_image') and content.get('base64_image'):
#             print('First tool use job log has image')


def _is_computer_use_tool_request(tool_invocation):
    is_message = tool_invocation.get('log_type') == 'message'
    is_computer_use = tool_invocation.get('content').get('name') == 'computer_use'
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
    if tool_invocations[0].get('content').get('type') != 'screenshot':
        print('First element does not invoke a screenshot')
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
        print('Current tool invocation is not a computer_use tool request')
        return None, None, offset + 2

    # if the tool_invocation is a screenshot, we return the screenshot and the next tool_use
    if _is_tool_request_of_type(tool_invocation, 'screenshot'):
        tool_use_invocation, prev_screenshot_response, offset = get_next_tool_use(
            tool_invocations, offset + 2
        )
        return tool_use_invocation, prev_screenshot_response, offset + 2

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
