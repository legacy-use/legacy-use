# Gemini Computer Use Integration Plan

## Context and Current Architecture
- The sampling loop stores message history in Anthropic `BetaMessageParam` format and always returns `BetaContentBlockParam` blocks to the loop.
- Provider handlers implement a strict interface in `server/computer_use/handlers/base.py` to:
  - Convert message history to provider format.
  - Prepare tool definitions per provider.
  - Invoke the provider API.
  - Convert provider responses back to internal tool-use blocks.
- Tooling is centralized in `server/computer_use/tools/` and grouped by version in `server/computer_use/tools/groups.py`:
  - `computer` (actions like left_click, type, scroll, etc.)
  - `extraction`
  - `ui_not_as_expected`
  - `custom_action`
- OpenAI and Anthropic handlers show the expected patterns for tool conversion, message conversion, and response normalization.
- Gemini computer use requires:
  - `computer_use` tool with optional excluded actions.
  - Custom user-defined functions for actions not in the predefined Gemini tool set.
- Gemini SDK supports async calls via `genai.Client(...).aio.models.generate_content`, so handler logic can stay fully async.
- Gemini models can return `thoughtSignature` metadata in content parts; if we convert responses into internal history, we must preserve and return these signatures on subsequent function calls.

## Gemini Tool Mapping Strategy
### Built-in Gemini actions to keep (mapped to internal `computer` actions)
- `click_at` -> `left_click` (denormalize coordinates)
- `hover_at` -> `mouse_move` (denormalize coordinates)
- `type_text_at` -> `left_click` + `type` (+ optional `key` for enter)
- `key_combination` -> `key` (normalize key combos)
- `scroll_document` -> `scroll` (default magnitude)
- `scroll_at` -> `scroll` (use `magnitude` if provided)
- `drag_and_drop` -> `mouse_move` + `left_click_drag` (start/destination)
- `wait_5_seconds` -> `wait` (duration=5)

### Gemini actions to exclude (not supported by internal tooling)
- `open_web_browser`
- `search`
- `navigate`
- `go_back`
- `go_forward`

### Custom Gemini functions to add (map to internal `computer` actions)
- `screenshot`
- `type_text` (text-only typing without coordinates)
- `right_click`
- `middle_click`
- `double_click`
- `triple_click`
- `left_mouse_down`
- `left_mouse_up`
- `hold_key`

These custom functions will be defined as Gemini `function_declarations` and converted to internal tool uses.

## Implementation Steps
1. **Provider Configuration**
   - Add `GEMINI` to `APIProvider` and default model mapping in `server/computer_use/config.py`.
   - Add tenant setting for Gemini API key (e.g., `GEMINI_API_KEY` or `GOOGLE_GENAI_API_KEY`) in `server/settings_tenant.py`.
   - Expose Gemini in `server/routes/settings.py` provider list and update endpoint.
   - Ensure `server/settings.py` includes the relevant API key and defaults (match existing patterns).

2. **Gemini Handler Skeleton**
   - Create `server/computer_use/handlers/gemini/handler.py`, `message_converter.py`, `response_converter.py`.
   - Follow OpenAI/Anthropic handler structure and keep other handlers unchanged.
   - Initialize a `genai.Client(http_options=HttpOptions(api_version="v1"))` and use `await client.aio.models.generate_content(...)` for async execution.

3. **Tool Preparation**
   - Build `GenerateContentConfig` with:
     - `types.Tool(computer_use=types.ComputerUse(...))` including excluded Gemini actions.
     - `types.Tool(function_declarations=[...])` for custom actions.
   - Capture display width/height from the `computer` tool to denormalize coordinates.

4. **Message Conversion (Internal -> Gemini)**
   - Convert `BetaMessageParam` history to Gemini `Content` list:
     - User text -> `Part(text=...)`.
     - Tool results -> `Part(function_response=...)` with optional inline image.
     - Assistant tool calls -> `Part(function_call=...)` mapped to Gemini function names.
   - Maintain a `tool_use_id -> function name` mapping to correctly form `FunctionResponse` entries.
   - Preserve `thoughtSignature` fields on assistant function_call parts by storing them in internal content blocks and re-emitting them verbatim in Gemini `Part(function_call=...)`.

5. **Response Conversion (Gemini -> Internal)**
   - Parse Gemini `function_call` parts into `BetaToolUseBlockParam` blocks.
   - Apply tool/action mappings, including coordinate denormalization and key normalization.
   - Emit multiple internal tool uses when a single Gemini action expands to multiple steps (e.g., type_text_at -> click + type [+ key]).
   - Map Gemini stop reason to internal `stop_reason` (default `tool_use` or `end_turn` based on content).
   - Capture any `thoughtSignature` returned with function calls and attach it to the corresponding internal tool_use block for later reuse.

6. **Telemetry + Error Handling**
   - Capture AI generation metadata when Gemini response exposes usage metrics.
   - Return safe defaults for request/response objects when raw HTTP isn’t available (match OpenCUA pattern).

7. **Wiring and Registry**
   - Register Gemini handler in `server/computer_use/handlers/registry.py`.
   - Ensure `validate_provider` and provider selection in `server/core.py` work with Gemini.

8. **Verification Plan**
   - Add targeted unit tests for conversion logic (optional if testing setup exists).
   - Manual sanity checks:
     - Build request, ensure Gemini tool list includes correct exclusions and custom functions.
     - Confirm tool calls map correctly to internal `computer` actions.
     - Validate screenshots return as tool results in Gemini function responses.

## Risks / Open Questions
- Decide on exact tenant setting key (`GEMINI_API_KEY` vs `GOOGLE_GENAI_API_KEY`) to match existing settings and UI.
- Confirm Gemini’s function_call response structure to generate stable tool_use IDs.
- Decide default scroll magnitude and how to handle `clear_before_typing` if Gemini sets it.
- Confirm how the SDK surfaces thought signatures (`thoughtSignature` vs `thought_signature`) and ensure we persist and replay them in the exact field/location required by Gemini.
