from .system_ops import BASH_SCHEMA, run_bash
from .file_ops import FILE_TOOLS_SCHEMAS, run_read, run_write, handle_mkdir, run_append_file, run_execute_test, run_list_directory, run_view_file_with_line_numbers, run_edit_file_by_lines
from .base import safe_path
# 1. Aggregate all Schemas for the LLM
STATIC_SCHEMAS = [BASH_SCHEMA] + FILE_TOOLS_SCHEMAS

# 2. Integrate all Runners into a single dictionary
STATIC_HANDLERS = {
    "bash":           lambda **kw: run_bash(kw.get("command", "")) if "command" in kw else "[Harness Error]: bash command key is missing.",
    
    # 🌟 既然底层自带安全锁，这里直接干净地原样转发参数
    "read_file":      lambda **kw: run_read(kw.get("path")),
    "write_file":     lambda **kw: run_write(kw.get("path"), kw.get("content")),
    "mkdir":          lambda **kw: handle_mkdir(kw),
    "append_file":    lambda **kw: run_append_file(path=kw.get("path"), text=kw.get("text") or kw.get("content")),
    
    "view_file_with_line_numbers": lambda **kw: run_view_file_with_line_numbers(kw.get("path")),
    "edit_file_by_lines":          lambda **kw: run_edit_file_by_lines(
        path=kw.get("path"),
        start_line=int(kw.get("start_line", 1)),
        end_line=int(kw.get("end_line", 1)),
        new_content=kw.get("new_content", "")
    ),
    "execute_test":   lambda **kw: run_execute_test(kw.get("path")),
    
    # 🌟 只有 list_directory 保持我们在上一轮做的相对路径特判拦截
    "list_directory": lambda **kw: run_list_directory(
        kw["sub_dir"] if kw.get("sub_dir") and kw["sub_dir"] != "." else "."
    )
}