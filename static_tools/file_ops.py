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
        "name": "edit_file",
        "description": "CRITICAL: Surgical precision edit ONLY. Modifies a specific local block of text within an existing file. DO NOT provide the entire file content in 'old_text' or 'new_text'. Only provide the exact 3-5 lines that need to change plus minimal surrounding context. For multiple changes, call this tool multiple times sequentially.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string", 
                    "description": "Relative path to the file."
                },
                "old_text": {
                    "type": "string", 
                    "description": "The exact existing text block to find. Must be copied verbatim from the file, including identical indentation, spaces, and newlines. Typically 1-5 lines."
                },
                "new_text": {
                    "type": "string", 
                    "description": "The new text block to replace 'old_text' with. Keep it minimal and focused only on the fix."
                }
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
        "description": "CRITICAL VERIFICATION TOOL. Executes the specified Python script in a controlled sandbox to check for syntax errors, compilation failures, and runtime Exceptions (e.g., NameError, ImportError). Always call this tool immediately after modifying any script to ensure your changes didn't break the application.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string", 
                    "description": "Relative path to the Python file you want to test (e.g., 'gui_code.py')."
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


def run_edit(path: str, old_text: str, new_text: str) -> str:
    """
    Advanced Surgical Edit. 
    Line-by-line whitespace-insensitive sliding window matcher.
    Completely fixes the control flow and newline injection bugs.
    """
    try:
        full_path = safe_path(path)
        if not full_path.exists():
            return f"Error: File '{path}' not found for editing."
            
        file_content = full_path.read_text(encoding="utf-8")
        file_lines = file_content.splitlines()
        
        # 1. 拦截空调用
        if not old_text.strip():
            return "Error: 'old_text' cannot be empty. Specify what to replace."

        # 2. 限制单次动刀的硬性范围 (防止模型失控全量重写)
        raw_old_lines_count = len(old_text.splitlines())
        if raw_old_lines_count > 100:
            return (f"Error: Single edit block is limited to 100 lines. ")

        # 3. 将大模型传来的 old_text 清洗为纯净的行列表（忽略首尾空行和空格）
        old_lines = [line.strip() for line in old_text.splitlines() if line.strip()]
        if not old_lines:
            return "Error: 'old_text' contains no effective executable code lines to match."
            
        matched_start_idx = -1
        match_count = 0
        n_old = len(old_lines)
        
        # 4. 核心核心：使用滑动窗口在原文件中寻找内容一致、忽略缩进和换行的唯一代码块
        for i in range(len(file_lines) - n_old + 1):
            window = [line.strip() for line in file_lines[i:i+n_old] if line.strip()]
            if len(window) == n_old and window == old_lines:
                match_count += 1
                if matched_start_idx == -1:
                    matched_start_idx = i

        # 5. 针对滑窗匹配结果进行精准的通用报错引导
        if match_count == 0:
            return (f"Error: Could not find the specified code block in '{path}'. "
                    f"The system scanned line-by-line ignoring leading/trailing spaces but still found NO match. "
                    f"Please read the file again to ensure the code you want to change actually exists verbatim.")
                    
        if match_count > 1:
            return (f"Error: Found {match_count} identical matches for this code block. "
                    f"The system cannot safely determine which one to replace. "
                    f"Please include 2-3 extra surrounding lines (before or after) to make 'old_text' unique.")

        # 6. 物理外科手术式切片替换 (完整保留原文件除了被替换块之外的所有原始换行和换行符)
        raw_file_lines = file_content.splitlines(keepends=True)
        
        # 将新代码转化为带有合适换行符的行列表
        new_lines_list = [l + "\n" for l in new_text.splitlines()]
        if not new_lines_list:
            new_lines_list = ["\n"]
            
        # 在物理行号上执行直接切除和植入
        raw_file_lines[matched_start_idx : matched_start_idx + n_old] = new_lines_list
        
        # 重新拼接落盘
        full_path.write_text("".join(raw_file_lines), encoding="utf-8")
        
        return f" File '{path}' surgical edit completed."

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
        return f"OBSERVATION: Directory '{path_str}' created/existed."
    except ValueError as ve:
        # 专门拦截并优雅返回安全越权报错，直接把异常甩回大模型脸上，警示它越界了
        return f"ERROR: Security Violation. {str(ve)}"
        
    except Exception as e:
        # 兜底其余系统级物理报错（如磁盘满、无权限等）
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