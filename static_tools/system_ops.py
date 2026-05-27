import subprocess
from utils.config import config

# 1. Brain's Guide (The Schema)
BASH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Execute a bash command in the terminal. Use this for file system navigation, running scripts, or system tasks.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The full bash command to run."
                }
            },
            "required": ["command"]
        }
    }
}

# 2. Hand's Action (The Logic)
def run_bash(command: str, timeout: int = 30) -> str:
    """
    Executes a bash command and returns the output or error.
    Includes a timeout to prevent infinite loops.
    """
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        # Run the command and capture output
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=config.workdir  # Ensure commands run in the agent's working directory
        )
        
        # Combine stdout and stderr to give the brain full context
        output = result.stdout
        error = result.stderr
        
        if result.returncode == 0:
            return output if output.strip() else "(Execution successful, no output)"
        else:
            return f"Error (Return Code {result.returncode}):\n{error}\n{output}"
            
    except subprocess.TimeoutExpired:
        return f"Timeout Error: The command took longer than {timeout} seconds to execute."
    except Exception as e:
        return f"Unexpected Error: {str(e)}"