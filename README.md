# agentWorkspace

## Overview

This repository showcases how to integrate the [AG2](https://ag2.ai/) agent framework inside a simple project. It now ships with an
end-to-end example agent that:

* calls the Hugging Face hosted `openai/gpt-oss-120b` model through the OpenAI compatible API using the `openai` Python client.
* executes Python snippets safely inside an ephemeral Docker container.
* interacts with the `markitdown` Model Context Protocol (MCP) server for document normalisation.
* connects to a Jira MCP server (running inside Podman) for project and issue information.

In addition to the AG2 example, the repository still provides a lightweight Flask backend and static frontend scaffold that you can extend as needed.

## Quick Start

1. **Clone the repository and create a virtual environment**

   ```bash
   git clone <repo-url>
   cd agentWorkspace
   python -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Provide credentials for the Hugging Face Inference Router**

   ```bash
   export HF_TOKEN="hf_your_token_here"
   ```

4. **Provide credentials for the Jira MCP server**

   Copy your Jira MCP `.env` file into `ag2_example/.env.jira` (or point `JIRA_MCP_ENV_FILE` at your own file). The file is not
   tracked in git because it contains secrets. A template is provided at `ag2_example/.env.jira.example` with the required
   variables.

5. **Run the AG2 example agent**

   ```bash
   python ag2_example/run_example_agent.py "Use markItDown to convert the README to Markdown and summarise it"
   ```

   The script loads the declarative AG2 configuration from `ag2_example/agent_app.yaml` and runs the task. AG2 automatically
   provisions the Docker sandbox, the markItDown MCP server, and the Jira MCP server described in the configuration, and the
   final Markdown response is printed to the console.

## Project Structure

```
backend/          # Flask microservice used by the demo
frontend/         # Static frontend assets
ag2_example/      # AG2 application, tools, and helper script
requirements.txt  # Python dependencies shared across the project
```

## Additional Resources

* [AG2 documentation](https://ag2.ai/)
* [markItDown MCP server](https://github.com/Significant-Gravitas/markitdown)
* [Jira MCP server container](https://github.com/nguyenvanduocit/jira-mcp)
* [Hugging Face Inference Router](https://huggingface.co/inference-api)
