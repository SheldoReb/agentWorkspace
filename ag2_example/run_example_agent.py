"""AG2 (AutoGen) example that exposes the Jira MCP tool to the assistant agent.

The script keeps the lightweight single-file entry point introduced earlier while
restoring access to the Jira Model Context Protocol (MCP) server.  The assistant is
backed by Hugging Face's OpenAI-compatible router and can call the MCP tool whenever
the conversation requires project-tracking context.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from typing import Any, Mapping

from autogen import ConversableAgent

try:  # Prefer the autogen-agentchat distribution when available.
    from autogen.agentchat.contrib.mcp import MCPToolkit
except ModuleNotFoundError:  # pragma: no cover - import path varies per install
    try:
        from ag2.autogen.mcp import MCPToolkit
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "MCP toolkit helpers are unavailable. Install either `autogen-agentchat[mcp]>=0.2.0` "
            "or the AG2 package that exposes `ag2.autogen.mcp`."
        ) from exc


DEFAULT_PROMPT = "Summarise README.md and provide a short bulleted outline."
DEFAULT_JIRA_IMAGE = "ghcr.io/nguyenvanduocit/jira-mcp:latest"
DEFAULT_JIRA_RUNTIME = "podman"


def _build_llm_config() -> dict[str, Any]:
    """Return the LLM configuration used by the demo agent."""

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError(
            "HF_TOKEN environment variable is required to authenticate with the Hugging Face router. "
            "Create a token at https://huggingface.co/settings/tokens and export it before running the example."
        )

    return {
        "config_list": [
            {
                "model": "openai/gpt-oss-120b",
                "api_key": token,
                "base_url": "https://router.huggingface.co/v1",
            }
        ]
    }


def _load_env_file(env_file: pathlib.Path) -> Mapping[str, str]:
    """Parse key/value pairs from ``env_file`` while tolerating comments."""

    if not env_file.exists():
        raise RuntimeError(
            f"Unable to locate Jira credential file at {env_file!s}. Create one from "
            "ag2_example/jira.env.example and supply credentials for the MCP container."
        )

    env: dict[str, str] = {}
    for raw_line in env_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        key, sep, value = line.partition("=")
        if not sep:
            raise RuntimeError(f"Invalid line in {env_file!s}: {raw_line!r}")
        env[key.strip()] = value.strip()

    return env


def _build_jira_toolkit(
    env_file: pathlib.Path,
    runtime: str,
    image: str,
) -> MCPToolkit:
    """Return an MCP toolkit definition that launches the Jira container on demand."""

    env_overrides = _load_env_file(env_file)
    args: list[str] = ["run", "--rm", "-i", "--env-file", str(env_file), image]

    spec = {
        "name": "jira",
        "command": runtime,
        "args": args,
        "env": env_overrides,
    }

    if hasattr(MCPToolkit, "from_spec"):
        return MCPToolkit.from_spec(spec)  # type: ignore[attr-defined]

    return MCPToolkit(**spec)  # type: ignore[arg-type,call-arg]


def run_agent(prompt: str, jira_env: pathlib.Path, runtime: str, image: str) -> None:
    """Send ``prompt`` to the configured AG2 agent and print the response."""

    agent = ConversableAgent(
        name="assistant",
        system_message=(
            "You are a concise technical assistant. When possible, respond with bullet points and actionable summaries."
        ),
        llm_config=_build_llm_config(),
    )

    jira_toolkit = _build_jira_toolkit(jira_env, runtime, image)
    if hasattr(agent, "register_toolkit"):
        agent.register_toolkit(jira_toolkit)  # type: ignore[attr-defined]
    else:  # pragma: no cover - fallback for older AG2 builds
        agent.toolkits = getattr(agent, "toolkits", []) + [jira_toolkit]  # type: ignore[attr-defined]

    response = agent.generate_reply(messages=[{"role": "user", "content": prompt}])

    if isinstance(response, dict):
        content = response.get("content")
        if isinstance(content, list):
            # Messages can occasionally be returned as a list of chunks.
            text = "\n".join(chunk.get("text", "") for chunk in content if isinstance(chunk, dict))
        else:
            text = str(content)
    else:
        text = str(response)

    print(text.strip())


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the lightweight AG2 example agent.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default=DEFAULT_PROMPT,
        help="User prompt that will be forwarded to the AG2 agent.",
    )
    parser.add_argument(
        "--jira-env",
        default=pathlib.Path(__file__).with_name(".env"),
        type=pathlib.Path,
        help=(
            "Path to the environment file consumed by the Jira MCP container. Defaults to ag2_example/.env."
        ),
    )
    parser.add_argument(
        "--jira-runtime",
        default=DEFAULT_JIRA_RUNTIME,
        help="Container runtime used to start the Jira MCP server (e.g. podman or docker).",
    )
    parser.add_argument(
        "--jira-image",
        default=DEFAULT_JIRA_IMAGE,
        help="Container image that provides the Jira MCP server.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        run_agent(args.prompt, args.jira_env, args.jira_runtime, args.jira_image)
    except Exception as exc:  # noqa: BLE001 - surface rich error message
        parser.error(str(exc))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
