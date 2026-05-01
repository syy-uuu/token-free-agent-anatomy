#!/usr/bin/env python3
# Harness: compression -- keep the active context small enough to keep working.
"""
s06_context_compact.py - Context Compact

This teaching version keeps the compact model intentionally small:

1. Large tool output is persisted to disk and replaced with a preview marker.
2. Older tool results are micro-compacted into short placeholders.
3. When the whole conversation gets too large, the agent summarizes it and
   continues from that summary.

The goal is not to model every production branch. The goal is to make the
active-context idea explicit and teachable.
"""

import subprocess
from pathlib import Path
from openai import OpenAI
from dataclasses import dataclass, field
import json
import time

WORKDIR = Path.cwd()
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)
MODEL = "qwen2.5:latest"

SYSTEM = (
    f"You are a coding agent at {WORKDIR}. "
    "Keep working step by step, and use compact if the conversation gets too long."
)

CONTEXT_LIMIT = 5000
KEEP_RECENT_TOOL_RESULTS = 3
PERSIST_THRESHOLD = 3000
PREVIEW_CHARS = 2000
TRANSCRIPT_DIR = WORKDIR / ".transcripts"
TOOL_RESULTS_DIR = WORKDIR / ".task_outputs" / "tool-results"


@dataclass
class CompactState:
    has_compacted: bool = False
    last_summary: str = ""
    recent_files: list[str] = field(default_factory=list)


def estimate_context_size(messages: list) -> int:
    return len(str(messages))


def track_recent_file(state: CompactState, path: str) -> None:
    if path in state.recent_files:
        state.recent_files.remove(path)
    state.recent_files.append(path)
    if len(state.recent_files) > 5:
        state.recent_files[:] = state.recent_files[-5:]


def persist_large_output(tool_use_id: str, output: str) -> str:
    if len(output) <= PERSIST_THRESHOLD:
        return output

    TOOL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = TOOL_RESULTS_DIR / f"{tool_use_id}.txt"
    if not stored_path.exists():
        stored_path.write_text(output)

    preview = output[:PREVIEW_CHARS]
    rel_path = stored_path.relative_to(WORKDIR)
    return (
        "<persisted-output>\n"
        f"Full output saved to: {rel_path}\n"
        "Preview:\n"
        f"{preview}\n"
        "</persisted-output>"
    )


def collect_tool_result_blocks(messages: list) -> list[tuple[int, int, dict]]:
    blocks = []
    for message_index, message in enumerate(messages):
        content = message.get("content")
        if message.get("role") != "user" or not isinstance(content, list):
            continue
        for block_index, block in enumerate(content):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                blocks.append((message_index, block_index, block))
    return blocks


def micro_compact(messages: list) -> list:
    tool_results = collect_tool_result_blocks(messages)
    if len(tool_results) <= KEEP_RECENT_TOOL_RESULTS:
        return messages

    for _, _, block in tool_results[:-KEEP_RECENT_TOOL_RESULTS]:
        content = block.get("content", "")
        if not isinstance(content, str) or len(content) <= 120:
            continue
        block["content"] = "[Earlier tool result compacted. Re-run the tool if you need full detail.]"
    return messages


def write_transcript(messages: list) -> Path:
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"
    with path.open("w") as handle:
        for message in messages:
            handle.write(json.dumps(message, default=str) + "\n")
    return path


def summarize_history(messages: list) -> str:
    # 将列表转换为 JSON 字符串作为输入，注意不要超出模型的单次处理限制
    conversation = json.dumps(messages, default=str)[:80000]
    
    prompt = (
        "Summarize this coding-agent conversation so work can continue.\n"
        "Preserve:\n"
        "1. The current goal\n"
        "2. Important findings and decisions\n"
        "3. Files read or changed\n"
        "4. Remaining work\n"
        "5. User constraints and preferences\n"
        "Be compact but concrete.\n\n"
        f"{conversation}"
    )

    # 修复点：改用 OpenAI 的调用方式
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
    )
    
    # 修复点：OpenAI 的返回对象获取内容的方式也不同
    return response.choices[0].message.content.strip()


def compact_history(messages: list, state: CompactState, focus: str | None = None) -> list:
    transcript_path = write_transcript(messages)
    print(f"[transcript saved: {transcript_path}]")

    summary = summarize_history(messages)
    if focus:
        summary += f"\n\nFocus to preserve next: {focus}"
    if state.recent_files:
        recent_lines = "\n".join(f"- {path}" for path in state.recent_files)
        summary += f"\n\nRecent files to reopen if needed:\n{recent_lines}"

    state.has_compacted = True
    state.last_summary = summary

    return [{
        "role": "user",
        "content": (
            "This conversation was compacted so the agent can continue working.\n\n"
            f"{summary}"
        ),
    }]


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

def run_compact(focus: str | None = None) -> str:
    return "This is a manual compact trigger. The agent should summarize the conversation so far to free up context space."



TOOLS = [
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
    },
    {
        "type": "function",
        "function": {
            "name": "compact",
            "description": "Summarize earlier conversation so work can continue in a smaller context..",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "se this tool when the conversation becomes very long or complex. It will summarize the history to free up context space while preserving key progress."}
                },
                "required": ["name"]
            }       
        }
    }
]

TOOL_HANDLERS = {
    "bash": lambda **kw: run_bash(kw["command"]),
    "read_file": lambda **kw: run_read(kw.get("path"), kw.get("limit")),
    "write_file": lambda **kw: run_write(kw.get("path"), kw.get("content")),
    "edit_file": lambda **kw: run_edit(kw.get("path"), kw.get("old_text"), kw.get("new_text")),
    "compact": lambda **kw: "Memory reorganization sequence initiated."
}

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


def agent_loop(messages: list, state: CompactState) -> None:
    while True:
        messages[:] = micro_compact(messages)

        if estimate_context_size(messages) > CONTEXT_LIMIT:
            print("[auto compact]")
            messages[:] = compact_history(messages, state)

        response = client.chat.completions.create(
            model=MODEL,
            messages=flatten_messages(messages),
            tools=TOOLS,
        )
        
        message = response.choices[0].message
        messages.append(message.model_dump()) # 直接添加 message 对象，OpenAI 库会自动处理

        # 2. 打印 Master 的话 (解决你的“沉默”问题)
        if message.content:
            print(f"\nMaster: {message.content}")
        
        # 存入原始 history，model_dump() 确保保留了 tool_calls 结构
        messages.append(message.model_dump()) 

        # 打印对话
        if message.content:
            print(f"\nMaster: {message.content}")

        # --- 3. 判断是否需要执行动作 ---
        if not message.tool_calls:
            # 如果模型没有下达任何工具指令，说明任务阶段性完成，停下来等用户输入
            return

        manual_compact = False
        compact_focus = None
        for tool_call in message.tool_calls:
            name = tool_call.function.name
            # 关键：Qwen 返回的是字符串，需要转字典
            
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}
            
            handler = TOOL_HANDLERS.get(name)
            if handler:
                # 依然可以使用 ** 解包，非常方便
                output = handler(**args)
            else:
                output = f"Unknown tool: {name}"

            print(f"\033[33m🚀 执行 {name}: {args}\033[0m")
            print(f"📄 输出: {str(output)[:100]}...")

            if name == "compact":
                manual_compact = True
                compact_focus = args.get("name") or args.get("focus")

            print(f"\033[33m🚀 执行 {name}: {args}\033[0m")


            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": name,
                "content": str(output)
            })

        if manual_compact:
            print("[manual compact]")
            messages[:] = compact_history(messages, state, focus=compact_focus)


if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36ms06 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break

        history.append({"role": "user", "content": query})
        agent_loop(history, CompactState())

    last_msg = history[-1]
    # 如果是字典用 .get()，如果是对象用 .content
    last_content = last_msg.get("content", "") if isinstance(last_msg, dict) else last_msg.content

    final_text = extract_text(last_content)
    if final_text:
        print(f"\nFinal Result: {final_text}")
    print()
