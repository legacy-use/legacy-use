"""
Core functionality for AI chat processing, shared between FastAPI and Streamlit interfaces.
"""

import base64
import logging
from datetime import datetime
from io import BytesIO
from typing import Any, Callable, Optional

from anthropic.types.beta import BetaMessageParam
from PIL import Image

from server.computer_use import (
    ApiResponseCallback,
    get_default_model_name,
    get_tool_version,
    sampling_loop,
)
from server.computer_use.tools import ToolResult
from server.img_utils import (
    get_screenshot_from_job,
    same_state_with_ground_truths_per_score,
    same_window_state,
)
from server.models.base import (
    APIDefinitionRuntime,
    APIResponse,
    JobStatus,
)
from server.settings_tenant import get_tenant_setting

# Set up logging
logger = logging.getLogger(__name__)


class APIGatewayCore:
    def __init__(self, tenant_schema: str, db_tenant=None):
        # Store tenant schema for use in methods
        self.tenant_schema = tenant_schema

        # Use tenant settings
        self.provider = get_tenant_setting(tenant_schema, 'API_PROVIDER')
        self.api_key = get_tenant_setting(tenant_schema, 'ANTHROPIC_API_KEY')

        # Set the model based on the provider
        self.model = get_default_model_name(self.provider)
        self.tool_version = get_tool_version(self.model)
        # Store the database service (tenant-aware or global)
        self.db_tenant = db_tenant

    async def load_api_definitions(self) -> dict[str, APIDefinitionRuntime]:
        """Load API definitions from the database."""
        # Get all API definitions, including archived ones
        api_definitions = await self.db_tenant.get_api_definitions(
            include_archived=True
        )

        # Load each definition and its active version
        definitions = {}
        for api_def in api_definitions:
            # Skip archived API definitions
            if api_def.is_archived:
                continue

            # Get the active version
            version = await self.db_tenant.get_active_api_definition_version(api_def.id)
            if not version:
                continue  # Skip if no active version

            # Create the API definition object
            definitions[api_def.name] = APIDefinitionRuntime(
                {
                    'name': api_def.name,
                    'description': api_def.description,
                    'parameters': version.parameters,
                    'custom_actions': version.custom_actions,
                    'prompt': version.prompt,
                    'prompt_cleanup': version.prompt_cleanup,
                    'response_example': version.response_example,
                    'version': version.version_number,
                    'version_id': str(version.id),
                }
            )

        return definitions

    async def execute_api(
        self,
        job_id: str,
        tool_callback: Optional[Callable[[ToolResult, str], None]] = None,
        api_response_callback: Optional[ApiResponseCallback] = None,
        output_callback: Optional[Callable[[Any], None]] = None,
        session_id: str = None,
    ) -> APIResponse:
        """Execute an API by name with the given parameters."""
        # Load API definitions fresh from the database
        api_definitions = await self.load_api_definitions()
        # Make sure job_id is still the correct ID string

        job_data = self.db_tenant.get_job(
            job_id
        )  # Renamed from job, assuming this might return a dict

        # Check if job_data is None or empty (if get_job can return None)
        if not job_data:
            raise ValueError(f"Job '{job_id}' not found")

        # Use dictionary access with .get() for safety
        job_api_name = job_data.get('api_name')
        job_parameters = job_data.get('parameters')

        # Ensure essential keys exist
        if job_api_name is None:
            raise ValueError(f"Job '{job_id}' data is missing 'api_name'")
        if job_parameters is None:
            raise ValueError(f"Job '{job_id}' data is missing 'parameters'")

        # Original logic using the extracted values
        if job_api_name not in api_definitions:
            raise ValueError(f"API '{job_api_name}' not found")

        api_def = api_definitions[job_api_name]

        # Check if messages already exist for this job
        message_count = self.db_tenant.count_job_messages(job_id)
        messages = []

        if message_count == 0:
            from server.routes.jobs import add_job_log

            add_job_log(
                job_id,
                'system',
                f'Executing API with parameters: {job_parameters}',
                self.tenant_schema,
            )

            # This is a new job or has no history, build the initial prompt
            prompt_text = api_def.build_prompt(job_parameters)
            logger.info(f'Job {job_id}: Sending initial prompt to model: {prompt_text}')

            # Add the initial prompt to standard job logs
            add_job_log(
                job_id,
                'system',
                {'message_type': 'initial_prompt', 'prompt': prompt_text},
                self.tenant_schema,
            )

            # Record the API version used for this job if available
            version_id = api_def.version_id if hasattr(api_def, 'version_id') else None
            if version_id:
                self.db_tenant.update_job(
                    job_id, {'api_definition_version_id': version_id}
                )

            # Create the initial message list for sampling_loop
            messages = [BetaMessageParam(role='user', content=prompt_text)]
        else:
            # Job is being resumed, pass empty messages list to sampling_loop
            logger.info(
                f'Job {job_id}: Resuming execution, {message_count} messages already exist in history. Skipping initial prompt.'
            )
            # Optionally log that we are resuming or confirm the API version is already set
            # api_version = job_data.get('api_definition_version_id')
            # if api_version:
            #    logger.info(f"Job {job_id}: Resuming with API version {api_version}")

        # The 'messages' list is now correctly populated (either with initial prompt or empty)

        # get last two jobs
        print(f'Job {job_id}: Getting last two jobs')
        print(f'Job {job_id}: Job data: {job_data}')
        current_version_id = job_data.get('api_definition_version_id')
        # TODO: how to select the two most "similar" jobs? Maybe by taking the shortest ones?
        last_two_jobs = self.db_tenant.get_last_two_success_jobs(current_version_id)
        print(f'Job {job_id}: Last two jobs: {last_two_jobs}')

        images = []
        # 3d1d796f-84f3-4a9f-967a-df914f0bec3c
        for old_job in last_two_jobs:
            print(
                f'Job {job_id}: Getting first tool use job log for job {old_job.get("id")}'
            )
            first_tool_use_job_log = self.db_tenant.get_first_tool_use_job_log(
                old_job.get('id')
            )
            content = first_tool_use_job_log.get('content')
            if content.get('has_image') and content.get('base64_image'):
                print(f'Job {job_id}: First tool use job log has image')
                base64_image = content.get('base64_image')
                # convert to Image.Image

                try:
                    img_bytes = base64.b64decode(base64_image)
                    images.append(Image.open(BytesIO(img_bytes)))
                except Exception as e:
                    print(f'Job {job_id}: Failed to decode or open image: {e}')
            else:
                print(f'Job {job_id}: First tool use job log does not have image')

        session_details = self.db_tenant.get_session(session_id)
        container_ip = session_details['container_ip']
        matching_state = False
        if len(images) == 2:
            print(f'Job {job_id}: Two images found, comparing with current job')
            result = same_window_state(images[0], images[1])
            print(f'Job {job_id}: Result: {result}')
            # take screenshot of current job

            current_job_screenshot = None

            current_job_screenshot = await get_screenshot_from_job(container_ip)

            if current_job_screenshot:
                result = same_state_with_ground_truths_per_score(
                    images[0], images[1], current_job_screenshot
                )
                print(f'Job {job_id}: Result with ground truths: {result}')
                matching_state = result.get('decision')
            else:
                print(f'Job {job_id}: Current job screenshot not found')

        if matching_state:
            # TODO: Get the tool calls of the last two jobs,
            # make sure that they are similar enough to each other and
            # if so, execute them, while checking after each tool call if the state is still matching
            # if not escelate to the model
            # also escelate to the model if the tool call is extraction
            tool_invocations_a = (
                self.db_tenant.get_all_tool_invocations_and_results_for_job(
                    last_two_jobs[0].get('id')
                )
            )
            tool_invocations_b = (
                self.db_tenant.get_all_tool_invocations_and_results_for_job(
                    last_two_jobs[1].get('id')
                )
            )
            last_iterration_was_a_tool_call = False
            for tool_a, tool_b in zip(tool_invocations_a, tool_invocations_b):
                print('#########################')
                print('NEW ITERATION')
                print('#########################')
                is_a_tool_call = tool_a.get('content').get('type') == 'tool_use'
                is_b_tool_call = tool_b.get('content').get('type') == 'tool_use'
                if is_a_tool_call != is_b_tool_call:
                    print(f'Job {job_id}: Tool calls are not similar')
                    matching_state = False
                    break

                if is_a_tool_call:
                    # TODO: check if the two tool calls are similar enough to each other
                    # TODO: execute the tool call
                    pass
                else:
                    # check images
                    new_image_a = tool_a.get('content').get('base64_image')
                    new_image_b = tool_b.get('content').get('base64_image')
                    # get new images from current job
                    current_job_screenshot = await get_screenshot_from_job(container_ip)
                    result = same_state_with_ground_truths_per_score(
                        new_image_a, new_image_b, current_job_screenshot
                    )
                    print(f'Job {job_id}: Result with ground truths: {result}')
                    matching_state = result.get('decision')
                    if not matching_state:
                        break

                if is_a_tool_call:
                    print(f'Job {job_id}: Next iteration will be a tool call')
                    last_iterration_was_a_tool_call = True
                else:
                    print(f'Job {job_id}: Next iteration will be a text response')
                    last_iterration_was_a_tool_call = False
            if last_iterration_was_a_tool_call:
                print(f'Job {job_id}: Last iteration was a tool call')
            else:
                print(f'Job {job_id}: Last iteration was a text response')

        try:
            # Execute the API call - sampling_loop will handle saving the messages if it receives any
            result, exchanges = await sampling_loop(
                job_id=job_id,
                db_tenant=self.db_tenant,
                model=self.model,
                provider=self.provider,
                system_prompt_suffix='',  # No additional suffix needed
                messages=messages,
                output_callback=output_callback or (lambda x: None),
                tool_output_callback=tool_callback or (lambda x, y: None),
                api_response_callback=api_response_callback or (lambda x, y, z: None),
                api_key=self.api_key,
                only_n_most_recent_images=3,
                session_id=session_id,
                tool_version=self.tool_version,
                tenant_schema=self.tenant_schema,
                job_data=job_data,
            )

            # --- Interpret result and Update DB Status --- START
            final_status = (
                JobStatus.ERROR
            )  # Default to error unless success/pause determined
            update_data = {
                'updated_at': datetime.now(),
                'completed_at': datetime.now(),  # Mark as completed on finish/error/pause
                'error': None,  # Clear previous error maybe?
                'result': None,  # Clear previous result maybe?
            }

            if isinstance(result, dict) and result.get('error'):
                error_reason = result.get('error_description') or result.get(
                    'error', 'Unknown error from sampling loop'
                )
                update_data['error'] = error_reason

                if result.get('error') in [
                    'Target Health Check Failed',
                    'UI Mismatch Detected',
                    'API Credits Exceeded',
                ]:
                    final_status = JobStatus.PAUSED
                    logger.info(f'Job {job_id} paused due to: {result.get("error")}')
                else:
                    # Other dict error returned by sampling_loop
                    final_status = JobStatus.ERROR
                    logger.error(
                        f'Job {job_id} failed. Error from sampling_loop: {error_reason}'
                    )
                # Include extraction data even on pause/error if present
                extraction_value = result.get('extraction')
                if extraction_value is not None and not isinstance(
                    extraction_value, dict
                ):
                    # Wrap non-dict extraction data in a dictionary
                    extraction_value = {'data': extraction_value}
                update_data['result'] = extraction_value

            elif (
                not isinstance(result, dict) or 'error' not in result
            ):  # Assuming success if not an error dict
                final_status = JobStatus.SUCCESS
                update_data['result'] = result  # Store the successful extraction
                logger.info(f'Job {job_id} completed successfully.')

            # Add final status to update data
            update_data['status'] = final_status.value

            # Perform the DB update
            try:
                self.db_tenant.update_job(job_id, update_data)
            except Exception as db_err:
                logger.error(
                    f'Failed to update job {job_id} final status to {final_status.value}: {db_err}'
                )
                # Decide how to handle - return response based on loop result anyway?

            # Ensure extraction is properly formatted for APIResponse
            extraction_data = update_data['result']
            if extraction_data is not None and not isinstance(extraction_data, dict):
                # Wrap non-dict extraction data in a dictionary
                extraction_data = {'data': extraction_data}

            # get all tool_calls of this job and print them
            tool_calls = self.db_tenant.get_all_tool_invocations_for_job(job_id)
            for tool_call in tool_calls:
                if tool_call.get('content').get('type') == 'tool_use':
                    content = tool_call.get('content')
                    print(f'Job {job_id}: Tool call: {content}')

            # Construct APIResponse based on determined status
            return APIResponse(
                status=final_status,
                reason=update_data['error'],  # Use the error reason we determined
                extraction=extraction_data,  # Use the properly formatted extraction data
                exchanges=exchanges,
            )
            # --- Interpret result and Update DB Status --- END

        except Exception as e:
            # Handle exceptions raised BY sampling_loop (e.g., ValueError, APIError, RuntimeError)
            error_message = str(e)
            logger.error(f'Job {job_id}: {error_message}', exc_info=True)
            # Update job status to ERROR on exception
            try:
                self.db_tenant.update_job(
                    job_id,
                    {
                        'status': JobStatus.ERROR.value,
                        'error': error_message,
                        'completed_at': datetime.now(),
                        'updated_at': datetime.now(),
                    },
                )
            except Exception as db_err:
                logger.error(
                    f'Failed to update job {job_id} status to ERROR after sampling_loop exception: {db_err}'
                )

            # Return ERROR APIResponse
            return APIResponse(
                status=JobStatus.ERROR,
                reason=error_message,
                extraction=None,
                exchanges=[],  # Exchanges might not be available if error was early
            )
        # --- Process results --- END (Removed original block)
