# AG2 Quickstart Example

This directory contains a lightweight [AG2 (AutoGen)](https://ag2.ai/) example that calls the
`openai/gpt-oss-120b` chat completion model hosted on the Hugging Face Inference Router and talks to
the Jira Model Context Protocol (MCP) server through a bespoke JSON-RPC bridge. The entry point
[`run_example_agent.py`](./run_example_agent.py) automatically launches the Jira MCP container when
the agent requests Jira-related context.

## Quickstart

1. Create and activate a Python 3.11+ virtual environment.
2. Install the Python dependencies listed in [`requirements.txt`](../requirements.txt):

   ```bash
   pip install -r requirements.txt
   ```

3. Export a Hugging Face API token (create one from the
   [Hugging Face settings page](https://huggingface.co/settings/tokens)):

   ```bash
   export HF_TOKEN="hf_your_token_here"
   ```

4. Configure Jira credentials for the MCP container:

   ```bash
   cp ag2_example/jira.env.example ag2_example/.env
   # Populate JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN
   ```

5. Run the example agent and pass an optional prompt:

   ```bash
   python ag2_example/run_example_agent.py "Summarise README.md and provide a short bulleted outline."
   ```

The script constructs a single `ConversableAgent` with an AutoGen configuration that targets the
OpenAI-compatible Hugging Face endpoint, registers a `jira_call_tool` function backed by the
JSON-RPC client, and prints the model's reply to the console.

## Sanity Check

If you would like to verify your Hugging Face token separately, you can issue a direct request with
the OpenAI client included in `requirements.txt`:

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=os.environ["HF_TOKEN"],
)

response = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[{"role": "user", "content": "Why is the sky blue?"}],
)

print(response.choices[0].message.content)
```

## Jira MCP Notes

* The script defaults to the `podman` runtime. Pass `--jira-runtime docker` if you prefer Docker.
* If you need to tweak container arguments (for example to mount a certificate bundle), you can
  edit [`run_example_agent.py`](./run_example_agent.py) and update `_build_jira_client`.
* To debug the MCP server separately, reuse the command surfaced in
  [`jira.env.example`](./jira.env.example) with

  ```bash
  npx @modelcontextprotocol/inspector podman run --rm -i --env-file ag2_example/.env ghcr.io/nguyenvanduocit/jira-mcp:latest
  ```

  Save the inspector's JSON `clientConfig` (or the spec emitted by your existing runtime tooling) to
  a file and pass it to the demo with `--jira-spec path/to/spec.json`. When a spec is supplied the
  agent skips assembling the default container command and instead reuses the JSON payload. The
  format must describe a `stdio` transport so the script can spawn the process locally; for example:

  ```json
  {
    "name": "jira",
    "command": "podman",
    "args": ["run", "--rm", "-i", "--env-file", "ag2_example/.env", "ghcr.io/nguyenvanduocit/jira-mcp:latest"],
    "env": {
      "JIRA_BASE_URL": "https://your-instance.atlassian.net",
      "JIRA_EMAIL": "you@example.com",
      "JIRA_API_TOKEN": "your_api_token"
    }
  }
  ```

  Specifications exported by other MCP tooling—such as the inspector's WebSocket client config—need
  to be converted to a stdio command before they can be consumed by this example. The demo focuses on
  local transports and avoids the `MCPToolkit` dependency entirely.
