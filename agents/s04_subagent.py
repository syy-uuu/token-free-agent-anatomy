#!/usr/bin/env python3
# Harness: context isolation -- protecting the model's clarity of thought.
"""
s04_subagent.py - Subagents

Spawn a child agent with fresh messages=[]. The child works in its own
context, sharing the filesystem, then returns only a summary to the parent.

    Parent agent                     Subagent
    +------------------+             +------------------+
    | messages=[...]   |             | messages=[]      |  <-- fresh
    |                  |  dispatch   |                  |
    | tool: task       | ---------->| while tool_use:  |
    |   prompt="..."   |            |   call tools     |
    |   description="" |            |   append results |
    |                  |  summary   |                  |
    |   result = "..." | <--------- | return last text |
    +------------------+             +------------------+
              |
    Parent context stays clean.
    Subagent context is discarded.

Key insight: "Fresh messages=[] gives context isolation. The parent stays clean."

Note: Real Claude Code also uses in-process isolation (not OS-level process
forking). The child runs in the same process with a fresh message array and
isolated tool context -- same pattern as this teaching implementation.

    Comparison with real Claude Code:
    +-------------------+------------------+----------------------------------+
    | Aspect            | This demo        | Real Claude Code                 |
    +-------------------+------------------+----------------------------------+
    | Backend           | in-process only  | 5 backends: in-process, tmux,    |
    |                   |                  | iTerm2, fork, remote             |
    | Context isolation | fresh messages=[]| createSubagentContext() isolates  |
    |                   |                  | ~20 fields (tools, permissions,  |
    |                   |                  | cwd, env, hooks, etc.)           |
    | Tool filtering    | manually curated | resolveAgentTools() filters from |
    |                   |                  | parent pool; allowedTools         |
    |                   |                  | replaces all allow rules         |
    | Agent definition  | hardcoded system | .claude/agents/*.md with YAML    |
    |                   | prompt           | frontmatter (AgentTemplate)      |
    +-------------------+------------------+----------------------------------+
"""


import re
import subprocess
from pathlib import Path
from openai import OpenAI
import json


WORKDIR = Path.cwd()
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)
MODEL = "qwen2.5:latest"

WORKDIR = Path.cwd()

SYSTEM = f"You are a coding agent at {WORKDIR}. Use the task tool to delegate exploration or subtasks."
SUBAGENT_SYSTEM = f"You are a coding subagent at {WORKDIR}. Complete the given task, then summarize your findings."


class AgentTemplate:
    """
    Parse agent definition from markdown frontmatter.

    Real Claude Code loads agent definitions from .claude/agents/*.md.
    Frontmatter fields: name, tools, disallowedTools, skills, hooks,
    model, effort, permissionMode, maxTurns, memory, isolation, color,
    background, initialPrompt, mcpServers.
    3 sources: built-in, custom (.claude/agents/), plugin-provided.
    """
    def __init__(self, path):
        self.path = Path(path)
        self.name = self.path.stem
        self.config = {}
        self.system_prompt = ""
        self._parse()

    def _parse(self):
        text = self.path.read_text()
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
        if not match:
            self.system_prompt = text
            return
        for line in match.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                self.config[k.strip()] = v.strip()
        self.system_prompt = match.group(2).strip()
        self.name = self.config.get("name", self.name)


# -- Tool implementations shared by parent and child --
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"

def run_read(path: str, limit: int = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"

def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes"
    except Exception as e:
        return f"Error: {e}"

def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        content = fp.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        fp.write_text(content.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


TOOL_HANDLERS = {
    "bash":       lambda **kw: run_bash(kw["command"]),
    "read_file":  lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":  lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
}

# Child gets all base tools except task (no recursive spawning)
CHILD_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute"}
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
                    "path": {"type": "string", "description": "Path to the file"},
                    "limit": {"type": "integer", "description": "Max lines to read"}
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
                    "path": {"type": "string", "description": "Path to the file"},
                    "content": {"type": "string", "description": "Content to write"}
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
                    "path": {"type": "string", "description": "Path to the file"},
                    "old_text": {"type": "string", "description": "The exact text to be replaced"},
                    "new_text": {"type": "string", "description": "The replacement text"}
                },
                "required": ["path", "old_text", "new_text"]
            }
        }
    }
]

def extract_text(content) -> str:
    texts=[]
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))  
    return "\n".join(texts).strip()

def flatten_messages(messages):
    new_messages = []
    for m in messages:
        # --- 核心修复：兼容对象和字典 ---
        # 如果 m 有 model_dump 方法，说明它是 OpenAI 对象，先转成字典
        if hasattr(m, "model_dump"):
            m = m.model_dump()
        # 如果 m 还是个对象（某些旧版本），尝试直接访问属性
        elif not isinstance(m, dict):
            m = {"role": getattr(m, "role", "assistant"), "content": getattr(m, "content", "")}

        role = m.get("role")
        content = m.get("content")

        if isinstance(content, list):
            # 提取文本片段
            text_str = "".join([
                item.get("text", "") 
                for item in content 
                if isinstance(item, dict) and item.get("type") == "text"
            ])
            new_messages.append({"role": role, "content": text_str})
        else:
            # 确保 content 始终是字符串（处理 None 的情况）
            new_messages.append({"role": role, "content": str(content or "")})
            
    return new_messages



# -- Subagent: fresh context, filtered tools, summary-only return --
def run_subagent(prompt: str) -> str:
    sub_messages = [{"role": "user", "content": prompt}]  # fresh context
    for _ in range(30):  # safety limit
        response = client.chat.completions.create(
            model=MODEL,system=SUBAGENT_SYSTEM,
            messages=flatten_messages(sub_messages),
            tools=CHILD_TOOLS,
        )
        sub_messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            break
        results = []
        for block in response.content:
            if block.type == "tool_use":
                handler = TOOL_HANDLERS.get(block.name)
                output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)[:50000]})
        sub_messages.append({"role": "user", "content": results})
    # Only the final text returns to the parent -- child context is discarded
    return "".join(b.text for b in response.content if hasattr(b, "text")) or "(no summary)"


# -- Parent tools: base tools + task dispatcher --
PARENT_TOOLS = CHILD_TOOLS + [
    {
        "type": "function",
        "function": {
            "name": "task",
            "description": "DELEGATE complex tasks to a specialized subagent. USE THIS for multi-step projects, file creation, or data processing. It is the most efficient way to get work done."
            "IMPORTANT: You MUST call a tool in EVERY turn until the task is physically completed. Telling the user what you 'will do' is NOT enough. If you don't call a tool, I will assume you are stuck.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string", 
                        "description": "Complete instructions for the subagent. Be specific about filenames and goals."
                    },
                    "description": {
                        "type": "string", 
                        "description": "A high-level summary of what the subagent is doing."
                    }
                },
                "required": ["prompt"]
            }
        }
    }
]


def agent_loop(messages: list):
    while True:
        # 1. 发起请求 (使用你之前写好的 flatten_messages)
        response = client.chat.completions.create(
            model=MODEL,
            messages=flatten_messages(messages),
            tools=PARENT_TOOLS,
        )
        
        message = response.choices[0].message
        messages.append(message.model_dump()) # 直接添加 message 对象，OpenAI 库会自动处理

        # 2. 打印 Master 的话 (解决你的“沉默”问题)
        if message.content:
            print(f"\nMaster: {message.content}")

        # 3. 判断是否需要调用工具 (OpenAI 的逻辑是判断 tool_calls 是否存在)
        if not message.tool_calls:
            # 如果没有工具调用且没有文字内容，给个保底提示
            if not message.content:
                print("\nMaster: (任务已完成)")
            return

        # 4. 处理工具调用
        for tool_call in message.tool_calls:
            name = tool_call.function.name
            # 解析 JSON 参数

            args = json.loads(tool_call.function.arguments)
            
            if name == "task":
                desc = args.get("description", "subtask")
                prompt = args.get("prompt", "")
                print(f"🚀 启动子智能体 [{desc}]: {prompt[:60]}...")
                output = run_subagent(prompt)
            else:
                handler = TOOL_HANDLERS.get(name)
                output = handler(**args) if handler else f"Unknown tool: {name}"
            
            # 打印执行反馈
            print(f"✅ 工具 [{name}] 返回: {str(output)[:100]}...")

            # 5. 按照 OpenAI 格式回传工具结果
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": name,
                "content": str(output)
            })


if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36ms04 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break

        history.append({"role": "user", "content": query})
        agent_loop(history)

    last_msg = history[-1]
    # 如果是字典用 .get()，如果是对象用 .content
    last_content = last_msg.get("content", "") if isinstance(last_msg, dict) else last_msg.content

    final_text = extract_text(last_content)
    if final_text:
        print(f"\nFinal Result: {final_text}")
    print()
