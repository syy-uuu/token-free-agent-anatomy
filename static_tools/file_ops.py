from static_tools.base import safe_path
import os
import sys
import time
import subprocess
import traceback
import py_compile

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
},
{
    "type": "function",
    "function": {
        "name": "view_file_with_line_numbers",
        "description": "Read the contents of an existing file with line numbers prefixed (e.g., '  1 | import os'). Always call this tool to inspect the exact line numbers BEFORE calling 'edit_file_by_lines'.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file to inspect."
                }
            },
            "required": ["path"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "edit_file_by_lines",
        "description": "CRITICAL: Surgical precision edit by line numbers. Replaces a specific line range [start_line, end_line] with 'new_content'. You MUST call 'view_file_with_line_numbers' first to verify the current line numbers.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file."
                },
                "start_line": {
                    "type": "integer",
                    "description": "The line number where the replacement should start (1-indexed, inclusive). Based on the output of view_file_with_line_numbers."
                },
                "end_line": {
                    "type": "integer",
                    "description": "The line number where the replacement should end (1-indexed, inclusive). To delete lines without adding new code, set new_content to empty string."
                },
                "new_content": {
                    "type": "string",
                    "description": "The new code that will replace the specified line range. Keep it minimal and focused only on the fix."
                }
            },
            "required": ["path", "start_line", "end_line", "new_content"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "append_file",
        "description": "RECOMMENDED for adding new code. Appends a block of text safely to the absolute END of an existing file. Use this tool when you want to add new functions, classes, or test cases, rather than rewriting existing lines. The system will automatically handle newlines and spacing.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to the file."},
                "text": {"type": "string", "description": "The new code or text block to append to the end of the file."}
            },
            "required": ["path", "text"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "execute_test",
        "description": "CRITICAL: Executes the specified Python script to perform syntax, compilation, and early initialization checks. For persistent applications (e.g., servers, infinite loops, background daemons), the system will automatically enforce a 2-second timeout. If no exceptions occur within these 2 seconds, it will be judged as successful and return a success message. NOTE: A successful test execution ONLY guarantees that your script is free of syntax errors or early crashes—it DOES NOT mean your business logic is complete. Always verify your implementation satisfies the requirements after testing.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string", 
                    "description": "Relative path to the Python file you want to test (e.g., 'main.py')."
                }
            },
            "required": ["path"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "list_directory",
        "description": "Lists files and subdirectories in the specified directory with details (size, modified time). Use this tool to verify if a file was successfully created, check file sizes, or explore the current workspace structure before editing.",
        "parameters": {
            "type": "object",
            "properties": {
                "sub_dir": {
                    "type": "string",
                    "description": "Optional relative path to a subdirectory to list (e.g., 'src' or 'tests'). Defaults to '.' (the current workspace root)."
                }
            },
            "required": []
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
        return f"Error: File '{path}' already exists. Use 'edit_file' to modify it or 'append_file' mode to append."

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        # 2. If this is a Python file, immediately run syntax and compilation checks
        if path.endswith(".py"):
            try:
                # py_compile only checks syntax errors (e.g., IndentationError, SyntaxError)
                # To catch NameError (undefined variables), use lightweight tools like flake8 or ruff
                py_compile.compile(str(full_path), doraise=True)
            except py_compile.PyCompileError as e:
                # If compilation fails, immediately return a fatal error to the Agent
                return f"Error: Code written, but Python compilation FAILED:\n{str(e)}"
        return f"File '{path}' written successfully."
    except Exception as e:
        return f"Error writing file: {str(e)}"


def run_view_file_with_line_numbers(path: str) -> str:
    """Read a file and automatically prefix line numbers for precise Agent edits."""
    full_path = safe_path(path)
    if not full_path.exists():
        return f"Error: File '{path}' does not exist."
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        output = []
        for idx, line in enumerate(lines, 1):
            output.append(f"{idx:4d} | {line}")
        return "".join(output)
    except Exception as e:
        return f"Error reading file: {str(e)}"

def run_edit_file_by_lines(path: str, start_line: int, end_line: int, new_content: str) -> str:
    """
    Partially replace file content by a specified line range (precise line-based editing tool).
    
    :param path: Relative file path, for example 'main.py'
    :param start_line: Start line number of the edit (inclusive, 1-indexed)
    :param end_line: End line number of the edit (inclusive, 1-indexed)
    :param new_content: New code string used to replace the specified range
    """
    full_path = safe_path(path)
    if not full_path.exists():
        return f"Error: File '{path}' does not exist."
    try:
        # 1. Read all lines from the original file
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        
        # 2. Boundary checks and fault tolerance
        if start_line < 1:
            start_line = 1
        if end_line > total_lines:
            end_line = total_lines
        if start_line > total_lines:
            return f"Error: start_line ({start_line}) is beyond the total {total_lines} lines in the file ({total_lines})."
            
        if start_line > end_line:
            return f"Error: start_line ({start_line}) cannot be greater than end_line ({end_line})."

        # 3. Parse new content (handle newlines and ensure trailing newline)
        new_lines = [line + '\n' if not line.endswith('\n') else line 
                     for line in new_content.splitlines()]
        
        # If new content is fully empty, the Agent intends to delete this range
        if not new_content.strip() and len(new_lines) == 1 and new_lines[0] == '\n':
            new_lines = []

        # 4. Core replacement logic (Python list indexing starts at 0, so use -1)
        # lines[start_line-1 : end_line] is the old code to be replaced
        lines[start_line - 1 : end_line] = new_lines

        # 5. Write back to file
        with open(full_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
            
        return f"Success: Updated lines {start_line} to {end_line} in '{path}' successfully."

    except Exception as e:
        return f"Error occurred while editing file: {str(e)}"

def handle_mkdir(arguments: dict) -> str:
    # 1. Strictly extract required argument
    path_str = arguments.get("path")
    if not path_str:
        return "ERROR: Missing required argument 'path'."
        
    try:
        # 2. Call the common safe-path validator (assumed to return pathlib.Path)
        target_path = safe_path(path_str)

        # 3. Idempotency check (avoid unnecessary disk I/O)
        if target_path.exists():
            if target_path.is_dir():
                return f"OBSERVATION: Directory '{path_str}' already exists. No action needed."
            else:
                return f"ERROR: Path '{path_str}' exists but it is a FILE, cannot convert to directory."

        # 4. Defensive guard and self-healing interception mechanism
        # Rule: if the path ends with .py or the file name contains '.' (e.g., .txt, .json)
        if target_path.suffix == '.py' or ('.' in target_path.name):
            # Automatically downgrade to its parent directory
            dir_to_create = target_path.parent
            
            # If the parent is already workspace root, no physical directory creation is needed
            if str(dir_to_create) == '.' or dir_to_create == Path():
                return f"OBSERVATION: Target path '{path_str}' seems to be a file in the root workspace. No directory needs to be created."
            
            # Apply strict physical action: create its parent directory instead
            dir_to_create.mkdir(parents=True, exist_ok=True)
            return f"OBSERVATION: Warning - You passed a file path '{path_str}' to mkdir. The system has automatically healed this by creating its parent directory instead: '{dir_to_create}/'. Please use 'write_file' next to create the actual file."

        # 5. Normal directory creation logic
        # parents=True is equivalent to mkdir -p
        target_path.mkdir(parents=True, exist_ok=True)
        
        # 6. Return deterministic physical-success feedback
        return f"OBSERVATION: Directory '{path_str}' successfully created."

    except ValueError as ve:
        # Specifically intercept and gracefully return security-violation errors
        return f"ERROR: Security Violation. {str(ve)}"
        
    except Exception as e:
        # Fallback for other system-level physical errors
        return f"ERROR: Failed to create directory due to system error: {str(e)}"
    
def run_append_file(path: str, text: str) -> str:
    """Append new text block to the end of an existing file safely."""
    try:
        full_path = safe_path(path)
        if not full_path.exists():
            return f"Error: File '{path}' not found. Cannot append."
            
        if not text.strip():
            return "Error: Cannot append empty text."

        # Read existing content and check trailing newline
        content = full_path.read_text(encoding="utf-8")
        
        # Smart tolerance: ensure exactly proper spacing/newlines between old and new content
        # If the file does not end with a newline, add one to prevent line concatenation
        if content and not content.endswith("\n"):
            prefix = "\n\n"
        elif content and content.endswith("\n") and not content.endswith("\n\n"):
            prefix = "\n"
        else:
            prefix = ""
            
        # Execute append
        with open(full_path, "a", encoding="utf-8") as f:
            f.write(prefix + text.strip("\r\n") + "\n")
            
        return f" File '{path}' appended with {len(text.splitlines())} lines."
        
    except Exception as e:
        return f"Error appending to file: {str(e)}"
    




def run_execute_test(path: str) -> str:
    """
    Advanced General-Purpose Runtime Verification Tool.
    Uses process-level timeout mutation to verify persistent GUI/servers,
    and implements strict line-level stderr filtering for LLM comprehension.
    """
    # 1. Strong defense: intercept missing-argument or None hallucination cases
    if path is None or not str(path).strip():
        return (
            "Error: Missing required argument 'path'. "
            "You must provide a valid file path string to execute_test (e.g., {'path': 'main.py'})."
        )
        
    try:
        # Assume safe_path is the global function that validates path security
        full_path = safe_path(path)
        if not full_path.exists():
            return f"Error: File '{path}' not found."
            
        if not str(path).endswith(".py"):
            return f"Error: 'execute_test' can only test Python (.py) files."

        # ======= 2. Static compilation checks (catch basic syntax/indentation errors first) =======
        try:
            py_compile.compile(str(full_path), doraise=True)
        except py_compile.PyCompileError as e:
            return f"❌ TEST FAILED: Compilation/Syntax Error!\n--------------------------------------------------\n{str(e.msg)}"

        # ======= 3. Semantic substance checks (prevent score gaming with comments only) =======
        script_content = full_path.read_text(encoding="utf-8")

        # Guard A: block completely empty files
        if not script_content.strip():
            return (
                "❌ TEST FAILED: The file is COMPLETELY EMPTY!\n"
                "--------------------------------------------------\n"
                "Harness Guard: You cannot pass a milestone with an empty file. "
                "Please implement the required logical scaffolding before testing."
            )
            
        # Guard B: require substantive executable lines
        lines = script_content.splitlines()
        effective_lines = [
            l.strip() for l in lines 
            if l.strip() and not l.strip().startswith("#") and not l.strip().startswith('"""') and not l.strip().startswith("'''")
        ]
        if len(effective_lines) < 1:
            return (
                "❌ TEST FAILED: No effective executable code found.\n"
                "--------------------------------------------------\n"
                "The file contains only comments or blank spacing. You must write "
                "actual execution statements (e.g., imports, functions) to pass."
            )

        # ======= 4. Dynamic runtime lifecycle verification (timeout circuit breaker) =======
        stderr_output = ""
        raw_stdout = ""
        is_timeout_success = False

        try:
            # Run the Agent's original code directly without any text concatenation pollution
            result = subprocess.run(
                [sys.executable, str(full_path)],
                capture_output=True,
                text=True,
                timeout=2.0  # Allow 2 seconds for startup and initialization
            )
            
            # If the script exits successfully within 2 seconds (e.g., non-blocking scripts)
            if result.returncode == 0:
                return f"'{path}' executed and exited normally with code 0."
            
            # If it does not exit successfully, extract stderr/stdout
            stderr_output = result.stderr if result.stderr else ""
            raw_stdout = result.stdout if result.stdout else ""

        except subprocess.TimeoutExpired as e:
            # Core idea: timeout means the script successfully started a persistent process (e.g., Tkinter/Flask)
            # This usually indicates initialization did not crash with NameError/ImportError
            is_timeout_success = True
            
            # Safely capture stdout/stderr already emitted before timeout
            stderr_output = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode('utf-8', errors='ignore') if e.stderr else "")
            raw_stdout = e.stdout if isinstance(e.stdout, str) else (e.stdout.decode('utf-8', errors='ignore') if e.stdout else "")

        # ======= 5. Structured error-engineering parsing layer =======
        stderr_output = stderr_output.strip()
        
        # Check whether stderr still leaked a Traceback/error during timeout hang
        if "Traceback" in stderr_output or "Error" in stderr_output or "Exception" in stderr_output:
            is_timeout_success = False  # Timed out, but process was actually failing internally

        # If finally judged successful, return a clean receipt
        if is_timeout_success:
            return (
                f"'{path}' executed successfully"
            )

        # If judged failed, clean low-level noise and keep high-readability error content
        if not stderr_output:
            if raw_stdout.strip():
                stderr_output = f"[Captured from stdout] {raw_stdout.strip()}"
            else:
                stderr_output = "Unknown runtime crash. Process exited but left no output streams."

        # Filter redundant absolute paths and keep core stack information
        cleaned_error = []
        for line in stderr_output.splitlines():
            if any(k in line for k in ["Traceback", "File", "Error", "Exception", "NameError", "ModuleNotFoundError"]):
            # Replace long absolute paths with current relative path
                cleaned_line = line.replace(str(full_path.parent), ".")
                cleaned_error.append(cleaned_line)
        
        error_report = "\n".join(cleaned_error) if cleaned_error else stderr_output

        return (
            f"❌ TEST FAILED: Runtime Exception occurred!\n"
            f"--------------------------------------------------\n"
            f"{error_report}\n"
            f"--------------------------------------------------\n"
        )

    except Exception as e:
        # If a rare harness/path-resolution failure occurs, return full traceback for debugging
        return (
            f"⚠️ Error executing test (Harness Internal Error): {str(e)}\n"
            f"Details:\n{traceback.format_exc()}"
        )


def run_list_directory(sub_dir: str = ".") -> str:
    """
    Safely lists the contents of a directory with human-readable file details.
    Optimized for LLM context parsing.
    """
    try:
        # 1. Path security validation (assume workspace root is obtained via WORKSPACE_ROOT)
        # Current directory is used here for demonstration; production should restrict to sandbox
        workspace_root = safe_path(".")
        
        # Compute target path
        target_path = safe_path(sub_dir)
        
        # Security defense: prevent escaping workspace via ../../../
        if os.path.commonpath([workspace_root]) != os.path.commonpath([workspace_root, target_path]):
            return "Error: Access denied. You cannot list directories outside the project workspace."
            
        if not target_path.exists():
            return f"Error: Directory '{sub_dir}' does not exist."
            
        if not target_path.is_dir():
            return f"Error: '{sub_dir}' is a file, not a directory. Use read_file to view its content."

        # 2. Traverse directory and extract structured metadata
        dirs_list = []
        files_list = []
        
        # Ignore low-level noisy items for Agent reasoning
        IGNORE_PATTERNS = {".git", ".pytest_cache", "__pycache__", ".DS_Store", ".venv", "venv"}

        for entry in target_path.iterdir():
            if entry.name in IGNORE_PATTERNS or entry.name.endswith(".pyc"):
                continue
                
            # Get modified time and size
            stat = entry.stat()
            mod_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
            
            if entry.is_dir():
                dirs_list.append(f"📁 {entry.name}/ [Directory] | Modified: {mod_time}")
            else:
                # Convert to human-readable file size
                size_bytes = stat.st_size
                if size_bytes < 1024:
                    size_str = f"{size_bytes} B"
                else:
                    size_str = f"{size_bytes / 1024:.1f} KB"
                    
                files_list.append(f"📄 {entry.name} ({size_str}) | Modified: {mod_time}")

        # 3. Assemble a Markdown report that is easy for LLM semantic parsing
        output = [f"### 🗂️ Target Directory: '{sub_dir}'"]
        
        if not dirs_list and not files_list:
            output.append("(The directory is empty)")
            return "\n".join(output)
            
        if dirs_list:
            output.append("\n**Subdirectories:**")
            output.extend(sorted(dirs_list))
            
        if files_list:
            output.append("\n**Files:**")
            output.extend(sorted(files_list))
            
        return "\n".join(output)

    except Exception as e:
        return f"Error listing directory: {str(e)}"