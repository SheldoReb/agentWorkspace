# agentWorkspace

## Overview

This repository demonstrates a lightweight integration of the [AG2 (AutoGen)](https://ag2.ai/) agent
framework. The `ag2_example` folder contains a single-file script that:

* calls the Hugging Face hosted `openai/gpt-oss-120b` model through the OpenAI compatible API,
* launches the Jira Model Context Protocol (MCP) container so the assistant can reason over Jira
  data, and
* prints the model's response directly to your terminal.

A minimal Flask backend and static frontend scaffold remain available should you want to build on top
of them.

## Quick Start

1. **Clone the repository and create a virtual environment**

   ```bash
   git clone <repo-url>
   cd agentWorkspace
   python -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies**

   Install the Python packages required by the AG2 example (including the MCP extras):

   ```bash
   pip install -r requirements.txt
   ```

   If you prefer installing AG2 directly from its repository, ensure it exposes the
   `ag2.autogen.mcp` module so the Jira toolkit import succeeds.

3. **Provide credentials for external services**

   * Export a Hugging Face token so the assistant can access the inference router:

     ```bash
     export HF_TOKEN="hf_your_token_here"
     ```

   * Copy the Jira MCP template and fill in the required fields:

     ```bash
     cp ag2_example/jira.env.example ag2_example/.env
     # Populate JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN
     ```

4. **Run the AG2 example agent**

   ```bash
   python ag2_example/run_example_agent.py "Summarise README.md and provide a short bulleted outline."
   ```

   The script constructs a `ConversableAgent` from AG2, attaches the Jira MCP toolkit, forwards your
   prompt to Hugging Face's OpenAI-compatible endpoint, and prints the model's reply. If you prefer
   to run the Jira MCP server independently (for example while debugging with the MCP Inspector),
   export the server specification to JSON and point the demo at it with `--jira-spec path/to/spec.json`.

## Project Structure

```
backend/          # Flask microservice used by the demo
frontend/         # Static frontend assets
ag2_example/      # Minimal AG2 example script and documentation
requirements.txt  # Python dependencies shared across the project
```

## Additional Resources

* [AG2 documentation](https://ag2.ai/)
* [Hugging Face Inference Router](https://huggingface.co/inference-api)
