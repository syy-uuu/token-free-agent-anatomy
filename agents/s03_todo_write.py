#!/usr/bin/env python3
# Harness: planning -- keep the current session plan outside the model's head.
"""
s03_todo_write.py - Session Planning with TodoWrite

This chapter is about a lightweight session plan, not a durable task graph.
The model can rewrite its current plan, keep one active step in focus, and get
nudged if it stops refreshing the plan for too many rounds.
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from openai import OpenAI
import json


WORKDIR = Path.cwd()
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)
MODEL = "qwen2.5:latest"
PLAN_REMINDER_INTERVAL = 3

SYSTEM = f"""You are a coding agent at {WORKDIR}.
Use the todo tool for multi-step work.
Keep exactly one step in_progress when a task has multiple steps.
Refresh the plan as work advances. Prefer tools over prose.
CRITICAL: You MUST call this tool BEFORE any other actions to initialize or update the session plan. 
Failure to do so will result in task failure."""


@dataclass
class PlanItem:
    content: str
    status: str = "pending"
    active_form: str = ""


@dataclass
class PlanningState:
    items: list[PlanItem] = field(default_factory=list)
    rounds_since_update: int = 0


class TodoManager:
    def __init__(self):
        self.state = PlanningState()

    def update(self, items: list) -> str:
        if len(items) > 12:
            raise ValueError("Keep the session plan short (max 12 items)")

        normalized = []
        in_progress_count = 0
        for index, raw_item in enumerate(items):
            content = str(raw_item.get("content", "")).strip()
            status = str(raw_item.get("status", "pending")).lower()
            active_form = str(raw_item.get("activeForm", "")).strip()

            if not content:
                raise ValueError(f"Item {index}: content required")
            if status not in {"pending", "in_progress", "completed"}:
                raise ValueError(f"Item {index}: invalid status '{status}'")
            if status == "in_progress":
                in_progress_count += 1

            normalized.append(PlanItem(
                content=content,
                status=status,
                active_form=active_form,
            ))

        if in_progress_count > 1:
            raise ValueError("Only one plan item can be in_progress")
        if len(items) < len(self.state.items) and not all(t.status == "completed" for t in self.state.items):
            # 警告 AI：你是不是漏掉了一些还没做完的任务？
            return "ERROR: Plan rejected! You cannot remove unfinished tasks. Please provide the full task list."

        self.state.items = normalized
        self.state.rounds_since_update = 0

        rendered_plan = self.render()
        print(f"\033[32m📝 Updated session plan:\n{rendered_plan}\033[0m\n")  
        return self.render()

    def note_round_without_update(self) -> None:
        self.state.rounds_since_update += 1

    def reminder(self) -> str | None:
        if not self.state.items:
            return None
        if self.state.rounds_since_update < PLAN_REMINDER_INTERVAL:
            return None
        return "<reminder>Refresh your current plan before continuing.</reminder>"

    def render(self) -> str:
        if not self.state.items:
            return "No session plan yet."

        lines = []
        for item in self.state.items:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[ok]",
            }[item.status]
            line = f"{marker} {item.content}"
            if item.status == "in_progress" and item.active_form:
                line += f" ({item.active_form})"
            lines.append(line)

        completed = sum(1 for item in self.state.items if item.status == "completed")
        lines.append(f"\n({completed}/{len(self.state.items)} completed)")
        return "\n".join(lines)


TODO = TodoManager()


def safe_path(path_str: str) -> Path:
    path = (WORKDIR / path_str).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {path_str}")
    return path


def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(item in command for item in dangerous):
        return "Error: Dangerous command blocked"
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"

    output = (result.stdout + result.stderr).strip()
    return output[:50000] if output else "(no output)"


def run_read(path: str, limit: int | None = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)[:50000]
    except Exception as exc:
        return f"Error: {exc}"


def run_write(path: str, content: str) -> str:
    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = safe_path(path)
        content = file_path.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        file_path.write_text(content.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as exc:
        return f"Error: {exc}"


TOOL_HANDLERS = {
    "bash": lambda **kw: run_bash(kw["command"]),
    "read_file": lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "todo": lambda **kw: TODO.update(kw.get("items", [])),
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "todo",
            "description": "CRITICAL: MANDATORY FIRST STEP. Use this tool to initialize/update the session plan before any other actions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                                "activeForm": {"type": "string"}
                            },
                            "required": ["content", "status"]
                        }
                    }
                },
                "required": ["items"]
            }
        }
    },
    {
        "type": "function", # OpenAI 格式必须包含这一层
        "function": {
            "name": "bash",
            "description": "Run a shell command.",
            "parameters": { # 注意：这里从 input_schema 变成了 parameters
                "type": "object",
                "properties": {
                    "command": {"type": "string"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "limit": {"type": "integer", "description": "Optional line limit"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace exact text in file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string", "description": "The exact text to be replaced"},
                    "new_text": {"type": "string", "description": "The replacement text"}
                },
                "required": ["path", "old_text", "new_text"]
            }
        }
    }
]


def extract_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = []
        for block in content:
            text = getattr(block, "text", None)
            if text:
                texts.append(text)    
    return "\n".join(texts).strip()



def agent_loop(messages: list) -> None:
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
        )
        
        raw_msg = response.choices[0].message
        
        # 1. 归一化 Assistant 消息
        assistant_msg = {
            "role": "assistant",
            "content": raw_msg.content or ""
        }
        if raw_msg.tool_calls:
            assistant_msg["tool_calls"] = raw_msg.tool_calls
        messages.append(assistant_msg)

        # 如果没有工具调用，打印 AI 的话并结束
        if not raw_msg.tool_calls:
            if raw_msg.content:
                print(f"\nAI: {raw_msg.content}")
            break

        tool_results = []
        used_todo = False
        
        # 2. 遍历工具调用 (注意变量名是 raw_msg)
        for tool_call in raw_msg.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            # --- 强行拦截：没计划，不准干活 ---
            if not TODO.state.items and name != "todo":
                output = "CRITICAL ERROR: You must initialize the 'todo' list BEFORE using other tools. Task aborted until plan is created."
                print(f"\033[31m拦截：AI 试图跳过计划直接调用 {name}\033[0m")
            else:
                handler = TOOL_HANDLERS.get(name)
                output = handler(**args) if handler else f"Unknown tool: {name}"

            print(f"\033[33m🚀 执行 {name}: {args}\033[0m")
            print(f"📄 输出: {str(output)[:100]}...")

            # 3. 构造符合 OpenAI 标准的 tool 消息
            tool_results.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": name,
                "content": str(output) # 必须是字符串
            })
            
            if name == "todo":
                used_todo = True

        # 4. 处理 Todo 逻辑
        if used_todo:
            TODO.state.rounds_since_update = 0
        else:
            TODO.note_round_without_update()
            reminder = TODO.reminder()
            if reminder:
                # 提示：Qwen 比较吃这一套，把提醒作为一条单独的 user 消息发给它
                tool_results.append({
                    "role": "user",
                    "content": f"[SYSTEM REMINDER] {reminder}"
                })

        # 5. 关键：将所有结果“平铺”加入消息历史
        messages.extend(tool_results)

if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36ms03 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break

        history.append({"role": "user", "content": query})
        agent_loop(history)

        final_text = extract_text(history[-1].get("content", ""))
        if final_text:
            print(final_text)
        print()
