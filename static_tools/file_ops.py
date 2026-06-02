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
        # 2. 如果是 Python 文件，立刻进行语法和编译静态检查
        if path.endswith(".py"):
            try:
                # py_compile 只会检查语法错误（如 IndentationError、SyntaxError）
                # 如果要检查 NameError（未定义变量），可以用 flake8 或 ruff 这种轻量工具
                py_compile.compile(str(full_path), doraise=True)
            except py_compile.PyCompileError as e:
                # 如果编译失败，立刻把致命错误返回给 Agent，不让它盲目自信！
                return f"Error: Code written, but Python compilation FAILED:\n{str(e)}"
        return f"File '{path}' written successfully."
    except Exception as e:
        return f"Error writing file: {str(e)}"


def run_view_file_with_line_numbers(path: str) -> str:
    """读取文件并自动带上行号，方便 Agent 观察后进行精准定位修改"""
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
    通过指定行号区间，局部替换文件内容（基于行号的精确定向修改工具）。
    
    :param path: 文件相对路径，例如 'main.py'
    :param start_line: 修改的起始行号（包含，从 1 开始计数）
    :param end_line: 修改的结束行号（包含，从 1 开始计数）
    :param new_content: 用来替换该区间的新代码字符串
    """
    full_path = safe_path(path)
    if not full_path.exists():
        return f"Error: File '{path}' does not exist."
    try:
        # 1. 读取原文件所有行
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        
        # 2. 边界条件防御与容错
        if start_line < 1:
            start_line = 1
        if end_line > total_lines:
            end_line = total_lines
        if start_line > total_lines:
            return f"Error: start_line ({start_line}) is beyond the total {total_lines} lines in the file ({total_lines})."
            
        if start_line > end_line:
            return f"Error: start_line ({start_line}) cannot be greater than end_line ({end_line})."

        # 3. 解析新内容（处理换行符，确保末尾有换行）
        new_lines = [line + '\n' if not line.endswith('\n') else line 
                     for line in new_content.splitlines()]
        
        # 如果新内容完全为空，说明 Agent 想删除这个区间的代码
        if not new_content.strip() and len(new_lines) == 1 and new_lines[0] == '\n':
            new_lines = []

        # 4. 核心替换逻辑 (注意 Python 列表索引从 0 开始，所以要 -1)
        # lines[start_line-1 : end_line] 就是要被干掉的老代码
        lines[start_line - 1 : end_line] = new_lines

        # 5. 写回文件
        with open(full_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
            
        return f"Success: Updated lines {start_line} to {end_line} in '{path}' successfully."

    except Exception as e:
        return f"Error occurred while editing file: {str(e)}"

def handle_mkdir(arguments: dict) -> str:
    # 1. 刚性提取参数
    path_str = arguments.get("path")
    if not path_str:
        return "ERROR: Missing required argument 'path'."
        
    try:
        # 2. 调用通用安全路径校验器（假设返回的是 pathlib.Path 对象）
        target_path = safe_path(path_str)

        # 3. 幂等性检查（避免无效的磁盘 IO）
        if target_path.exists():
            if target_path.is_dir():
                return f"OBSERVATION: Directory '{path_str}' already exists. No action needed."
            else:
                return f"ERROR: Path '{path_str}' exists but it is a FILE, cannot convert to directory."

        # 🚀 4. 防呆与自愈拦截机制 (防御性编程)
        # 判定条件：如果是以 .py 结尾，或者文件名里包含点 '.'（如 .txt, .json）
        if target_path.suffix == '.py' or ('.' in target_path.name):
            # 自动降级提取其父目录
            dir_to_create = target_path.parent
            
            # 如果切出来的父目录已经是当前工作区顶级根目录了，提示无需物理创建
            if str(dir_to_create) == '.' or dir_to_create == Path():
                return f"OBSERVATION: Target path '{path_str}' seems to be a file in the root workspace. No directory needs to be created."
            
            # 刚性物理落地：改为创建它的父目录！
            dir_to_create.mkdir(parents=True, exist_ok=True)
            return f"OBSERVATION: Warning - You passed a file path '{path_str}' to mkdir. The system has automatically healed this by creating its parent directory instead: '{dir_to_create}/'. Please use 'write_file' next to create the actual file."

        # 🚀 5. 正常创建目录逻辑
        # parents=True 等价于 mkdir -p
        target_path.mkdir(parents=True, exist_ok=True)
        
        # 6. 返回确定性的物理成功反馈
        return f"OBSERVATION: Directory '{path_str}' successfully created."

    except ValueError as ve:
        # 专门拦截并优雅返回安全越权报错
        return f"ERROR: Security Violation. {str(ve)}"
        
    except Exception as e:
        # 兜底其余系统级物理报错
        return f"ERROR: Failed to create directory due to system error: {str(e)}"
    
def run_append_file(path: str, text: str) -> str:
    """Append new text block to the end of an existing file safely."""
    try:
        full_path = safe_path(path)
        if not full_path.exists():
            return f"Error: File '{path}' not found. Cannot append."
            
        if not text.strip():
            return "Error: Cannot append empty text."

        # 读取原有内容，检查末尾的换行符
        content = full_path.read_text(encoding="utf-8")
        
        # 智能容错：确保原有内容和新内容之间有且仅有合适的换行
        # 如果文件不是以换行符结尾，帮模型补一个，防止新代码跟老代码挤在同一行
        if content and not content.endswith("\n"):
            prefix = "\n\n"
        elif content and content.endswith("\n") and not content.endswith("\n\n"):
            prefix = "\n"
        else:
            prefix = ""
            
        # 执行追加
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
    # 1. 强力防御：拦截大模型参数漏传或 None 幻觉
    if path is None or not str(path).strip():
        return (
            "Error: Missing required argument 'path'. "
            "You must provide a valid file path string to execute_test (e.g., {'path': 'main.py'})."
        )
        
    try:
        # 假设 safe_path 是你系统里校验路径安全的全局函数
        full_path = safe_path(path)
        if not full_path.exists():
            return f"Error: File '{path}' not found."
            
        if not str(path).endswith(".py"):
            return f"Error: 'execute_test' can only test Python (.py) files."

        # ======= 2. 静态编译检查 (先抓基础语法、缩进错误) =======
        try:
            py_compile.compile(str(full_path), doraise=True)
        except py_compile.PyCompileError as e:
            return f"❌ TEST FAILED: Compilation/Syntax Error!\n--------------------------------------------------\n{str(e.msg)}"

        # ======= 3. 语义实质性检查 (防 Agent 刷分和注释敷衍) =======
        script_content = full_path.read_text(encoding="utf-8")

        # 守卫 A：绝对空文件拦截
        if not script_content.strip():
            return (
                "❌ TEST FAILED: The file is COMPLETELY EMPTY!\n"
                "--------------------------------------------------\n"
                "Harness Guard: You cannot pass a milestone with an empty file. "
                "Please implement the required logical scaffolding before testing."
            )
            
        # 守卫 B：实质性有效代码行拦截
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

        # ======= 4. 动态运行生命周期验证 (超时熔断机制) =======
        stderr_output = ""
        raw_stdout = ""
        is_timeout_success = False

        try:
            # 完整运行 Agent 的原始代码，不进行任何文本拼接污染
            result = subprocess.run(
                [sys.executable, str(full_path)],
                capture_output=True,
                text=True,
                timeout=2.0  # 给程序 2 秒钟时间让它充分拉起和初始化
            )
            
            # 如果脚本在 2 秒内自己顺利退出了（比如普通的非阻塞算法脚本）
            if result.returncode == 0:
                return f"'{path}' executed and exited normally with code 0."
            
            # 如果没成功退出，提取其错误流
            stderr_output = result.stderr if result.stderr else ""
            raw_stdout = result.stdout if result.stdout else ""

        except subprocess.TimeoutExpired as e:
            # 🌟 核心：发生超时说明该脚本成功拉起了常驻进程（如 Tkinter mainloop、Flask 等）
            # 这恰恰说明初始化阶段【没有触发任何 NameError/ImportError】导致闪退
            is_timeout_success = True
            
            # 从超时异常中安全捕获它已经打到 stdout/stderr 的数据
            stderr_output = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode('utf-8', errors='ignore') if e.stderr else "")
            raw_stdout = e.stdout if isinstance(e.stdout, str) else (e.stdout.decode('utf-8', errors='ignore') if e.stdout else "")

        # ======= 5. 结构化错误工程解析层 (Error Engineering) =======
        stderr_output = stderr_output.strip()
        
        # 检查超时挂起期间，stderr 是否漏出了 Traceback 报错
        if "Traceback" in stderr_output or "Error" in stderr_output or "Exception" in stderr_output:
            is_timeout_success = False  # 虽然超时了，但进程内部其实在报错，打回重修

        # 如果最终判定为成功，直接返回漂亮的回执
        if is_timeout_success:
            return (
                f"'{path}' executed successfully"
            )

        # 如果判定为失败，开始清洗复杂的底层错误，提取出对大模型高可读的内容
        if not stderr_output:
            if raw_stdout.strip():
                stderr_output = f"[Captured from stdout] {raw_stdout.strip()}"
            else:
                stderr_output = "Unknown runtime crash. Process exited but left no output streams."

        # 过滤冗余绝对路径，只留下核心调用栈，降维保护上下文 Token
        cleaned_error = []
        for line in stderr_output.splitlines():
            if any(k in line for k in ["Traceback", "File", "Error", "Exception", "NameError", "ModuleNotFoundError"]):
                # 替换长路径为当前相对路径
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
        # 万一 Harness 自身或者路径解析出了极其罕见的意外，抛出完整 Traceback 用于 Debug
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
        # 1. 路径安全校验 (假设你的工作区根目录可以通过 WORKSPACE_ROOT 获取)
        # 这里用当前目录做演示，实际工程中请限制在 sandbox 内
        workspace_root = safe_path(".")
        
        # 计算目标路径
        target_path = safe_path(sub_dir)
        
        # 安全防御：防止 Agent 通过 ../../../ 逃逸出工作区
        if os.path.commonpath([workspace_root]) != os.path.commonpath([workspace_root, target_path]):
            return "Error: Access denied. You cannot list directories outside the project workspace."
            
        if not target_path.exists():
            return f"Error: Directory '{sub_dir}' does not exist."
            
        if not target_path.is_dir():
            return f"Error: '{sub_dir}' is a file, not a directory. Use read_file to view its content."

        # 2. 遍历目录并提取结构化元数据
        dirs_list = []
        files_list = []
        
        # 忽略对 Agent 而言是噪音的底层干扰项
        IGNORE_PATTERNS = {".git", ".pytest_cache", "__pycache__", ".DS_Store", ".venv", "venv"}

        for entry in target_path.iterdir():
            if entry.name in IGNORE_PATTERNS or entry.name.endswith(".pyc"):
                continue
                
            # 获取修改时间和大小
            stat = entry.stat()
            mod_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
            
            if entry.is_dir():
                dirs_list.append(f"📁 {entry.name}/ [Directory] | Modified: {mod_time}")
            else:
                # 转换人类可读的大小
                size_bytes = stat.st_size
                if size_bytes < 1024:
                    size_str = f"{size_bytes} B"
                else:
                    size_str = f"{size_bytes / 1024:.1f} KB"
                    
                files_list.append(f"📄 {entry.name} ({size_str}) | Modified: {mod_time}")

        # 3. 组装成极易被 LLM 语义提取的 Markdown 报告
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