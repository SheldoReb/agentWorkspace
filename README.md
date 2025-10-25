# agentWorkspace

## Overview

This repository showcases a focused AutoGen setup that highlights how an assistant agent can combine
multiple tools while running entirely inside a container. The example located in
[`ag2_example/`](./ag2_example/):

* routes language-model traffic to Hugging Face's OpenAI-compatible endpoint,
* connects to a Jira Model Context Protocol (MCP) server as a stdio client so the agent can call Jira
  tools,
* exposes [markitdown](https://github.com/h2oai/markitdown) as a formatting helper, and
* executes arbitrary Python code inside short-lived Docker containers to support iterative development.

A Dockerfile is included so you can containerise the full runtime. Lightweight backend/frontend
scaffolding is still present if you want to extend the project beyond the AutoGen demo.

## Quick start

1. **Create a virtual environment and install dependencies**

   ```bash
   git clone <repo-url>
   cd agentWorkspace
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure credentials**

   * Export a Hugging Face token so the assistant can reach the inference router:

     ```bash
     export HF_TOKEN="hf_your_token_here"
     ```

   * Copy the Jira MCP template and populate the required environment variables:

     ```bash
     cp ag2_example/jira.env.example ag2_example/.env
     # Populate JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN
     ```

3. **Run the AutoGen agent**

   ```bash
   python ag2_example/run_example_agent.py --max-turns 8 "Summarise README.md in bullet points."
   ```

   The agent registers three tools—`jira_call_tool`, `render_with_markitdown`, and `execute_python`—and
   decides when to invoke each one while working towards a final answer. Jira tools can also be supplied
   via a JSON spec using `--jira-spec path/to/spec.json`.

4. **Containerised workflow (optional)**

   Build and run the provided Docker image when you want the entire stack to execute inside a
   container. Mount the Jira environment file and expose your host's container runtime so nested code
   execution can spawn additional containers:

   ```bash
   docker build -f ag2_example/Dockerfile -t ag2-autogen-agent .
   docker run --rm -it \
     -e HF_TOKEN=$HF_TOKEN \
     --env-file ag2_example/.env \
     -v $(pwd)/ag2_example/.env:/app/ag2_example/.env:ro \
     -v /var/run/docker.sock:/var/run/docker.sock \
     ag2-autogen-agent
   ```

## Project structure

```
backend/          # Flask microservice scaffold (unused by the AutoGen demo)
frontend/         # Static frontend starter
ag2_example/      # AutoGen example, Dockerfile, and documentation
requirements.txt  # Python dependencies shared across the project
```

## Further reading

* [AutoGen documentation](https://microsoft.github.io/autogen/stable/)
* [Model Context Protocol specification](https://modelcontextprotocol.io/)
* [markitdown project](https://github.com/h2oai/markitdown)
