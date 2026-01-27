---
name: qwen-bedrock-handler
overview: Add Qwen3-VL as a new Computer Use provider backed by Amazon Bedrock (region forced to eu-west-2), following the existing handler/message_converter/response_converter pattern and without changing any other provider handler logic.
todos:
  - id: add-provider-enum
    content: Add APIProvider.QWEN_BEDROCK + default model mapping in `server/computer_use/config.py`.
    status: completed
  - id: implement-qwen-handler
    content: Create `server/computer_use/handlers/qwen/{handler,message_converter,response_converter}.py` using Bedrock Converse, forced region eu-west-2, and Beta-format conversions.
    status: completed
  - id: register-handler
    content: Register `QWEN_BEDROCK` in `server/computer_use/handlers/registry.py` without changing existing mappings.
    status: completed
  - id: settings-provider
    content: Expose and configure the new provider in `server/routes/settings.py` with required AWS credentials and forced region eu-west-2.
    status: completed
  - id: tests-smoke
    content: Add minimal unit tests for converters + a manual Bedrock smoke test checklist.
    status: completed
isProject: false
---

# Integrate Qwen3-VL on Bedrock (Computer Use)

## Goals & constraints

- **Goal**: Add a **new provider** `qwen_bedrock` that can run Computer Use jobs using **Amazon Bedrock** model **`qwen.qwen3-vl-235b-a22b`**, using the same internal Anthropic Beta message/tool format used by the sampling loop.
- **Hard constraints**:
- **Do not change behavior** of existing handlers (`anthropic`, `openai`, `gemini`, `opencua`).
- **Force Bedrock region to `eu-west-2`** for this provider (ignore tenant `AWS_REGION`).
- Keep diffs minimal and localized.

## Where this plugs in (current architecture)

- The sampling loop selects a handler via the registry:
- [`/Users/thiloreintjes/Documents/legacy-use/server/computer_use/handlers/registry.py`](/Users/thiloreintjes/Documents/legacy-use/server/computer_use/handlers/registry.py) maps `APIProvider -> Handler`.
- Provider options & credential forms come from:
- [`/Users/thiloreintjes/Documents/legacy-use/server/routes/settings.py`](/Users/thiloreintjes/Documents/legacy-use/server/routes/settings.py)
- Provider enum + default model comes from:
- [`/Users/thiloreintjes/Documents/legacy-use/server/computer_use/config.py`](/Users/thiloreintjes/Documents/legacy-use/server/computer_use/config.py)

## Implementation approach

### 1) Add a new provider enum + default model

- Update [`/Users/thiloreintjes/Documents/legacy-use/server/computer_use/config.py`](/Users/thiloreintjes/Documents/legacy-use/server/computer_use/config.py)
- Add `APIProvider.QWEN_BEDROCK = 'qwen_bedrock'`.
- Add `PROVIDER_TO_DEFAULT_MODEL_NAME[APIProvider.QWEN_BEDROCK] = 'qwen.qwen3-vl-235b-a22b'`.

### 2) Implement a new handler following existing patterns

Create a new handler folder (avoid hyphens in module names):

- [`/Users/thiloreintjes/Documents/legacy-use/server/computer_use/handlers/qwen/handler.py`](/Users/thiloreintjes/Documents/legacy-use/server/computer_use/handlers/qwen/handler.py)
- [`/Users/thiloreintjes/Documents/legacy-use/server/computer_use/handlers/qwen/message_converter.py`](/Users/thiloreintjes/Documents/legacy-use/server/computer_use/handlers/qwen/message_converter.py)
- [`/Users/thiloreintjes/Documents/legacy-use/server/computer_use/handlers/qwen/response_converter.py`](/Users/thiloreintjes/Documents/legacy-use/server/computer_use/handlers/qwen/response_converter.py)

Handler responsibilities (match the `ProviderHandler` protocol in [`handlers/base.py`](/Users/thiloreintjes/Documents/legacy-use/server/computer_use/handlers/base.py)):

- **Client**: Use `aioboto3` to create a `bedrock-runtime` client with `region_name='eu-west-2'` and sensible timeouts/retries.
- **API call**: Use **Bedrock Runtime Converse** (`client.converse(...)`) with:
- `modelId=model`
- `system=[{'text': system_prompt}]`
- `messages=[{role, content:[...]}]`
- `toolConfig={tools:[{toolSpec:{name, description, inputSchema:{json:...}}}...]}`
- `inferenceConfig={'maxTokens': max_tokens, 'temperature': temperature}`
- **Tool schema mapping**:
- For most tools: use each tool’s `internal_spec()` (`name`, `description`, `input_schema`) and map directly to Bedrock `toolSpec`.
- For the `computer` tool: expand into per-action tool specs (same approach as OpenAI), so the model can call `screenshot`, `left_click`, `type`, etc as separate tools. This avoids needing a nested “actions” schema (Bedrock tools want JSON Schema per tool).
- **Message mapping (Anthropic Beta ↔ Bedrock Converse)**:
- `text` blocks map to `{text: ...}`.
- Assistant `tool_use` blocks map to `{toolUse:{toolUseId, name, input}}`.
- User `tool_result` blocks map to `{toolResult:{toolUseId, content:[...], status:'success'|'error'}}`.
- Screenshot images in tool results: decode our base64 PNG and pass as Bedrock image blocks in the user message content.
- If Qwen rejects images inside `toolResult.content`, use a safe fallback encoding: send `toolResult` with text/json only, and append the screenshot as a separate `{image:{...}}` content block in the same user message.
- **Response conversion**:
- Convert Bedrock `output.message.content[]` to internal `BetaContentBlockParam[]` (text + tool_use).
- Normalize computer action calls so they become a single internal `computer` tool with `input.action=<action>` (same semantics as the rest of the system).
- Map Bedrock `stopReason` to existing sampling-loop values (`end_turn`, `tool_use`, `max_tokens`, …).
- **HTTP exchange logging compatibility**:
- Wrap the Bedrock request/response into `httpx.Request`/`httpx.Response` objects (similar to `LegacyUseClient`) so existing logging/token-limit code can record exchanges uniformly.

### 3) Register the new handler

- Update [`/Users/thiloreintjes/Documents/legacy-use/server/computer_use/handlers/registry.py`](/Users/thiloreintjes/Documents/legacy-use/server/computer_use/handlers/registry.py)
- Import the new handler.
- Add `APIProvider.QWEN_BEDROCK: QwenBedrockHandler` to `HANDLER_REGISTRY`.
- Leave existing provider mappings untouched.

### 4) Expose the provider in settings + credential handling

- Update [`/Users/thiloreintjes/Documents/legacy-use/server/routes/settings.py`](/Users/thiloreintjes/Documents/legacy-use/server/routes/settings.py)
- Add a provider entry for `qwen_bedrock` with:
- `name`: “Qwen (Bedrock)”
- `description`: mention **Qwen3-VL via Bedrock Converse; region fixed to eu-west-2**
- `default_model`: from `get_default_model_name(APIProvider.QWEN_BEDROCK)`
- `credentials`: **only** `access_key_id`, `secret_access_key` (no `region`, because the frontend requires all listed keys)
- `available`: true if the required AWS keys exist.
- In the POST `/settings/providers` handler:
- Add a new `elif provider_enum == APIProvider.QWEN_BEDROCK:` branch.
- Require `access_key_id` + `secret_access_key`.
- Persist them in tenant settings (reuse existing `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`).
- Set `AWS_REGION` to **`eu-west-2`** (forced).
- Set `API_PROVIDER` to `qwen_bedrock`.

## Validation / test plan

- **Unit tests (no network)**
- Add focused tests that:
- Convert internal messages with tool_use/tool_result(+image) into Bedrock message format.
- Convert Bedrock toolUse blocks into internal `tool_use` blocks (including computer action normalization).
- Convert Bedrock stop reasons.
- Mock the bedrock client response dict rather than calling AWS.
- **Manual smoke test (with AWS creds)**
- Configure “Qwen (Bedrock)” in the Settings UI.
- Run a small job and confirm:
- First model turn requests `screenshot`.
- Subsequent turns request computer actions.
- Final result uses the `extraction` tool and the job completes.

## Notes / external references

- Bedrock Converse + tool use reference (request/response shapes):
- `https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html`
- `https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use-inference-call.html`
- AWS-supported model list shows `qwen.qwen3-vl-235b-a22b` supports Text+Image input (verify access in your account/region):
- `https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html`
