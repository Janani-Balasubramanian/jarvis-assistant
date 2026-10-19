import subprocess

def run_terminal_command(command: str) -> str:
    """Run an arbitrary terminal command."""
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        
        output = f"Exit code: {proc.returncode}"
        if stdout:
            output += f"\nStdout:\n{stdout[:2000]}"
        if stderr:
            output += f"\nStderr:\n{stderr[:2000]}"
        return output
    except subprocess.TimeoutExpired:
        return f"Command '{command}' took too long and was stopped."
    except Exception as e:
        return f"Failed to run command: {e}"

REGISTRY = {
    # The `True` ensures that CONFIRM is always triggered for this tool.
    "run_terminal_command": (run_terminal_command, True),
}

SCHEMAS = [
    {
        "name": "run_terminal_command",
        "description": (
            "Run an arbitrary system terminal command in a real shell (powershell/cmd/bash). "
            "Use this to take control of the user's system, read/write files not otherwise exposed, or execute scripts. "
            "WARNING: Because this executes arbitrary code, the user MUST confirm every execution."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The exact shell command to execute."
                },
            },
            "required": ["command"],
        },
    }
]
