from static_tools.base import safe_path
import os
import py_compile
import subprocess
import sys
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
        return f"Success: File '{path}' written successfully."
    except Exception as e:
        return f"Error writing file: {str(e)}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        full_path = safe_path(path)
        if not full_path.exists():
            return f"Error: File '{path}' not found for editing."
        
        content = full_path.read_text(encoding="utf-8")
        
        # === 鲁棒性升级：处理 Qwen 脑补的换行符 ===
        if old_text not in content:
            # 尝试一：如果是因为尾部多写了换行符或空格，帮它 strip() 后再试一次
            stripped_old = old_text.strip()
            if stripped_old and stripped_old in content:
                # 找到原文件中真正对应的带有真实换行符的那个片段
                # 这一步是为了找出原文件里那一段到底长啥样
                lines = content.splitlines()
                stripped_lines = stripped_old.splitlines()
                
                # 寻找连续匹配的行
                for i in range(len(lines) - len(stripped_lines) + 1):
                    if [line.strip() for line in lines[i:i+len(stripped_lines)]] == [sl.strip() for sl in stripped_lines]:
                        # 锁定原文件中的真实片段（包括它本来的换行和缩进）
                        actual_old_text = "\n".join(lines[i:i+len(stripped_lines)])
                        # 用原文件中真实的片段来进行替换
                        old_text = actual_old_text
                        break
            else:
                # 实在找不到了，再抛出你写好的高情商报错
                return (f"Error: Could not find the exact 'old_text' block in '{path}'. "
                        f"Your provided 'old_text' has {len(old_text.splitlines())} lines. "
                        f"Please use a read tool to check the exact newlines and spaces.")
                    
        
        # 2. 拦截行数过多的全量替换行为 (Hard Limit: 比如限制单次改动范围不超过30行)
        old_lines_count = len(old_text.splitlines())
        if old_lines_count > 30:
            return (f"Error: Single edit block is too large ({old_lines_count} lines). "
                    f"To prevent hallucination, you are prohibited from rewriting large blocks. "
                    f"Please narrow down your 'old_text' to ONLY the specific 2-5 lines that need changes.")

        # 3. 检查 old_text 是否存在
        if old_text not in content:
            return (f"Error: Could not find the exact 'old_text' block in '{path}'. "
                    f"Please view the file again to check the exact indentation, spaces, and spelling. "
                    f"Make sure you copied it verbatim.")
        
        # 4. 关键：防止多处误伤
        match_count = content.count(old_text)
        if match_count > 1:
            return (f"Error: The 'old_text' block you provided was found {match_count} times in the file. "
                    f"The system cannot safely determine which one to replace. "
                    f"Please include 2-3 extra lines of surrounding code (before or after) in both 'old_text' and 'new_text' to make it unique.")
        
        # 5. 执行替换（指定 count=1 确保绝对安全）
        new_content = content.replace(old_text, new_text, 1)
        full_path.write_text(new_content, encoding="utf-8")
        
        return f"Success: File '{path}' updated locally and precisely."
        
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
            
        return f"Success: Successfully appended {len(text.splitlines())} lines to the end of '{path}'."
        
    except Exception as e:
        return f"Error appending to file: {str(e)}"
    


def run_execute_test(path: str) -> str:
    """
    Executes the python file to catch runtime errors.
    Completely immune to NoneType strip/lstrip errors when scripts run successfully.
    """
    if path is None or not str(path).strip():
        return (
            "Error: Missing required argument 'path'. "
            "You must provide a valid file path string to execute_test"
        )
        
    try:
        full_path = safe_path(path)
        if not full_path.exists():
            return f"Error: File '{path}' not found."
            
        if not path.endswith(".py"):
            return f"Error: 'execute_test' can only test Python (.py) files."

        # ======= 1. 静态编译检查 =======
        try:
            py_compile.compile(str(full_path), doraise=True)
        except py_compile.PyCompileError as e:
            return f"❌ TEST FAILED: Compilation/Syntax Error!\n--------------------------------------------------\n{str(e.msg)}"

        # ======= 2. 动态注入防卡死补丁并执行 =======
        script_content = full_path.read_text(encoding="utf-8")
        
        test_wrapper = (
            "import tkinter\n"
            "original_tk = tkinter.Tk\n"
            "def patched_tk(*args, **kwargs):\n"
            "    root = original_tk(*args, **kwargs)\n"
            "    root.after(500, root.destroy)\n"
            "    return root\n"
            "tkinter.Tk = patched_tk\n"
        )
        test_code = test_wrapper + script_content

        result = subprocess.run(
            [sys.executable, "-c", test_code],
            capture_output=True,
            text=True,
            timeout=5
        )

        # ======= 3. 返回值解析（核心修复防御点） =======
        # 先安全提取 stdout 和 stderr，只要是 None 就强制变为空字符串
        raw_stderr = result.stderr if result.stderr is not None else ""
        raw_stdout = result.stdout if result.stdout is not None else ""
        
        # 正常顺利退出的情况
        if result.returncode == 0:
            return (
                f"✅ TEST SUCCESS: '{path}' executed successfully.\n"
            )

        # 异常崩溃退出的情况 (returncode != 0)
        stderr_output = raw_stderr.strip()
        if not stderr_output:
            if raw_stdout.strip():
                stderr_output = f"[Captured from stdout] {raw_stdout.strip()}"
            else:
                stderr_output = f"Unknown runtime crash. Process exited with code {result.returncode} but left no logs."

        # 报错清洗过滤
        cleaned_error = []
        for line in stderr_output.splitlines():
            if any(k in line for k in ["Traceback", "File", "Error", "Exception", "NameError"]):
                cleaned_line = line.replace(str(full_path.parent), ".")
                cleaned_error.append(cleaned_line)
        
        error_report = "\n".join(cleaned_error) if cleaned_error else stderr_output

        return (
            f"❌ TEST FAILED: Runtime Exception occurred!\n"
            f"--------------------------------------------------\n"
            f"{error_report}\n"
            f"--------------------------------------------------\n"
            f"💡 Hint: Check local variable scopes, indents, or cross-function definitions."
        )

    except subprocess.TimeoutExpired:
        return f"⚠️ Test Warning: Execution timed out. Possible infinite loop."
    except Exception as e:
        # 万一工具自身报错，把整个异常堆栈打出来，方便 debug 到底是哪行 NoneType
        import traceback
        return f"Error executing test (Harness Internal Error): {str(e)}\nDetails:\n{traceback.format_exc()}"


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