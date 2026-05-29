from static_tools.base import safe_path
import os


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
    },
    {
    "type": "function",
    "function": {
        "name": "mkdir",
        "description": "CRITICAL: MUST use this tool whenever you need to create a new directory or workspace folder. NEVER assume a directory exists. This tool safely creates the target directory and will automatically create any missing parent directories in the path (equivalent to mkdir -p). Check if the directory structure is correct before calling.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The relative or absolute path of the directory to be created. Do not use vague or empty paths."
                }
            },
            "required": ["path"]
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

    
def handle_mkdir(arguments: dict) -> str:
# 1. 刚性提取参数
    path_str = arguments.get("path")
    if not path_str:
        return "ERROR: Missing required argument 'path'."
        
    try:
        # 2. 调用你的通用安全路径校验器进行物理越权拦截
        # 如果越权，这里会直接抛出 ValueError 并被下面的 except 捕获
        target_path = safe_path(path_str)

        # 3. 幂等性检查（避免无效的磁盘 IO）
        if target_path.exists():
            if target_path.is_dir():
                return f"OBSERVATION: Directory '{path_str}' already exists. No action needed."
            else:
                return f"ERROR: Path '{path_str}' exists but it is a FILE, cannot convert to directory."

        # 4. 物理落地：级联创建目录 (等价于 mkdir -p)
        # exist_ok=True 预防多线程并发冲突，parents=True 开启多级级联创建
        target_path.mkdir(parents=True, exist_ok=True)
        
        # 5. 返回确定性的物理成功反馈
        return f"OBSERVATION: Success. Directory '{path_str}' and all its missing parents have been physically created within the secure workspace."

    except ValueError as ve:
        # 专门拦截并优雅返回安全越权报错，直接把异常甩回大模型脸上，警示它越界了
        return f"ERROR: Security Violation. {str(ve)}"
        
    except Exception as e:
        # 兜底其余系统级物理报错（如磁盘满、无权限等）
        return f"ERROR: Failed to create directory due to system error: {str(e)}"