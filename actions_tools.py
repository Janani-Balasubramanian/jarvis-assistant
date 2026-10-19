"""
Jarvis - Phase 5: laptop actions.

Jarvis can only do what you list in actions.json. There is no "run any command" tool:
the model picks an action NAME (plus optional whitelisted numeric parameters), and the command
that runs is the one you wrote. Commands run without a shell, so a parameter can never smuggle
extra arguments or operators into them.

actions.json format (see actions.example.json):
{
  "open_calculator": {
    "description": "Open the calculator",
    "confirm": false,                       # default true; only set false for harmless actions
    "command": {"windows": ["calc.exe"], "mac": ["open", "-a", "Calculator"], "linux": ["gnome-calculator"]}
  },
  "set_volume": {
    "description": "Set the system volume",
    "params": {"level": {"min": 0, "max": 100}},          # integers only
    "command": {"mac": ["osascript", "-e", "set volume output volume {level}"]},
    "wait": true                                          # wait for it to finish and report the result
  },
  "open_classroom": {"description": "Open Google Classroom", "url": "https://classroom.google.com", "confirm": false}
}
"""

import json
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = Path(os.getenv("JARVIS_ACTIONS_FILE") or BASE_DIR / "actions.json")


def _platform() -> str:
    return {"win32": "windows", "darwin": "mac"}.get(sys.platform, "linux")


def _load() -> dict:
    if not CONFIG_FILE.exists():
        raise ValueError(f"No actions configured yet. Copy actions.example.json to {CONFIG_FILE.name} and edit it.")
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def _command_for_platform(action: dict):
    command = action.get("command")
    return command.get(_platform()) if isinstance(command, dict) else command


def describe_action(name: str) -> str:
    """Human-readable description, used when asking for confirmation."""
    try:
        return _load().get(name, {}).get("description") or name.replace("_", " ")
    except Exception:
        return name.replace("_", " ")


def needs_confirmation(args: dict) -> bool:
    """Called by the dispatcher: does this particular run_action call need the user's approval?"""
    try:
        return bool(_load().get(args.get("name"), {}).get("confirm", True))
    except Exception:
        return True  # if in doubt, ask


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------

def list_actions() -> str:
    actions = _load()
    plat = _platform()
    lines = []
    for name, a in actions.items():
        if "url" not in a and not _command_for_platform(a):
            continue  # not set up for this operating system
        params = ", ".join(
            f"{k} ({r.get('min', '')}-{r.get('max', '')})" for k, r in a.get("params", {}).items()
        )
        lines.append(f"{name}: {a.get('description', '')}" + (f" [params: {params}]" if params else ""))
    return "\n".join(lines) or f"No actions available for {plat}."


def run_action(name: str, params: dict | None = None) -> str:
    actions = _load()
    if name not in actions:
        return f"Unknown action '{name}'. Use list_actions to see what is allowed."
    action = actions[name]
    params = params or {}
    spec = action.get("params", {})

    extra = set(params) - set(spec)
    if extra:
        return f"Unexpected parameter(s): {', '.join(sorted(extra))}."
    values = {}
    for key, rule in spec.items():
        if key not in params:
            return f"Missing parameter '{key}'."
        try:
            value = int(params[key])
        except (TypeError, ValueError):
            return f"Parameter '{key}' must be a whole number."
        if not rule.get("min", value) <= value <= rule.get("max", value):
            return f"Parameter '{key}' must be between {rule.get('min')} and {rule.get('max')}."
        values[key] = value

    if "url" in action:
        webbrowser.open(action["url"])
        return f"Opened {action['url']}."

    argv = _command_for_platform(action)
    if not argv:
        return f"Action '{name}' is not set up for {_platform()}."
    argv = [part.format(**values) for part in argv]
    exe = shutil.which(argv[0])
    if not exe:
        return f"Command not found: {argv[0]}"
    argv[0] = exe

    if action.get("wait"):
        try:
            proc = subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace", timeout=15)
        except subprocess.TimeoutExpired:
            return f"'{name}' took too long and was stopped."
        detail = (proc.stdout + proc.stderr).strip()[:200]
        return f"Ran '{name}' (exit code {proc.returncode})." + (f" {detail}" if detail else "")

    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"Started '{name}'."


REGISTRY = {
    "list_actions": (list_actions, False),
    "run_action": (run_action, needs_confirmation),  # per-action confirm flag from actions.json
}

SCHEMAS = [
    {
        "name": "list_actions",
        "description": "List the laptop actions Jarvis is allowed to perform (open apps, websites, adjust settings).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_action",
        "description": (
            "Perform one of the allowed laptop actions by name. Only actions from list_actions exist; "
            "never guess names. Some actions need a numeric parameter."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "params": {"type": "object", "description": "Integer parameters, e.g. {\"level\": 40}"},
            },
            "required": ["name"],
        },
    },
]
