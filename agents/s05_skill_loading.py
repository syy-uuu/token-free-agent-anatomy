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
import json


WORKDIR = Path.cwd()
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)
MODEL = "qwen2.5:latest"

SKILLS_DIR = WORKDIR / "skills"

ACTIVE_SKILLS = set()  # 存储已加载的技能名称，如 {"code-review", "pdf"}

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
        self.documents = {}
        self._load_all()

    def _load_all(self):
        if not self.skills_dir.exists(): return
        for path in sorted(self.skills_dir.rglob("SKILL.md")):
            # 这里的解析逻辑保持不变，但我们需要在 body 里寻找 JSON 定义
            meta, body = self._parse_frontmatter(path.read_text())
            name = meta.get("name", path.parent.name)
            self.documents[name] = {
                "manifest": {"name": name, "description": meta.get("description", "")},
                "body": body.strip(),
                "tools": self._extract_tools(body) # 新增：解析出 OpenAI 格式的 tools
            }

    def _extract_tools(self, body: str) -> list:
        """
        通用技巧：在 SKILL.md 里用 ```json 块标记该技能提供的 tools 定义
        """
        tools = []
        # 匹配 ```json ... ``` 块
        matches = re.findall(r"```json\n(.*?)\n```", body, re.DOTALL)
        for m in matches:
                    try:
                        data = json.loads(m)
                        # 兼容 {"tools": [...]} 这种常见的包装格式
                        if isinstance(data, dict) and "tools" in data:
                            tools.extend(data["tools"])
                        elif isinstance(data, list): 
                            tools.extend(data)
                        elif isinstance(data, dict): 
                            tools.append(data)
                    except: 
                        continue
        return tools

    def get_skill_tools(self, name: str) -> list:
        skill = self.documents.get(name)
        # 确保返回的是一个列表给 current_tools.extend()
        return skill if isinstance(skill, list) else skill.get("tools", [])
    
    def load_full_text(self, name: str) -> str:
            """这是 load_skill 工具对应的底层逻辑：读取文档全文"""
            # 从你之前定义的 documents 字典里拿数据
            document = self.documents.get(name)
            if not document:
                known = ", ".join(sorted(self.documents.keys())) or "(none)"
                return f"Error: Unknown skill '{name}'. Available skills: {known}"

            # 返回符合 OpenAI/Claude 逻辑的文本块
            return (
                f"<skill name=\"{name}\">\n"
                f"{document['body']}\n"
                "</skill>"
            )
    # 原有的 describe_available 和 load_full_text 保持兼容
    def describe_available(self):
        return "\n".join([f"- {k}: {v['manifest']['description']}" for k, v in self.documents.items()])

    def _parse_frontmatter(self, text: str):
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if not match: return {}, text
        meta = {l.split(":", 1)[0].strip(): l.split(":", 1)[1].strip() 
                for l in match.group(1).strip().splitlines() if ":" in l}
        return meta, match.group(2)


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

def run_load_skill(name: str) -> str:
    content = SKILL_REGISTRY.load_full_text(name)
    
    if not content.startswith("Error"):
        ACTIVE_SKILLS.add(name)
        
        # --- 注入强制引导信息 ---
        instruction = (
            f"\n\n[SYSTEM NOTICE]\n"
            f"The skill '{name}' has been integrated into your KNOWLEDGE BASE.\n"
            f"1. You now possess all the expertise described in the <skill_knowledge> block above.\n"
            f"2. IMPORTANT: This skill provides NO specialized tools. You must apply this new "
            f"knowledge using your EXISTING BASE TOOLS: 'write_file', 'bash', 'read_file'.\n"
            f"3. Example: To build the MCP server you just learned about, call 'write_file' to "
            f"save the code to a relative path like './server.py'."
        )
        
        full_response = content + instruction
        print(f"✅ 技能已激活: {name}")
        return full_response
    
    return content



TOOL_HANDLERS = {
    "bash": lambda **kw: run_bash(kw["command"]),
    "read_file": lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "load_skill": lambda **kw: run_load_skill(kw["name"]),
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

def run_skill_script(tool_name: str, args: dict) -> str:
    # 遍历所有已激活的技能，寻找对应的脚本
    for skill_name in ACTIVE_SKILLS:
        # 路径规则：skills/{skill_name}/scripts/{tool_name}.py
        script_path = Path("skills") / skill_name / "scripts" / f"{tool_name}.py"
        
        if script_path.exists():
            import subprocess
            # 执行脚本，并将 args 转为 JSON 字符串作为命令行参数
            try:
                result = subprocess.run(
                    ["python", str(script_path), json.dumps(args)],
                    capture_output=True, text=True, timeout=30
                )
                return result.stdout if result.returncode == 0 else f"Script Error: {result.stderr}"
            except Exception as e:
                return f"Execution failed: {str(e)}"
    
    return f"Error: No .py script found for tool '{tool_name}' in active skills."


def agent_loop(messages: list) -> None:
    """
    S05 核心全自动循环：支持 Skill 的动态热插拔
    """
    while True:
        current_tools = list(TOOLS) 
        
        # 2. 动态追加已激活技能的工具
        for skill_name in ACTIVE_SKILLS:
            skill_tools = SKILL_REGISTRY.get_skill_tools(skill_name)
            current_tools.extend(skill_tools)

        api_messages = [{"role": "system", "content": SYSTEM}] + flatten_messages(messages)

        api_params = {
                    "model": MODEL,
                    "messages": api_messages,
                    "temperature": 0
                }
        
        # --- 核心判断：只有工具箱不为空，才把 tools 塞进请求 ---
        if current_tools:
            api_params["tools"] = current_tools
        # --------------------------------------------------
        # 3. 发起请求（使用 ** 解包参数）
        response = client.chat.completions.create(**api_params)

        msg_obj = response.choices[0].message
        
        # 存入原始 history，model_dump() 确保保留了 tool_calls 结构
        messages.append(msg_obj.model_dump()) 

        # 打印对话
        if msg_obj.content:
            print(f"\nMaster: {msg_obj.content}")

        # --- 3. 判断是否需要执行动作 ---
        if not msg_obj.tool_calls:
            # 如果模型没有下达任何工具指令，说明任务阶段性完成，停下来等用户输入
            return

        # --- 4. 循环处理本轮所有的工具调用 ---
        for tool_call in msg_obj.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            if name in TOOL_HANDLERS:
                output = TOOL_HANDLERS[name](**args)
            # 2. 如果不是，就去技能包里找脚本
            else:
                output = run_skill_script(name, args)
            # -----------------------

            print(f"🛠️ 执行 [{name}] -> {str(output)[:100]}...")

            # 将执行结果按照 OpenAI 规范回传给 history
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": name,
                "content": str(output),
            })
            
        # 注意：这里不 return！循环会回到开头，带着 tool 结果再次询问 AI 
        # 此时如果加载了新技能，unique_tools 会在下一轮循环开头自动更新。


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
