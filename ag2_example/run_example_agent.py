"""Entry point for the AG2 markItDown Docker example agent.

The script performs a small amount of orchestration around the AG2 runtime:

1. Loads the declarative agent application definition from ``agent_app.yaml``.
2. Makes sure environment variables expected by the configuration (``HF_TOKEN`` and ``REPO_ROOT``) are present.
3. Runs the AG2 task with the user supplied prompt and streams the final result to stdout.

The helper is intentionally lightweight so that it is easy to adapt when experimenting with additional agents,
models, or MCP integrations.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import inspect
import os
import pkgutil
import sys
from pathlib import Path
from typing import Any, Callable

import yaml

APP_ROOT = Path(__file__).resolve().parent
REPO_ROOT = APP_ROOT.parent
DEFAULT_PROMPT = "Summarise README.md and provide a short bulleted outline."


def _load_app_builder() -> Callable[[dict[str, Any]], Any]:
    """Load the AG2 application builder entry point.

    The Python package name for AG2 is still evolving, so we try a few common import locations before failing
    with a helpful message. The returned callable must accept a configuration dictionary and return an object
    with a ``run`` method that triggers an agent task. At runtime this corresponds to ``ag2.app.App`` or
    ``ag2.runtime.App`` depending on the installed version.
    """

    ag2_spec = importlib.util.find_spec("ag2")
    if ag2_spec is None:
        raise ImportError(
            "AG2 is not installed. Install it by following the official instructions at https://ag2.ai/docs "
            "(for example \"pip install 'ag2 @ git+https://github.com/ag2ai/ag2.git'\") before running the example."
        )

    candidate_paths = (
        "ag2.app.App",
        "ag2.runtime.App",
        "ag2.core.app.App",
        "ag2.app.runtime.App",
        "ag2.app.app.App",
    )

    for path in candidate_paths:
        module_name, _, attr = path.rpartition(".")
        try:
            module = __import__(module_name, fromlist=[attr])
        except ImportError:
            continue
        builder = getattr(module, attr, None)
        if builder is None:
            continue

        if hasattr(builder, "from_dict") and callable(getattr(builder, "from_dict")):
            return getattr(builder, "from_dict")

        if callable(builder):
            def _create_app(config: dict[str, Any], _builder: Callable[[dict[str, Any]], Any] = builder) -> Any:
                return _builder(config)

            return _create_app

    def _candidate_from_obj(obj: Any) -> Callable[[dict[str, Any]], Any] | None:
        if obj is None:
            return None

        if hasattr(obj, "from_dict") and callable(getattr(obj, "from_dict")):
            return getattr(obj, "from_dict")

        if inspect.isclass(obj):
            return lambda config, cls=obj: cls(config)

        if callable(obj):
            return obj

        return None

    try:
        ag2_package = importlib.import_module("ag2")
    except ImportError as exc:  # pragma: no cover - guarded by find_spec above
        raise ImportError("Failed to import the AG2 package even though it was detected.") from exc

    for attr_name in ("App", "create_app", "build_app"):
        builder = _candidate_from_obj(getattr(ag2_package, attr_name, None))
        if builder is not None:
            return builder

    if getattr(ag2_package, "__path__", None):
        for module_info in pkgutil.walk_packages(ag2_package.__path__, ag2_package.__name__ + "."):
            try:
                module = importlib.import_module(module_info.name)
            except Exception:  # pragma: no cover - best effort discovery for evolving APIs
                continue

            for attr_name in ("App", "Application", "AG2App", "create_app", "build_app"):
                builder = _candidate_from_obj(getattr(module, attr_name, None))
                if builder is not None:
                    return builder

    raise ImportError(
        "Could not locate the AG2 application entry point. Confirm that your installed AG2 version exposes "
        "an App builder (for example ag2.app.App)."
    )


def run_agent(prompt: str) -> None:
    if "HF_TOKEN" not in os.environ:
        raise RuntimeError("HF_TOKEN environment variable is required to authenticate with the Hugging Face router.")

    os.environ.setdefault("REPO_ROOT", str(REPO_ROOT))

    jira_env_file = os.environ.get("JIRA_MCP_ENV_FILE")
    if jira_env_file:
        jira_path = Path(jira_env_file).expanduser()
        if not jira_path.is_file():
            raise RuntimeError(
                "JIRA_MCP_ENV_FILE is set to '{jira_env_file}' but the file does not exist. "
                "Provide a valid env-file for the Jira MCP server or remove the variable to use the default lookup."
                .format(jira_env_file=jira_env_file)
            )
        resolved = str(jira_path.resolve())
        os.environ["JIRA_MCP_ENV_FILE"] = resolved
        jira_env_file = resolved
    else:
        candidate_files = (
            APP_ROOT / ".env.jira",
            APP_ROOT / ".env",
        )
        for candidate in candidate_files:
            if candidate.is_file():
                resolved = str(candidate.resolve())
                os.environ["JIRA_MCP_ENV_FILE"] = resolved
                jira_env_file = resolved
                break
        if jira_env_file is None:
            raise RuntimeError(
                "A Jira MCP env file is required. Set the JIRA_MCP_ENV_FILE environment variable to the path of your "
                "credentials file (for example, 'export JIRA_MCP_ENV_FILE=ag2_example/.env.jira') or place the file at "
                "ag2_example/.env.jira."
            )

    with (APP_ROOT / "agent_app.yaml").open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    app_builder = _load_app_builder()
    app = app_builder(config)

    result = app.run(prompt)

    if hasattr(result, "final_response"):
        print(result.final_response)
    else:
        print(result)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the AG2 Docker + markItDown example agent.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default=DEFAULT_PROMPT,
        help="User prompt that will be forwarded to the AG2 agent.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        run_agent(args.prompt)
    except Exception as exc:  # noqa: BLE001 - surface rich error message
        parser.error(str(exc))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
