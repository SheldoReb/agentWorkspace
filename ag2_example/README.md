# AutoGen Jira MCP Example

This directory contains an [AutoGen](https://microsoft.github.io/autogen/stable/) sample that wires a
single assistant agent to three complementary tools:

* **Jira MCP** – connect to the Jira Model Context Protocol server over stdio and expose every tool to
  the language model via a `jira_call_tool` function.
* **markitdown** – convert rich text (HTML, Markdown, plain text) into Markdown through the Python API.
* **Docker code execution** – run arbitrary Python snippets in ephemeral containers so the agent can
  draft, execute, and iterate on code safely.

The entry point [`run_example_agent.py`](./run_example_agent.py) can either spawn the Jira MCP
container itself or consume a pre-generated stdio specification. It also registers the markitdown and
code execution helpers as AutoGen tools, enabling the model to decide when each capability should be
invoked.

## Prerequisites

* Python 3.11+
* A working Docker or Podman installation that the agent can reach. Docker is used by default; pass
  `--jira-runtime podman --code-runtime podman` if you prefer Podman.
* An environment file that provides Jira credentials for the MCP container. Start with
  [`jira.env.example`](./jira.env.example).
* A Hugging Face token with access to the Inference Router saved in `HF_TOKEN`.

## Local quick start

1. Create a virtual environment and install the dependencies from
   [`requirements.txt`](../requirements.txt):

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Configure Jira credentials for the MCP runtime:

   ```bash
   cp ag2_example/jira.env.example ag2_example/.env
   # Populate JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN
   ```

3. Export the Hugging Face token that will be used for LLM calls:

   ```bash
   export HF_TOKEN="hf_your_token_here"
   ```

4. Run the demo and optionally override the container runtime or maximum number of automated turns:

   ```bash
   python ag2_example/run_example_agent.py --max-turns 8 "Summarise README.md in bullet points."
   ```

   The assistant will call `jira_call_tool`, `render_with_markitdown`, and `execute_python` as needed
   during the conversation. Tool responses are streamed back into the chat history so the model can
   iterate on its plan before producing the final answer.

5. To attach to an already described Jira MCP server, export the inspector's stdio specification to a
   JSON file and provide it via `--jira-spec path/to/spec.json`. When a spec is supplied the launcher
   skips assembling the default container command.

## Running inside Docker

A dedicated Dockerfile is provided so the entire stack can run inside a container. Build the image from
repo root:

```bash
docker build -f ag2_example/Dockerfile -t ag2-autogen-agent .
```

Launch the agent by mounting the Jira environment file and exposing your host container runtime. The
example below assumes Docker; adjust the volume mounts if you rely on Podman or a remote socket:

```bash
docker run --rm -it \
  -e HF_TOKEN=$HF_TOKEN \
  --env-file ag2_example/.env \
  -v $(pwd)/ag2_example/.env:/app/ag2_example/.env:ro \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ag2-autogen-agent \
  --max-turns 8
```

The container executes `python -m ag2_example.run_example_agent` by default, so any CLI flags can be
appended directly to the `docker run` command. Mounting the Docker socket gives the in-container agent
permission to launch additional containers for code execution. If you prefer an alternate runtime,
bind the appropriate socket and set `--code-runtime` accordingly.

## Hugging Face sanity check

You can validate that your Hugging Face credentials work before running the agent with the bundled
OpenAI-compatible client:

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

## Jira MCP notes

* The default Jira runtime is Docker. Override `--jira-runtime` if you prefer Podman or another
  container engine.
* Specifications exported by inspector and other tooling must describe a `stdio` transport so the
  launcher can spawn the process locally.
* Tool metadata returned by the `tools/list` RPC is surfaced to the language model inside the system
  prompt. Ensure your Jira MCP server exposes helpful descriptions to get the best results.
