from .system_ops import BASH_SCHEMA, run_bash
from .file_ops import FILE_TOOLS_SCHEMAS, run_read, run_write, run_edit, handle_mkdir, run_append_file, run_execute_test, run_list_directory

# 1. Aggregate all Schemas for the LLM
STATIC_SCHEMAS = [BASH_SCHEMA] + FILE_TOOLS_SCHEMAS

# 2. Integrate all Runners into a single dictionary
STATIC_HANDLERS = {
    "bash":       lambda **kw: run_bash(kw.get("command", "")) if "command" in kw else "[Harness Error]: bash command key is missing. Did you mean to use 'command' instead of 'path'?",
    "read_file":  lambda **kw: run_read(kw["path"]),
    "write_file": lambda **kw: run_write(kw.get("path"), kw.get("content")),
    "mkdir":      lambda **kw: handle_mkdir(kw),
    "append_file": lambda **kw: run_append_file(
        path=kw.get("path"), 
        text=kw.get("text") or kw.get("content")
    ),
    "edit_file":  lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "execute_test": lambda **kw: run_execute_test(kw.get("path")),
    "list_directory": lambda **kw: run_list_directory(kw.get("sub_dir", "."))
}