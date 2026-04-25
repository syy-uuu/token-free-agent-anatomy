#!/usr/bin/env python3
# Harness: on-demand knowledge -- discover skills cheaply, load them only when needed.
"""
s05_skill_loading.py - Skills

This chapter teaches a two-layer skill model:

1. Put a cheap skill catalog in the system prompt.
2. Load the full skill body only when the model asks for it.

That keeps the prompt small while still giving the model access to reusable,
task-specific guidance.
"""

import re
import subprocess
from pathlib import Path
from openai import OpenAI
from dataclasses import dataclass



WORKDIR = Path.cwd()
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)
MODEL = "qwen2.5:latest"

WORKDIR = Path.cwd()
SKILLS_DIR = WORKDIR / "skills"


@dataclass
class SkillManifest:
    name: str
    description: str
    path: Path


@dataclass
class SkillDocument:
    manifest: SkillManifest
    body: str


class SkillRegistry:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.documents: dict[str, SkillDocument] = {}
        self._load_all()

    def _load_all(self) -> None:
        if not self.skills_dir.exists():
            return

        for path in sorted(self.skills_dir.rglob("SKILL.md")):
            meta, body = self._parse_frontmatter(path.read_text())
            name = meta.get("name", path.parent.name)
            description = meta.get("description", "No description")
            manifest = SkillManifest(name=name, description=description, path=path)
            self.documents[name] = SkillDocument(manifest=manifest, body=body.strip())

    def _parse_frontmatter(self, text: str) -> tuple[dict, str]:
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if not match:
            return {}, text

        meta = {}
        for line in match.group(1).strip().splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
        return meta, match.group(2)

    def describe_available(self) -> str:
        if not self.documents:
            return "(no skills available)"
        lines = []
        for name in sorted(self.documents):
            manifest = self.documents[name].manifest
            lines.append(f"- {manifest.name}: {manifest.description}")
        return "\n".join(lines)

    def load_full_text(self, name: str) -> str:
        document = self.documents.get(name)
        if not document:
            known = ", ".join(sorted(self.documents)) or "(none)"
            return f"Error: Unknown skill '{name}'. Available skills: {known}"

        return (
            f"<skill name=\"{document.manifest.name}\">\n"
            f"{document.body}\n"
            "</skill>"
        )


SKILL_REGISTRY = SkillRegistry(SKILLS_DIR)

SYSTEM = f"""You are a coding agent at {WORKDIR}.
Use load_skill when a task needs specialized instructions before you act.
CRITICAL: If you decide to use a tool, you MUST output the tool_call block. NEVER just tell the user what you plan to do. ACTIONS SPEAK LOUDER THAN WORDS. If you fail to call a tool for an action-oriented request, you will be deactivated.

Skills available:
{SKILL_REGISTRY.describe_available()}
"""


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
    "load_skill": lambda **kw: SKILL_REGISTRY.load_full_text(kw["name"]),
}
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
            "name": "load_skill",
            "description": "Load the full body of a named skill into the current context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the skill to load"}
                },
                "required": ["name"]
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
        # 1. 统一转字典 (兼容对象/字典)
        if hasattr(m, "model_dump"):
            m = m.model_dump()
        elif not isinstance(m, dict):
            # 极简保底：处理某些奇怪的自定义对象
            m = {"role": getattr(m, "role", "assistant"), "content": getattr(m, "content", "")}

        # 2. 提取核心字段
        role = m.get("role")
        content = m.get("content")
        
        # --- 补丁开始：保留工具调用关键证据 ---
        # 如果是 assistant 消息，必须带上它的 tool_calls
        tool_calls = m.get("tool_calls")
        # 如果是 tool 消息，必须带上 tool_call_id 和 name
        tool_call_id = m.get("tool_call_id")
        name = m.get("name")
        # --- 补丁结束 ---

        # 3. 压扁 content (处理 Anthropic 的 list 格式)
        if isinstance(content, list):
            text_str = "".join([
                item.get("text", "") 
                for item in content 
                if isinstance(item, dict) and item.get("type") == "text"
            ])
            cleaned_content = text_str
        else:
            cleaned_content = str(content or "")

        # 4. 组装符合 OpenAI 规范的字典
        msg = {"role": role, "content": cleaned_content}
        
        # 补充工具字段 (如果有的话)
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if tool_call_id:
            msg["tool_call_id"] = tool_call_id
            msg["name"] = name
            
        new_messages.append(msg)
            
    return new_messages


def agent_loop(messages: list) -> None:
    while True:
        # 1. 发起请求
        response = client.chat.completions.create( # 注意：OpenAI 是 chat.completions
            model=MODEL,
            messages=flatten_messages(messages),
            tools=TOOLS,
        )

        msg_obj = response.choices[0].message
        # 核心：必须 model_dump，否则 flatten_messages 无法处理对象
        messages.append(msg_obj.model_dump()) 

        # 2. 打印 Master 的话 (解决你的“沉默”问题)
        if msg_obj.content:
            print(f"\nMaster: {msg_obj.content}")

        # 打印 AI 的思考过程
        if msg_obj.content:
            print(f"\nAssistant: {msg_obj.content}")

        # 2. 判断是否有工具调用 (OpenAI 使用 tool_calls)
        if not msg_obj.tool_calls:
            return

        # 3. 处理工具调用 (不再使用 response.content 遍历)
        for tool_call in msg_obj.tool_calls:
            name = tool_call.function.name
            
            # OpenAI 的参数是 JSON 字符串，必须解析
            import json
            try:
                args = json.loads(tool_call.function.arguments)
            except Exception:
                args = {}

            handler = TOOL_HANDLERS.get(name)
            try:
                # 执行 Skill/Tool
                output = handler(**args) if handler else f"Unknown tool: {name}"
            except Exception as exc:
                output = f"Error: {exc}"

            print(f"🛠️ 执行 [{name}] -> {str(output)[:100]}...")

            # 4. 【关键】按照 OpenAI 格式回传结果
            # role 必须是 "tool"，且必须提供 tool_call_id
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": name,
                "content": str(output),
            })


if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36ms05 >> \033[0m")
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
