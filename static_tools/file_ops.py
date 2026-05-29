# tools/file_ops.py

from static_tools.base import safe_path


# --- 1. Schemas ---

FILE_TOOLS_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the content of a file from the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or overwrite an existing one with new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file."},
                    "content": {"type": "string", "description": "The full text content to write."}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "CRITICAL: MUST use this tool for existing files to modify specific parts. NEVER use write_file to overwrite an entire file if you only need to change a few lines. Always read the file first to get the exact text block for matching.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file."},
                    "old_text": {"type": "string", "description": "The exact text block to find."},
                    "new_text": {"type": "string", "description": "The text block to replace it with."}
                },
                "required": ["path", "old_text", "new_text"]
            }
        }
    }
]

# --- 2. Handlers ---

def run_read(path: str) -> str:
    """Read file content safely within WORKDIR."""
    try:
        full_path = safe_path(path)
        return full_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {str(e)}"

def run_write(path: str, content: str, mode: str = "overwrite") -> str:
    """Write content to a file, creating directories if needed."""

    full_path = safe_path(path)
    if mode == "create" and full_path.exists():
        return f"Error: File '{path}' already exists. Use 'edit_file' to modify it or 'overwrite' mode to replace."

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return f"Success: File '{path}' written successfully."
    except Exception as e:
        return f"Error writing file: {str(e)}"

def run_edit(path: str, old_text: str, new_text: str) -> str:
    """Standard search and replace edit logic."""
    try:
        full_path = safe_path(path)
        if not full_path.exists():
            return f"Error: File '{path}' not found for editing."
        
        content = full_path.read_text(encoding="utf-8")
        if old_text not in content:
            return f"Error: Could not find the exact 'old_text' block in '{path}'. Edit failed."
        
        new_content = content.replace(old_text, new_text)
        full_path.write_text(new_content, encoding="utf-8")
        return f"Success: File '{path}' updated."
    except Exception as e:
        return f"Error editing file: {str(e)}"