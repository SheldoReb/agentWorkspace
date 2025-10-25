"""AG2 (AutoGen) example that exposes the Jira MCP server without the MCPToolkit.

The script keeps the lightweight single-file entry point while talking to the Jira
Model Context Protocol (MCP) server through a tiny JSON-RPC bridge instead of the
`MCPToolkit` helpers.  The assistant still relies on Hugging Face's
OpenAI-compatible router and calls the MCP server whenever the conversation
requires project-tracking context.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import pathlib
import subprocess
import sys
import threading
from collections import deque
from typing import Any, Iterable, Mapping, MutableMapping

from autogen import ConversableAgent

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


class MCPClientError(RuntimeError):
    """Raised when the Jira MCP client encounters an unrecoverable error."""


class MCPStdioTransport:
    """Minimal JSON-RPC transport that communicates with an MCP server over stdio."""

    def __init__(
        self,
        command: str,
        args: Iterable[str],
        env: Mapping[str, str] | None,
    ) -> None:
        if not command:
            raise MCPClientError("MCP transport requires a command to execute.")

        merged_env = os.environ.copy()
        if env:
            merged_env.update({str(key): str(value) for key, value in env.items()})

        self._process = subprocess.Popen(
            [command, *list(args)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=merged_env,
            text=False,
            bufsize=0,
        )
        if self._process.stdin is None or self._process.stdout is None:
            self.close()
            raise MCPClientError("Failed to establish pipes for the MCP transport.")

        self._stdin = self._process.stdin
        self._stdout = self._process.stdout
        self._stderr = self._process.stderr
        self._lock = threading.Lock()
        self._next_request_id = 0
        self._stderr_tail: deque[str] = deque(maxlen=50)

        if self._stderr is not None:
            threading.Thread(target=self._drain_stderr, daemon=True).start()

    # ------------------------------------------------------------------ utils
    def _ensure_alive(self) -> None:
        if self._process.poll() is not None:
            stderr_output = "\n".join(self._stderr_tail)
            if not stderr_output:
                stderr_output = "<no stderr output>"
            raise MCPClientError(
                "Jira MCP process exited unexpectedly. Last stderr output:\n" + stderr_output
            )

    def _drain_stderr(self) -> None:  # pragma: no cover - diagnostic helper
        assert self._stderr is not None
        for raw_line in iter(self._stderr.readline, b""):
            try:
                decoded = raw_line.decode("utf-8", errors="replace").rstrip()
            except Exception:  # pragma: no cover - safety net
                decoded = str(raw_line)
            if decoded:
                self._stderr_tail.append(decoded)

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive cleanup
            self._process.kill()
        finally:
            with contextlib.suppress(Exception):
                self._stdin.close()
            with contextlib.suppress(Exception):
                self._stdout.close()
            if self._stderr is not None:
                with contextlib.suppress(Exception):
                    self._stderr.close()

    # ---------------------------------------------------------------- requests
    def _send_bytes(self, payload: bytes) -> None:
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
        self._stdin.write(header + payload)
        self._stdin.flush()

    def _read_message(self) -> MutableMapping[str, Any]:
        self._ensure_alive()

        # Read headers until an empty line.
        header_bytes = bytearray()
        while True:
            line = self._stdout.readline()
            if not line:
                raise MCPClientError("Unexpected EOF while waiting for MCP response headers.")
            header_bytes.extend(line)
            if line in (b"\n", b"\r\n"):
                break

        header_text = header_bytes.decode("utf-8", errors="replace")
        content_length = None
        for raw_header in header_text.splitlines():
            key, _, value = raw_header.partition(":")
            if key.lower() == "content-length":
                try:
                    content_length = int(value.strip())
                except ValueError as exc:
                    raise MCPClientError(f"Invalid Content-Length header: {raw_header!r}") from exc
                break

        if content_length is None:
            raise MCPClientError("Missing Content-Length header in MCP response.")

        body = self._stdout.read(content_length)
        if not body:
            raise MCPClientError("Failed to read MCP response body.")

        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:  # pragma: no cover - protocol corruption
            raise MCPClientError(f"Malformed MCP JSON payload: {exc}") from exc

        if not isinstance(decoded, MutableMapping):
            raise MCPClientError(f"Unexpected MCP response type: {type(decoded)!r}")

        return decoded

    def request(self, method: str, params: Mapping[str, Any] | None) -> Any:
        with self._lock:
            self._ensure_alive()

            self._next_request_id += 1
            request_id = self._next_request_id
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
            }
            if params is not None:
                payload["params"] = params

            self._send_bytes(json.dumps(payload).encode("utf-8"))

            while True:
                message = self._read_message()
                if message.get("id") != request_id:
                    # Ignore notifications and responses to previous requests.
                    continue

                if "error" in message:
                    raise MCPClientError(
                        f"MCP request {method!r} failed: {json.dumps(message['error'], ensure_ascii=False)}"
                    )

                return message.get("result")

    def notify(self, method: str, params: Mapping[str, Any] | None) -> None:
        with self._lock:
            payload = {
                "jsonrpc": "2.0",
                "method": method,
            }
            if params is not None:
                payload["params"] = params

            self._send_bytes(json.dumps(payload).encode("utf-8"))


class JiraMCPClient:
    """High-level helper that speaks the MCP JSON-RPC protocol."""

    def __init__(self, spec: MutableMapping[str, Any]) -> None:
        self.name = str(spec.get("name", DEFAULT_JIRA_NAME))
        command, args, env = _normalise_spec(spec)
        self._transport = MCPStdioTransport(command, args, env)

        try:
            self._transport.request(
                "initialize",
                {
                    "protocolVersion": "0.1",
                    "clientInfo": {"name": "ag2-example", "version": "1.0"},
                    "capabilities": {},
                },
            )
            self._transport.notify("initialized", {})

            self._tools = self._collect_tools()
        except Exception:
            self._transport.close()
            raise

    # ----------------------------------------------------------------- helpers
    def _collect_tools(self) -> list[MutableMapping[str, Any]]:
        tools: list[MutableMapping[str, Any]] = []
        cursor = None

        while True:
            params: dict[str, Any] = {}
            if cursor is not None:
                params["cursor"] = cursor

            result = self._transport.request("tools/list", params or None)
            if isinstance(result, MutableMapping):
                batch = result.get("tools")
                if isinstance(batch, list):
                    tools.extend(item for item in batch if isinstance(item, MutableMapping))
                cursor = result.get("nextCursor")
                if cursor is None:
                    break
            else:
                break

        return tools

    # ---------------------------------------------------------------- interface
    def llm_description(self) -> str:
        if not self._tools:
            return (
                "Call Jira MCP tools by providing a tool name and optional JSON arguments. "
                "Tool discovery failed so consult server documentation for valid names."
            )

        lines = []
        for entry in self._tools:
            name = str(entry.get("name", "<unnamed>"))
            description = str(entry.get("description", "")).strip()
            if description:
                lines.append(f"- {name}: {description}")
            else:
                lines.append(f"- {name}")

        joined = "\n".join(lines)
        return (
            "Call Jira MCP tools by providing a tool name and optional JSON arguments. "
            "Available tools include:\n"
            + joined
        )

    def system_suffix(self) -> str:
        if not self._tools:
            return (
                "Use the `jira_call_tool` function when Jira context is required. "
                "Pass the MCP tool name and JSON arguments expected by the server."
            )

        tool_names = ", ".join(sorted(str(tool.get("name", "")) for tool in self._tools if tool.get("name")))
        return (
            "Use the `jira_call_tool` function to invoke Jira MCP operations. "
            f"Available tool identifiers: {tool_names}."
        )

    def call_tool(self, tool_name: str, arguments: Mapping[str, Any] | str | None = None) -> str:
        payload: dict[str, Any] = {"name": tool_name}
        if arguments is not None and len(arguments) == 0:
            arguments = None

        if arguments is not None:
            if isinstance(arguments, Mapping):
                payload["arguments"] = dict(arguments)
            elif isinstance(arguments, str):
                try:
                    parsed = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    raise MCPClientError(f"Failed to parse MCP arguments JSON: {exc}") from exc
                if not isinstance(parsed, Mapping):
                    raise MCPClientError("Parsed MCP arguments must be a JSON object.")
                payload["arguments"] = dict(parsed)
            else:
                raise MCPClientError(
                    "MCP arguments must be provided as a mapping or JSON-encoded string."
                )

        result = self._transport.request("tools/call", payload)
        return self._render_result(result)

    def _render_result(self, result: Any) -> str:
        if isinstance(result, MutableMapping):
            # Prefer textual outputs when present.
            outputs = result.get("content") or result.get("outputs")
            if isinstance(outputs, list):
                rendered: list[str] = []
                for item in outputs:
                    if not isinstance(item, Mapping):
                        continue
                    item_type = item.get("type")
                    if item_type == "text" and "text" in item:
                        rendered.append(str(item.get("text", "")))
                    elif item_type == "error":
                        message = item.get("message") or item.get("text") or item
                        rendered.append(f"Error: {message}")
                if rendered:
                    return "\n".join(rendered)

        return json.dumps(result, indent=2, ensure_ascii=False)

    def close(self) -> None:
        self._transport.close()


def _normalise_spec(spec: MutableMapping[str, Any]) -> tuple[str, list[str], Mapping[str, str]]:
    """Extract a stdio transport description from ``spec``."""

    # Direct `command` / `args` layout.
    if "command" in spec:
        command = str(spec["command"])
        args = [str(arg) for arg in spec.get("args", [])]
        env = spec.get("env") if isinstance(spec.get("env"), Mapping) else {}
        return command, args, env  # type: ignore[return-value]

    transport = spec.get("transport")
    if isinstance(transport, MutableMapping):
        transport_type = transport.get("type") or transport.get("mode")
        if str(transport_type).lower() != "stdio":
            raise MCPClientError(
                "Unsupported MCP transport. Only 'stdio' transports are supported by this example."
            )

        command = transport.get("command") or transport.get("path") or transport.get("executable")
        if not command:
            raise MCPClientError("MCP stdio transport requires a 'command' field.")

        args = transport.get("args") or transport.get("argv") or []
        env = transport.get("env")
        if env is not None and not isinstance(env, Mapping):
            raise MCPClientError("MCP transport 'env' must be a mapping of environment variables.")

        return str(command), [str(arg) for arg in args], env or {}

    raise MCPClientError(
        "Unsupported MCP spec format. Provide either 'command'/'args' or a 'transport' object with type 'stdio'."
    )


def _build_jira_client(
    env_file: pathlib.Path,
    runtime: str,
    image: str,
    spec_path: pathlib.Path | None,
) -> JiraMCPClient:
    """Return an MCP client that can communicate with the Jira server."""

    if spec_path is not None:
        spec = _load_tool_spec(spec_path)
        spec.setdefault("name", DEFAULT_JIRA_NAME)
    else:
        env_overrides = _load_env_file(env_file)
        args: list[str] = ["run", "--rm", "-i", "--env-file", str(env_file), image]
        spec = {
            "name": DEFAULT_JIRA_NAME,
            "command": runtime,
            "args": args,
            "env": env_overrides,
        }

    return JiraMCPClient(spec)


def run_agent(
    prompt: str,
    jira_env: pathlib.Path,
    runtime: str,
    image: str,
    spec_path: pathlib.Path | None,
) -> None:
    """Send ``prompt`` to the configured AG2 agent and print the response."""

    jira_client = _build_jira_client(jira_env, runtime, image, spec_path)

    system_message = (
        "You are a concise technical assistant. When possible, respond with bullet points and actionable summaries. "
        + jira_client.system_suffix()
    )

    agent = ConversableAgent(
        name="assistant",
        system_message=system_message,
        llm_config=_build_llm_config(),
    )

    @agent.register_for_llm(name="jira_call_tool", description=jira_client.llm_description())
    def jira_call_tool(tool_name: str, arguments: Mapping[str, Any] | str | None = None) -> str:
        try:
            return jira_client.call_tool(tool_name, arguments)
        except MCPClientError as exc:
            return f"Error calling Jira MCP tool '{tool_name}': {exc}"

    try:
        response = agent.generate_reply(messages=[{"role": "user", "content": prompt}])
    finally:
        jira_client.close()

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
