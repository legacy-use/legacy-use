<br />

The Gemini 2.5 Computer Use Preview model and tool enable you to build browser
control agents that interact with and automate tasks. Using screenshots, the
Computer Use model can "see" a computer screen, and "act" by generating specific
UI actions like mouse clicks and keyboard inputs. Similar to function calling,
you need to write the client-side application code to receive and execute the
Computer Use actions.

With Computer Use, you can build agents that:

- Automate repetitive data entry or form filling on websites.
- Perform automated testing of web applications and user flows
- Conduct research across various websites (e.g., gathering product information, prices, and reviews from ecommerce sites to inform a purchase)

The easiest way to test the Gemini Computer Use model is through the [reference
implementation](https://github.com/google/computer-use-preview/) or
[Browserbase demo environment](http://gemini.browserbase.com).
| **Note:** As a Preview model, the Gemini 2.5 Computer Use model may be prone to errors and security vulnerabilities. We recommend supervising closely for important tasks, and that you avoid using the Computer Use model for tasks involving critical decisions, sensitive data, or actions where serious errors cannot be corrected. We encourage you to review the [Safety best
| practices](https://ai.google.dev/gemini-api/docs/computer-use#safety-best-practices), the [Prohibited Use
| Policy](https://policies.google.com/terms/generative-ai/use-policy) and [Gemini
| API Additional Terms of Service](https://ai.google.dev/terms).

## How Computer Use works

To build a browser control agent with the Computer Use model, implement
an agent loop that does the following:

1. [**Send a request to the model**](https://ai.google.dev/gemini-api/docs/computer-use#send-request)

   - Add the Computer Use tool and optionally any custom user-defined functions or excluded functions to your API request.
   - Prompt the Computer Use model with the user's request.
2. [**Receive the model response**](https://ai.google.dev/gemini-api/docs/computer-use#model-response)

   - The Computer Use model analyzes the user request and screenshot, and generates a response which includes a suggested `function_call` representing a UI action (e.g., "click at coordinate (x,y)" or "type 'text'"). For a description of all UI actions supported by the Computer Use model, see [Supported actions](https://ai.google.dev/gemini-api/docs/computer-use#supported-actions).
   - The API response may also include a `safety_decision` from an internal safety system that checks the model's proposed action. This `safety_decision` classifies the action as:
     - **Regular / allowed:** The action is considered safe. This may also be represented by no `safety_decision` being present.
     - **Requires confirmation (`require_confirmation`):** The model is about to perform an action that may be risky (e.g., clicking on an "accept cookie banner").
3. [**Execute the received action**](https://ai.google.dev/gemini-api/docs/computer-use#execute-actions)

   - Your client-side code receives the `function_call` and any accompanying `safety_decision`.
     - **Regular / allowed:** If the `safety_decision` indicates regular / allowed (or if no `safety_decision` is present), your client-side code can execute the specified `function_call` in your target environment (e.g., a web browser).
     - **Requires confirmation:** If the `safety_decision` indicates requires confirmation, your application must prompt the end-user for confirmation before executing the `function_call`. If the user confirms, proceed to execute the action. If the user denies, don't execute the action.
4. [**Capture the new environment state**](https://ai.google.dev/gemini-api/docs/computer-use#capture-state)

   - If the action has been executed, your client captures a new screenshot of the GUI and the current URL to send back to the Computer Use model as part of a `function_response`.
   - If an action was blocked by the safety system or denied confirmation by the user, your application might send a different form of feedback to the model or end the interaction.

This process repeats from step 2 with the Computer Use model using the new
screenshot and the ongoing goal to suggest the next action. The loop continues
until the task is completed, an error occurs, or the process is terminated
(e.g., due to a "block" safety response or user decision).

![Computer Use
overview](https://ai.google.dev/static/gemini-api/docs/images/computer_use.png)

## How to implement Computer Use

Before building with the Computer Use model and tool you will need to set up the
following:

- **Secure execution environment:** For safety reasons, you should run your Computer Use agent in a secure and controlled environment (e.g., a sandboxed virtual machine, a container, or a dedicated browser profile with limited permissions).
- **Client-side action handler:** You will need to implement client-side logic to execute the actions generated by the model and capture screenshots of the environment after each action.

The examples in this section use a browser as the execution environment
and [Playwright](https://playwright.dev/) as the client-side action handler. To
run these samples you must install the necessary dependencies and initialize a
Playwright browser instance.  

#### Install Playwright

<br />

```
    pip install google-genai playwright
    playwright install chromium
    
```  

#### Initialize Playwright browser instance

<br />

```
    from playwright.sync_api import sync_playwright

    # 1. Configure screen dimensions for the target environment
    SCREEN_WIDTH = 1440
    SCREEN_HEIGHT = 900

    # 2. Start the Playwright browser
    # In production, utilize a sandboxed environment.
    playwright = sync_playwright().start()
    # Set headless=False to see the actions performed on your screen
    browser = playwright.chromium.launch(headless=False)

    # 3. Create a context and page with the specified dimensions
    context = browser.new_context(
        viewport={"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}
    )
    page = context.new_page()

    # 4. Navigate to an initial page to start the task
    page.goto("https://www.google.com")

    # The 'page', 'SCREEN_WIDTH', and 'SCREEN_HEIGHT' variables
    # will be used in the steps below.
    
```

Sample code for extending to an Android
environment is included in the [Using custom user-defined
functions](https://ai.google.dev/gemini-api/docs/computer-use#custom-functions) section.

### 1. Send a request to the model

Add the Computer Use tool to your API request and send a prompt to the Computer
Use model that includes the user's goal.
You must use the Gemini Computer Use model,
`gemini-2.5-computer-use-preview-10-2025`. If you try to use the Computer Use
tool with a different model, you will get an error.

You can also optionally add the following parameters:

- **Excluded actions:** If there are any actions from the list of [Supported
  UI actions](https://ai.google.dev/gemini-api/docs/computer-use#supported-actions) that you don't want the model to take, specify these actions as `excluded_predefined_functions`.
- **User-defined functions:** In addition to the Computer Use tool, you may want to include custom user-defined functions.

Note that there is no need to specify the display size when issuing a request;
the model predicts pixel coordinates scaled to the height and width of the
screen.  

### Python

    from google import genai
    from google.genai import types
    from google.genai.types import Content, Part

    client = genai.Client()

    # Specify predefined functions to exclude (optional)
    excluded_functions = ["drag_and_drop"]

    generate_content_config = genai.types.GenerateContentConfig(
        tools=[
            # 1. Computer Use tool with browser environment
            types.Tool(
                computer_use=types.ComputerUse(
                    environment=types.Environment.ENVIRONMENT_BROWSER,
                    # Optional: Exclude specific predefined functions
                    excluded_predefined_functions=excluded_functions
                    )
                  ),
            # 2. Optional: Custom user-defined functions
            #types.Tool(
              # function_declarations=custom_functions
              #   )
              ],
      )

    # Create the content with user message
    contents=[
        Content(
            role="user",
            parts=[
                Part(text="Search for highly rated smart fridges with touchscreen, 2 doors, around 25 cu ft, priced below 4000 dollars on Google Shopping. Create a bulleted list of the 3 cheapest options in the format of name, description, price in an easy-to-read layout."),
            ],
        )
    ]

    # Generate content with the configured settings
    response = client.models.generate_content(
        model='gemini-2.5-computer-use-preview-10-2025',
        contents=contents,
        config=generate_content_config,
    )

    # Print the response output
    print(response)

For an example with custom functions, see [Using custom
user-defined functions](https://ai.google.dev/gemini-api/docs/computer-use#custom-functions).

### 2. Receive the model response

The Computer Use model will respond with one or more `FunctionCalls` if it
determines UI actions are needed to complete the task. Computer Use supports
parallel function calling, meaning the model can return multiple actions in a
single turn.

Here is an example model response.  

    {
      "content": {
        "parts": [
          {
            "text": "I will type the search query into the search bar. The search bar is in the center of the page."
          },
          {
            "function_call": {
              "name": "type_text_at",
              "args": {
                "x": 371,
                "y": 470,
                "text": "highly rated smart fridges with touchscreen, 2 doors, around 25 cu ft, priced below 4000 dollars on Google Shopping",
                "press_enter": true
              }
            }
          }
        ]
      }
    }

### 3. Execute the received actions

Your application code needs to parse the model response, execute the actions,
and collect the results.

The example code below extracts function calls from the Computer Use model
response, and translates them into actions that can be executed with Playwright.
The model outputs normalized coordinates (0-999) regardless of the input image
dimensions, so part of the translation step is converting these normalized
coordinates back to actual pixel values.

The recommended screen size for use
with the Computer Use model is (1440, 900). The model will work with any
resolution, though the quality of the results may be impacted.

Note that this example only includes the implementation for the 3 most common
UI actions: `open_web_browser`, `click_at`, and `type_text_at`. For
production use cases, you will need to implement all other UI actions from the
[Supported actions](https://ai.google.dev/gemini-api/docs/computer-use#supported-actions) list unless you explicitly add them as
`excluded_predefined_functions`.  

### Python

    from typing import Any, List, Tuple
    import time

    def denormalize_x(x: int, screen_width: int) -> int:
        """Convert normalized x coordinate (0-1000) to actual pixel coordinate."""
        return int(x / 1000 * screen_width)

    def denormalize_y(y: int, screen_height: int) -> int:
        """Convert normalized y coordinate (0-1000) to actual pixel coordinate."""
        return int(y / 1000 * screen_height)

    def execute_function_calls(candidate, page, screen_width, screen_height):
        results = []
        function_calls = []
        for part in candidate.content.parts:
            if part.function_call:
                function_calls.append(part.function_call)

        for function_call in function_calls:
            action_result = {}
            fname = function_call.name
            args = function_call.args
            print(f"  -> Executing: {fname}")

            try:
                if fname == "open_web_browser":
                    pass # Already open
                elif fname == "click_at":
                    actual_x = denormalize_x(args["x"], screen_width)
                    actual_y = denormalize_y(args["y"], screen_height)
                    page.mouse.click(actual_x, actual_y)
                elif fname == "type_text_at":
                    actual_x = denormalize_x(args["x"], screen_width)
                    actual_y = denormalize_y(args["y"], screen_height)
                    text = args["text"]
                    press_enter = args.get("press_enter", False)

                    page.mouse.click(actual_x, actual_y)
                    # Simple clear (Command+A, Backspace for Mac)
                    page.keyboard.press("Meta+A")
                    page.keyboard.press("Backspace")
                    page.keyboard.type(text)
                    if press_enter:
                        page.keyboard.press("Enter")
                else:
                    print(f"Warning: Unimplemented or custom function {fname}")

                # Wait for potential navigations/renders
                page.wait_for_load_state(timeout=5000)
                time.sleep(1)

            except Exception as e:
                print(f"Error executing {fname}: {e}")
                action_result = {"error": str(e)}

            results.append((fname, action_result))

        return results

### 4. Capture the new environment state

After executing the actions, send the result of the function execution back to
the model so it can use this information to generate the next action. If
multiple actions (parallel calls) were executed, you must send a
`FunctionResponse` for each one in the subsequent user turn.  

### Python


    def get_function_responses(page, results):
        screenshot_bytes = page.screenshot(type="png")
        current_url = page.url
        function_responses = []
        for name, result in results:
            response_data = {"url": current_url}
            response_data.update(result)
            function_responses.append(
                types.FunctionResponse(
                    name=name,
                    response=response_data,
                    parts=[types.FunctionResponsePart(
                            inline_data=types.FunctionResponseBlob(
                                mime_type="image/png",
                                data=screenshot_bytes))
                    ]
                )
            )
        return function_responses

## Build an agent loop

To enable multi-step interactions, combine the four steps from the [How to
implement Computer Use](https://ai.google.dev/gemini-api/docs/computer-use#implement-computer-use) section into a loop.
Remember to manage the conversation history correctly by appending both model
responses and your function responses.

To run this code sample you need to:

- Install the [necessary Playwright
  dependencies](https://ai.google.dev/gemini-api/docs/computer-use#expandable-1).
- Define the helper functions from steps [(3) Execute the received
  actions](https://ai.google.dev/gemini-api/docs/computer-use#execute-actions) and [(4) Capture the new environment
  state](https://ai.google.dev/gemini-api/docs/computer-use#capture-state).

### Python


    import time
    from typing import Any, List, Tuple
    from playwright.sync_api import sync_playwright

    from google import genai
    from google.genai import types
    from google.genai.types import Content, Part

    client = genai.Client()

    # Constants for screen dimensions
    SCREEN_WIDTH = 1440
    SCREEN_HEIGHT = 900

    # Setup Playwright
    print("Initializing browser...")
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT})
    page = context.new_page()

    # Define helper functions. Copy/paste from steps 3 and 4
    # def denormalize_x(...)
    # def denormalize_y(...)
    # def execute_function_calls(...)
    # def get_function_responses(...)

    try:
        # Go to initial page
        page.goto("https://ai.google.dev/gemini-api/docs")

        # Configure the model (From Step 1)
        config = types.GenerateContentConfig(
            tools=[types.Tool(computer_use=types.ComputerUse(
                environment=types.Environment.ENVIRONMENT_BROWSER
            ))],
            thinking_config=types.ThinkingConfig(include_thoughts=True),
        )

        # Initialize history
        initial_screenshot = page.screenshot(type="png")
        USER_PROMPT = "Go to ai.google.dev/gemini-api/docs and search for pricing."
        print(f"Goal: {USER_PROMPT}")

        contents = [
            Content(role="user", parts=[
                Part(text=USER_PROMPT),
                Part.from_bytes(data=initial_screenshot, mime_type='image/png')
            ])
        ]

        # Agent Loop
        turn_limit = 5
        for i in range(turn_limit):
            print(f"\n--- Turn {i+1} ---")
            print("Thinking...")
            response = client.models.generate_content(
                model='gemini-2.5-computer-use-preview-10-2025',
                contents=contents,
                config=config,
            )

            candidate = response.candidates[0]
            contents.append(candidate.content)

            has_function_calls = any(part.function_call for part in candidate.content.parts)
            if not has_function_calls:
                text_response = " ".join([part.text for part in candidate.content.parts if part.text])
                print("Agent finished:", text_response)
                break

            print("Executing actions...")
            results = execute_function_calls(candidate, page, SCREEN_WIDTH, SCREEN_HEIGHT)

            print("Capturing state...")
            function_responses = get_function_responses(page, results)

            contents.append(
                Content(role="user", parts=[Part(function_response=fr) for fr in function_responses])
            )

    finally:
        # Cleanup
        print("\nClosing browser...")
        browser.close()
        playwright.stop()

## Using custom user-defined functions

You can optionally include custom user-defined functions in your request to
extend the functionality of the model. The example below adapts the Computer Use
model and tool for mobile use cases by including custom user-defined actions
like `open_app`, `long_press_at`, and `go_home`, while excluding
browser-specific actions. The model can intelligently call these custom
functions alongside standard UI actions to complete tasks in non-browser
environments.  

### Python

    from typing import Optional, Dict, Any

    from google import genai
    from google.genai import types
    from google.genai.types import Content, Part

    client = genai.Client()

    SYSTEM_PROMPT = """You are operating an Android phone. Today's date is October 15, 2023, so ignore any other date provided.
    * To provide an answer to the user, *do not use any tools* and output your answer on a separate line. IMPORTANT: Do not add any formatting or additional punctuation/text, just output the answer by itself after two empty lines.
    * Make sure you scroll down to see everything before deciding something isn't available.
    * You can open an app from anywhere. The icon doesn't have to currently be on screen.
    * Unless explicitly told otherwise, make sure to save any changes you make.
    * If text is cut off or incomplete, scroll or click into the element to get the full text before providing an answer.
    * IMPORTANT: Complete the given task EXACTLY as stated. DO NOT make any assumptions that completing a similar task is correct.  If you can't find what you're looking for, SCROLL to find it.
    * If you want to edit some text, ONLY USE THE `type` tool. Do not use the onscreen keyboard.
    * Quick settings shouldn't be used to change settings. Use the Settings app instead.
    * The given task may already be completed. If so, there is no need to do anything.
    """

    def open_app(app_name: str, intent: Optional[str] = None) -> Dict[str, Any]:
        """Opens an app by name.

        Args:
            app_name: Name of the app to open (any string).
            intent: Optional deep-link or action to pass when launching, if the app supports it.

        Returns:
            JSON payload acknowledging the request (app name and optional intent).
        """
        return {"status": "requested_open", "app_name": app_name, "intent": intent}

    def long_press_at(x: int, y: int) -> Dict[str, int]:
        """Long-press at a specific screen coordinate.

        Args:
            x: X coordinate (absolute), scaled to the device screen width (pixels).
            y: Y coordinate (absolute), scaled to the device screen height (pixels).

        Returns:
            Object with the coordinates pressed and the duration used.
        """
        return {"x": x, "y": y}

    def go_home() -> Dict[str, str]:
        """Navigates to the device home screen.

        Returns:
            A small acknowledgment payload.
        """
        return {"status": "home_requested"}

    #  Build function declarations
    CUSTOM_FUNCTION_DECLARATIONS = [
        types.FunctionDeclaration.from_callable(client=client, callable=open_app),
        types.FunctionDeclaration.from_callable(client=client, callable=long_press_at),
        types.FunctionDeclaration.from_callable(client=client, callable=go_home),
    ]

    #Exclude browser functions
    EXCLUDED_PREDEFINED_FUNCTIONS = [
        "open_web_browser",
        "search",
        "navigate",
        "hover_at",
        "scroll_document",
        "go_forward",
        "key_combination",
        "drag_and_drop",
    ]

    #Utility function to construct a GenerateContentConfig
    def make_generate_content_config() -> genai.types.GenerateContentConfig:
        """Return a fixed GenerateContentConfig with Computer Use + custom functions."""
        return genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[
                types.Tool(
                    computer_use=types.ComputerUse(
                        environment=types.Environment.ENVIRONMENT_BROWSER,
                        excluded_predefined_functions=EXCLUDED_PREDEFINED_FUNCTIONS,
                    )
                ),
                types.Tool(function_declarations=CUSTOM_FUNCTION_DECLARATIONS),
            ],
        )

    # Create the content with user message
    contents: list[Content] = [
        Content(
            role="user",
            parts=[
                # text instruction
                Part(text="Open Chrome, then long-press at 200,400."),
            ],
        )
    ]

    # Build your fixed config (from helper)
    config = make_generate_content_config()

    # Generate content with the configured settings
    response = client.models.generate_content(
            model='gemini-2.5-computer-use-preview-10-2025',
            contents=contents,
            config=config,
        )

    print(response)

## Supported UI actions

The Computer Use model can request the following UI actions via a
`FunctionCall`. Your client-side code must implement the execution logic for
these actions. See the [reference
implementation](https://github.com/google/computer-use-preview) for
examples.

|     Command Name     |                                                                                    Description                                                                                    |                                                            Arguments (in Function Call)                                                             |                                         Example Function Call                                          |
|----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|
| **open_web_browser** | Opens the web browser.                                                                                                                                                            | None                                                                                                                                                | `{"name": "open_web_browser", "args": {}}`                                                             |
| **wait_5_seconds**   | Pauses execution for 5 seconds to allow dynamic content to load or animations to complete.                                                                                        | None                                                                                                                                                | `{"name": "wait_5_seconds", "args": {}}`                                                               |
| **go_back**          | Navigates to the previous page in the browser's history.                                                                                                                          | None                                                                                                                                                | `{"name": "go_back", "args": {}}`                                                                      |
| **go_forward**       | Navigates to the next page in the browser's history.                                                                                                                              | None                                                                                                                                                | `{"name": "go_forward", "args": {}}`                                                                   |
| **search**           | Navigates to the default search engine's homepage (e.g., Google). Useful for starting a new search task.                                                                          | None                                                                                                                                                | `{"name": "search", "args": {}}`                                                                       |
| **navigate**         | Navigates the browser directly to the specified URL.                                                                                                                              | `url`: str                                                                                                                                          | `{"name": "navigate", "args": {"url": "https://www.wikipedia.org"}}`                                   |
| **click_at**         | Clicks at a specific coordinate on the webpage. The x and y values are based on a 1000x1000 grid and are scaled to the screen dimensions.                                         | `y`: int (0-999), `x`: int (0-999)                                                                                                                  | `{"name": "click_at", "args": {"y": 300, "x": 500}}`                                                   |
| **hover_at**         | Hovers the mouse at a specific coordinate on the webpage. Useful for revealing sub-menus. x and y are based on a 1000x1000 grid.                                                  | `y`: int (0-999) `x`: int (0-999)                                                                                                                   | `{"name": "hover_at", "args": {"y": 150, "x": 250}}`                                                   |
| **type_text_at**     | Types text at a specific coordinate, defaults to clearing the field first and pressing ENTER after typing, but these can be disabled. x and y are based on a 1000x1000 grid.      | `y`: int (0-999), `x`: int (0-999), `text`: str, `press_enter`: bool (Optional, default True), `clear_before_typing`: bool (Optional, default True) | `{"name": "type_text_at", "args": {"y": 250, "x": 400, "text": "search query", "press_enter": false}}` |
| **key_combination**  | Press keyboard keys or combinations, such as "Control+C" or "Enter". Useful for triggering actions (like submitting a form with "Enter") or clipboard operations.                 | `keys`: str (e.g. 'enter', 'control+c').                                                                                                            | `{"name": "key_combination", "args": {"keys": "Control+A"}}`                                           |
| **scroll_document**  | Scrolls the entire webpage "up", "down", "left", or "right".                                                                                                                      | `direction`: str ("up", "down", "left", or "right")                                                                                                 | `{"name": "scroll_document", "args": {"direction": "down"}}`                                           |
| **scroll_at**        | Scrolls a specific element or area at coordinate (x, y) in the specified direction by a certain magnitude. Coordinates and magnitude (default 800) are based on a 1000x1000 grid. | `y`: int (0-999), `x`: int (0-999), `direction`: str ("up", "down", "left", "right"), `magnitude`: int (0-999, Optional, default 800)               | `{"name": "scroll_at", "args": {"y": 500, "x": 500, "direction": "down", "magnitude": 400}}`           |
| **drag_and_drop**    | Drags an element from a starting coordinate (x, y) and drops it at a destination coordinate (destination_x, destination_y). All coordinates are based on a 1000x1000 grid.        | `y`: int (0-999), `x`: int (0-999), `destination_y`: int (0-999), `destination_x`: int (0-999)                                                      | `{"name": "drag_and_drop", "args": {"y": 100, "x": 100, "destination_y": 500, "destination_x": 500}}`  |

## Safety and security

### Acknowledge safety decision

Depending on the action, the model response might also include a
`safety_decision` from an internal safety system that checks the model's
proposed action.  

    {
      "content": {
        "parts": [
          {
            "text": "I have evaluated step 2. It seems Google detected unusual traffic and is asking me to verify I'm not a robot. I need to click the 'I'm not a robot' checkbox located near the top left (y=98, x=95).",
          },
          {
            "function_call": {
              "name": "click_at",
              "args": {
                "x": 60,
                "y": 100,
                "safety_decision": {
                  "explanation": "I have encountered a CAPTCHA challenge that requires interaction. I need you to complete the challenge by clicking the 'I'm not a robot' checkbox and any subsequent verification steps.",
                  "decision": "require_confirmation"
                }
              }
            }
          }
        ]
      }
    }

If the `safety_decision` is `require_confirmation`, you must
ask the end user to confirm before proceeding with executing the action. Per the
[terms of service](https://ai.google.dev/gemini-api/terms), you are not allowed
to bypass requests for human confirmation.

This code sample prompts the end-user for confirmation before executing the
action. If the user does not confirm the action, the loop terminates. If the
user confirms the action, the action is executed and the
`safety_acknowledgement` field is marked as `True`.  

### Python

    import termcolor

    def get_safety_confirmation(safety_decision):
        """Prompt user for confirmation when safety check is triggered."""
        termcolor.cprint("Safety service requires explicit confirmation!", color="red")
        print(safety_decision["explanation"])

        decision = ""
        while decision.lower() not in ("y", "n", "ye", "yes", "no"):
            decision = input("Do you wish to proceed? [Y]es/[N]o\n")

        if decision.lower() in ("n", "no"):
            return "TERMINATE"
        return "CONTINUE"

    def execute_function_calls(candidate, page, screen_width, screen_height):

        # ... Extract function calls from response ...

        for function_call in function_calls:
            extra_fr_fields = {}

            # Check for safety decision
            if 'safety_decision' in function_call.args:
                decision = get_safety_confirmation(function_call.args['safety_decision'])
                if decision == "TERMINATE":
                    print("Terminating agent loop")
                    break
                extra_fr_fields["safety_acknowledgement"] = "true" # Safety acknowledgement

            # ... Execute function call and append to results ...

If the user confirms, you must include the safety acknowledgement in
your `FunctionResponse`.  

### Python

    function_response_parts.append(
        FunctionResponse(
            name=name,
            response={"url": current_url,
                      **extra_fr_fields},  # Include safety acknowledgement
            parts=[
                types.FunctionResponsePart(
                    inline_data=types.FunctionResponseBlob(
                        mime_type="image/png", data=screenshot
                    )
                 )
               ]
             )
           )

### Safety best practices

Computer Use API is a novel API and presents new risks that developers should be
mindful of:

- **Untrusted content \& scams:** As the model tries to achieve the user's goal, it may rely on untrustworthy sources of information and instructions from the screen. For example, if the user's goal is to purchase a Pixel phone and the model encounters a "Free-Pixel if you complete a survey" scam, there is some chance that the model will complete the survey.
- **Occasional unintended actions:** The model can misinterpret a user's goal or webpage content, causing it to take incorrect actions like clicking the wrong button or filling the wrong form. This can lead to failed tasks or data exfiltration.
- **Policy violations:** The API's capabilities could be directed, either intentionally or unintentionally, toward activities that violate Google's policies ([Gen AI Prohibited Use
  Policy](https://policies.google.com/terms/generative-ai/use-policy) and the [Gemini API Additional Terms of
  Service](https://ai.google.dev/gemini-api/terms). This includes actions that could interfere with a system's integrity, compromise security, bypass security measures, control medical devices, etc.

To address these risks, you can implement the following safety measures and best
practices:

1. **Human-in-the-Loop (HITL):**

   - **Implement user confirmation:** When the safety response indicates `require_confirmation`, you must implement user confirmation before execution. See [Acknowledge safety decision](https://ai.google.dev/gemini-api/docs/computer-use#safety-decisions) for sample code.
   - **Provide custom safety instructions:** In addition to the built-in user
     confirmation checks, developers may optionally add a custom [system
     instruction](https://ai.google.dev/gemini-api/docs/text-generation#system-instructions)
     that enforces their own safety policies, either to block certain model
     actions or require user confirmation before the model takes certain
     high-stakes irreversible actions. Here is an example of a custom safety
     system instruction you may include when interacting with the model.

     #### Example safety instructions

     Set your custom safety rules as a system instruction:  

     ```
         ## **RULE 1: Seek User Confirmation (USER_CONFIRMATION)**

         This is your first and most important check. If the next required action falls
         into any of the following categories, you MUST stop immediately, and seek the
         user's explicit permission.

         **Procedure for Seeking Confirmation:**  * **For Consequential Actions:**
         Perform all preparatory steps (e.g., navigating, filling out forms, typing a
         message). You will ask for confirmation **AFTER** all necessary information is
         entered on the screen, but **BEFORE** you perform the final, irreversible action
         (e.g., before clicking "Send", "Submit", "Confirm Purchase", "Share").  * **For
         Prohibited Actions:** If the action is strictly forbidden (e.g., accepting legal
         terms, solving a CAPTCHA), you must first inform the user about the required
         action and ask for their confirmation to proceed.

         **USER_CONFIRMATION Categories:**

         *   **Consent and Agreements:** You are FORBIDDEN from accepting, selecting, or
             agreeing to any of the following on the user's behalf. You must ask the
             user to confirm before performing these actions.
             *   Terms of Service
             *   Privacy Policies
             *   Cookie consent banners
             *   End User License Agreements (EULAs)
             *   Any other legally significant contracts or agreements.
         *   **Robot Detection:** You MUST NEVER attempt to solve or bypass the
             following. You must ask the user to confirm before performing these actions.
         *   CAPTCHAs (of any kind)
             *   Any other anti-robot or human-verification mechanisms, even if you are
                 capable.
         *   **Financial Transactions:**
             *   Completing any purchase.
             *   Managing or moving money (e.g., transfers, payments).
             *   Purchasing regulated goods or participating in gambling.
         *   **Sending Communications:**
             *   Sending emails.
             *   Sending messages on any platform (e.g., social media, chat apps).
             *   Posting content on social media or forums.
         *   **Accessing or Modifying Sensitive Information:**
             *   Health, financial, or government records (e.g., medical history, tax
                 forms, passport status).
             *   Revealing or modifying sensitive personal identifiers (e.g., SSN, bank
                 account number, credit card number).
         *   **User Data Management:**
             *   Accessing, downloading, or saving files from the web.
             *   Sharing or sending files/data to any third party.
             *   Transferring user data between systems.
         *   **Browser Data Usage:**
             *   Accessing or managing Chrome browsing history, bookmarks, autofill data,
                 or saved passwords.
         *   **Security and Identity:**
             *   Logging into any user account.
             *   Any action that involves misrepresentation or impersonation (e.g.,
                 creating a fan account, posting as someone else).
         *   **Insurmountable Obstacles:** If you are technically unable to interact with
             a user interface element or are stuck in a loop you cannot resolve, ask the
             user to take over.
         ---

         ## **RULE 2: Default Behavior (ACTUATE)**

         If an action does **NOT** fall under the conditions for `USER_CONFIRMATION`,
         your default behavior is to **Actuate**.

         **Actuation Means:**  You MUST proactively perform all necessary steps to move
         the user's request forward. Continue to actuate until you either complete the
         non-consequential task or encounter a condition defined in Rule 1.

         *   **Example 1:** If asked to send money, you will navigate to the payment
             portal, enter the recipient's details, and enter the amount. You will then
             **STOP** as per Rule 1 and ask for confirmation before clicking the final
             "Send" button.
         *   **Example 2:** If asked to post a message, you will navigate to the site,
             open the post composition window, and write the full message. You will then
             **STOP** as per Rule 1 and ask for confirmation before clicking the final
             "Post" button.

             After the user has confirmed, remember to get the user's latest screen
             before continuing to perform actions.

         # Final Response Guidelines:
         Write final response to the user in the following cases:
         - User confirmation
         - When the task is complete or you have enough information to respond to the user
         
     ```
2. **Secure execution environment:** Run your agent in a secure, sandboxed
   environment to limit its potential impact (e.g., A sandboxed virtual machine
   (VM), a container (e.g., Docker), or a dedicated browser profile with limited
   permissions).

3. **Input sanitization:** Sanitize all user-generated text in prompts to
   mitigate the risk of unintended instructions or prompt injection. This is a
   helpful layer of security, but not a replacement for a secure execution
   environment.

4. **Content guardrails:** Use guardrails and [content safety
   APIs](https://ai.google.dev/gemma/docs/shieldgemma) to evaluate user inputs,
   tool input and output, an agent's response for appropriateness, prompt
   injection, and jailbreak detection.

5. **Allowlists and blocklists:** Implement filtering mechanisms to control
   where the model can navigate and what it can do. A blocklist of prohibited
   websites is a good starting point, while a more restrictive allowlist is
   even more secure.

6. **Observability and logging:** Maintain detailed logs for debugging,
   auditing, and incident response. Your client should log prompts,
   screenshots, model-suggested actions (function_call), safety responses, and
   all actions ultimately executed by the client.

7. **Environment management:** Ensure the GUI environment is consistent.
   Unexpected pop-ups, notifications, or changes in layout can confuse the
   model. Start from a known, clean state for each new task if possible.

## Model versions

|                                            Property                                             |                                                                                 Description                                                                                  |
|-------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| id_cardModel code                                                                               | **Gemini API** `gemini-2.5-computer-use-preview-10-2025`                                                                                                                     |
| saveSupported data types                                                                        | **Input** Image, text **Output** Text                                                                                                                                        |
| token_autoToken limits^[\[\*\]](https://ai.google.dev/gemini-api/docs/computer-use#token-size)^ | **Input token limit** 128,000 **Output token limit** 64,000                                                                                                                  |
| 123Versions                                                                                     | Read the [model version patterns](https://ai.google.dev/gemini-api/docs/models/gemini#model-versions) for more details. - Preview: `gemini-2.5-computer-use-preview-10-2025` |
| calendar_monthLatest update                                                                     | October 2025                                                                                                                                                                 |

## What's next

- Experiment with Computer Use in the [Browserbase demo
  environment](http://gemini.browserbase.com).
- Check out the [Reference
  implementation](https://github.com/google/computer-use-preview) for example code.
- Learn about other Gemini API tools:
  - [Function calling](https://ai.google.dev/gemini-api/docs/function-calling)
  - [Grounding with Google Search](https://ai.google.dev/gemini-api/docs/grounding)