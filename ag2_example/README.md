# AG2 Example Agent

This directory contains a minimal [AG2](https://ag2.ai/) project that demonstrates how to wire up:

* the Hugging Face hosted `openai/gpt-oss-120b` chat completion model through the OpenAI compatible API,
* the built-in Docker based code execution sandbox,
* the [markItDown](https://github.com/Significant-Gravitas/markitdown) Model Context Protocol (MCP) server for rich document to Markdown conversion, and
* a [Jira MCP server](https://github.com/nguyenvanduocit/jira-mcp) running inside Podman for querying projects and issues.

## Project Layout

```
ag2_example/
├── README.md              # This file
├── agent_app.yaml         # Declarative AG2 application definition
├── run_example_agent.py   # Python entrypoint that launches a sample AG2 task
└── mcp/
    ├── jira.json         # Optional MCP descriptor mirroring the Jira configuration
    └── markitdown.json    # Optional MCP client descriptor for markItDown (useful for external tooling)
```

## Prerequisites

1. Install system dependencies (Docker, Python 3.11+, and `uv`/`pip`).
2. Install the Python packages listed in [`requirements.txt`](../requirements.txt):

   ```bash
   pip install -r requirements.txt
   ```

3. Install the AG2 runtime. Until a PyPI distribution is available you can install it directly from the upstream repository:

   ```bash
   pip install "ag2 @ git+https://github.com/ag2ai/ag2.git"
   ```

   Confirm that the package was installed correctly:

   ```bash
   python -c "import ag2; print(getattr(ag2, '__version__', 'unknown'))"
   ```

4. Provide an API token for the Hugging Face Inference Router via the `HF_TOKEN` environment variable. You can generate a token from the [Hugging Face settings page](https://huggingface.co/settings/tokens).

5. Ensure Docker is running locally so the AG2 Docker tool can start ephemeral containers.

6. Install the `markitdown` MCP server. The server is distributed as a Python package so it can be installed directly:

   ```bash
   pip install markitdown
   ```

7. Install [Podman](https://podman.io/) (or ensure it is already available). The Jira MCP server is distributed as a container
   image and the AG2 configuration shells out to Podman to start it.

8. Provide Jira credentials. Copy `ag2_example/.env.jira.example` to `ag2_example/.env.jira` and populate the variables as
   documented by the Jira MCP server, or point the `JIRA_MCP_ENV_FILE` environment variable to an existing credentials file.

9. (Optional) Verify that your Hugging Face token works by issuing a simple chat completion request against the
   `openai/gpt-oss-120b` model:

   ```python
   import os
   from openai import OpenAI

   client = OpenAI(
       base_url="https://router.huggingface.co/v1",
       api_key=os.environ["HF_TOKEN"],
   )

   response = client.chat.completions.create(
       model="openai/gpt-oss-120b",
       messages=[{"role": "user", "content": "Why is the sky blue"}],
   )

   print(response.choices[0].message.content)
   ```

## Running the Example Agent

The declarative configuration in `agent_app.yaml` is consumed by the AG2 runtime. The helper script `run_example_agent.py` loads the configuration and invokes the agent with a test task, while AG2 automatically provisions the Docker sandbox along with the markItDown and Jira MCP servers described in the configuration.

```bash
export HF_TOKEN="hf_your_token_here"
# Optional: override the Jira MCP env file lookup
# export JIRA_MCP_ENV_FILE="$PWD/ag2_example/.env"
python ag2_example/run_example_agent.py "Summarise the README.md file and return Markdown"
```

When executed, the agent will:

1. Spin up a Docker sandbox using the AG2 Docker tool.
2. Forward the user prompt to the Hugging Face hosted `openai/gpt-oss-120b` model via the OpenAI compatible API endpoint.
3. Use the markItDown MCP server to transform rich content to Markdown when needed.
4. Query the Jira MCP server for project data when requested.
5. Print the final response (and any intermediate tool logs) to the console.

### Inspecting the Jira MCP server

The repository includes an MCP descriptor (`mcp/jira.json`) that mirrors the configuration used by AG2. You can inspect the server independently with the Model Context Protocol inspector:

```bash
npx @modelcontextprotocol/inspector podman run --rm -i \
  --env-file ag2_example/.env.jira \
  ghcr.io/nguyenvanduocit/jira-mcp:latest
```

## Customising the Agent

* Update `agent_app.yaml` to change the default model, prompts, or tool configuration.
* Pass a different user prompt as a command-line argument to `run_example_agent.py`.
* Extend the `tools` section inside `agent_app.yaml` to add additional AG2 tools or custom MCP servers, or adjust the
  markItDown and Jira tool definitions to point at different deployments.

Refer to the official [AG2 documentation](https://ag2.ai/docs) for more details on advanced configuration and orchestration patterns.
