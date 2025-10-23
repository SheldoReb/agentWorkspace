"""AG2 (AutoGen) example that exposes the Jira MCP tool to the assistant agent.

The script keeps the lightweight single-file entry point introduced earlier while
restoring access to the Jira Model Context Protocol (MCP) server.  The assistant is
backed by Hugging Face's OpenAI-compatible router and can call the MCP tool whenever
the conversation requires project-tracking context.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import pathlib
import sys
from typing import Any, Mapping, MutableMapping

from autogen import ConversableAgent


def _resolve_mcp_toolkit() -> type:
    """Return the MCP toolkit class regardless of installation layout."""

    candidates = (
        ("autogen.agentchat.contrib.mcp", "MCPToolkit"),
        ("autogen.agentchat.mcp", "MCPToolkit"),
        ("ag2.autogen.mcp", "MCPToolkit"),
        ("ag2.autogen.mcp.toolkit", "MCPToolkit"),
        ("ag2.autogen.agentchat.contrib.mcp", "MCPToolkit"),
    )

    errors: list[str] = []
    for module_name, attr_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:  # pragma: no cover - layout specific
            errors.append(f"{module_name}: {exc}")
            continue
        except ImportError as exc:  # pragma: no cover - attr missing on package
            errors.append(f"{module_name}: {exc}")
            continue

        try:
            return getattr(module, attr_name)
        except AttributeError as exc:
            errors.append(f"{module_name}.{attr_name}: {exc}")
            continue

    raise ModuleNotFoundError(
        "Unable to locate MCPToolkit. Install `autogen-agentchat[mcp]>=0.2.0` or an AG2 build that "
        "exposes the MCP helpers. Tried: " + ", ".join(errors)
    )


MCPToolkit = _resolve_mcp_toolkit()


DEFAULT_PROMPT = "Summarise README.md and provide a short bulleted outline."
DEFAULT_JIRA_IMAGE = "ghcr.io/nguyenvanduocit/jira-mcp:latest"
DEFAULT_JIRA_RUNTIME = "podman"
DEFAULT_JIRA_NAME = "jira"


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


def _load_tool_spec(spec_path: pathlib.Path) -> MutableMapping[str, Any]:
    """Load a JSON MCP specification from ``spec_path``."""

    if not spec_path.exists():
        raise RuntimeError(f"Unable to locate Jira MCP spec at {spec_path!s}.")

    try:
        loaded = json.loads(spec_path.read_text())
    except json.JSONDecodeError as exc:  # pragma: no cover - validation branch
        raise RuntimeError(f"Failed to parse MCP spec JSON: {exc}") from exc

    if not isinstance(loaded, MutableMapping):
        raise RuntimeError("MCP spec must decode to a JSON object.")

    return loaded


def _instantiate_toolkit(spec: MutableMapping[str, Any]) -> MCPToolkit:
    """Instantiate ``MCPToolkit`` from ``spec`` across API variants."""

    if hasattr(MCPToolkit, "from_spec") and callable(getattr(MCPToolkit, "from_spec")):
        return MCPToolkit.from_spec(spec)  # type: ignore[attr-defined]

    if hasattr(MCPToolkit, "from_dict") and callable(getattr(MCPToolkit, "from_dict")):
        return MCPToolkit.from_dict(spec)  # type: ignore[attr-defined]

    try:
        signature = inspect.signature(MCPToolkit)
    except (TypeError, ValueError):  # pragma: no cover - builtins or C extensions
        signature = None

    if signature is not None:
        parameters = signature.parameters

        if "spec" in parameters:
            name = spec.get("name", DEFAULT_JIRA_NAME)
            payload = spec.get("spec")
            if not isinstance(payload, MutableMapping):
                payload = {key: value for key, value in spec.items() if key != "name"}
            return MCPToolkit(name=name, spec=payload)  # type: ignore[call-arg]

    return MCPToolkit(**spec)  # type: ignore[arg-type,call-arg]


def _build_jira_toolkit(
    env_file: pathlib.Path,
    runtime: str,
    image: str,
    spec_path: pathlib.Path | None,
) -> MCPToolkit:
    """Return an MCP toolkit definition that launches the Jira container on demand."""

    if spec_path is not None:
        spec = _load_tool_spec(spec_path)
        spec.setdefault("name", DEFAULT_JIRA_NAME)
        return _instantiate_toolkit(spec)

    env_overrides = _load_env_file(env_file)
    args: list[str] = ["run", "--rm", "-i", "--env-file", str(env_file), image]

    spec: MutableMapping[str, Any] = {
        "name": DEFAULT_JIRA_NAME,
        "command": runtime,
        "args": args,
        "env": env_overrides,
    }

    return _instantiate_toolkit(spec)


def run_agent(
    prompt: str,
    jira_env: pathlib.Path,
    runtime: str,
    image: str,
    spec_path: pathlib.Path | None,
) -> None:
    """Send ``prompt`` to the configured AG2 agent and print the response."""

    agent = ConversableAgent(
        name="assistant",
        system_message=(
            "You are a concise technical assistant. When possible, respond with bullet points and actionable summaries."
        ),
        llm_config=_build_llm_config(),
    )

    jira_toolkit = _build_jira_toolkit(jira_env, runtime, image, spec_path)
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
    parser.add_argument(
        "--jira-spec",
        type=pathlib.Path,
        default=None,
        help=(
            "Optional path to a JSON MCP toolkit specification. When provided the script connects to the existing "
            "server described by the spec instead of spawning the container runtime."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        run_agent(args.prompt, args.jira_env, args.jira_runtime, args.jira_image, args.jira_spec)
    except Exception as exc:  # noqa: BLE001 - surface rich error message
        parser.error(str(exc))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
