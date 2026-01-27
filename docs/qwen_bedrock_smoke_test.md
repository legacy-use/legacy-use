# Qwen Bedrock Computer Use Smoke Test

Prerequisites:
- AWS credentials with Bedrock access to `qwen.qwen3-vl-235b-a22b` in `eu-west-2`.
- App running with Settings UI reachable.

Checklist:
1) In Settings, select **Qwen (Bedrock)** and enter `access_key_id` + `secret_access_key`.
2) Confirm the provider shows as available and the region is fixed to `eu-west-2`.
3) Start a small computer-use job (e.g., open a browser and search for a simple query).
4) Verify the first model turn requests `computer` with action `screenshot`.
5) Verify subsequent turns request computer actions (click/type/scroll) and tool results return.
6) Verify the final turn uses the `extraction` tool and the job completes successfully.
