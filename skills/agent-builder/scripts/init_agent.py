#!/usr/bin/env python3
"""
Agent Scaffold Script (OpenAI/Qwen Version) - Create a new agent project.

Usage:
    python init_agent.py <agent-name> [--level 0-4] [--path <output-dir>]

Environment Setup:
    pip install openai python-dotenv

Example:
    python init_agent.py my-qwen-bot --level 1
    
Levels:
    0: Minimal (Bash only) - Great for simple automation
    1: Standard (Bash, Read, Write, Edit) - The "Swiss Army Knife"
    2-4: Specialized (Planning, Subagents, Skills) - Advanced architectures
"""

import argparse
import os
import sys
from pathlib import Path

# Agent templates for each level
TEMPLATES = {
    0: '''#!/usr/bin/env python3
"""
Level 0 Agent - Bash is All You Need (~50 lines)
OpenAI/Qwen Version

Core insight: One tool (bash) can do everything.
Subagents via self-recursion: python {name}.py "subtask"
"""

from openai import OpenAI
import subprocess
import os
import json
from pathlib import Path


client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)
MODEL = "qwen2.5:latest"

SYSTEM = """You are a coding agent. Use bash for everything:
- Read: cat, grep, find, ls
- Write: echo 'content' > file
- Subagent: python {name}.py 'subtask'
"""

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
    }
]

def run(prompt, history=[]):
    history.append({{"role": "user", "content": prompt}})
    while True:
        # OpenAI 调用方式
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{{"role": "system", "content": SYSTEM}}] + history,
            tools=TOOLS
        )
        
        msg = r.choices[0].message
        history.append(msg.model_dump()) # 关键：记录 Assistant 的回复（含 tool_calls）

        if not msg.tool_calls:
            return msg.content or ""

        for tool_call in msg.tool_calls:
            if tool_call.function.name == "bash":
                command = json.loads(tool_call.function.arguments)["command"]
                print(f"> {{command}}")
                try:
                    out = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
                    output = (out.stdout + out.stderr).strip() or "(empty)"
                except Exception as e:
                    output = f"Error: {{e}}"
                
                # 回传工具执行结果
                history.append({{
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": "bash",
                    "content": output[:50000]
                }})
if __name__ == "__main__":
    h = []
    print(f"{name} - Level 0 Agent (Ollama/Qwen)")
    print("Type 'q' to quit.\\n")
    while True:
        try:
            query = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if query in ("q", "quit", "exit", ""):
            break
        # 执行 agent 循环并打印结果
        result = run(query, h)
        print(f"\\n{{result}}\\n")
''',

    1: '''#!/usr/bin/env python3
"""
Level 1 Agent - Model as Agent (~200 lines)

Core insight: 4 tools cover 90% of coding tasks.
The model IS the agent. Code just runs the loop.
"""

from openai import OpenAI
import subprocess
import os
import json
from pathlib import Path


client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)
MODEL = "qwen2.5:latest"
WORKDIR = Path.cwd()

SYSTEM = f"""You are a coding agent at {{WORKDIR}}.

Rules:
- Prefer tools over prose. Act, don't just explain.
- Never invent file paths. Use ls/find first if unsure.
- Make minimal changes. Don't over-engineer.
- After finishing, summarize what changed."""

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
    }
]

def safe_path(path_str: str) -> Path:
    path = (WORKDIR / path_str).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {path_str}")
    return path

def execute(name: str, args: dict) -> str:
    """执行工具并返回结果 - 适配 Ollama/Qwen 环境"""
    if name == "bash":
        # 安全守卫：防止 AI 拆家
        dangerous = ["rm -rf /", "sudo", "shutdown", "> /dev/"]
        if any(d in args["command"] for d in dangerous):
            return "Error: Dangerous command blocked for security."
        try:
            # 执行本地命令
            r = subprocess.run(args["command"], shell=True, cwd=WORKDIR, capture_output=True, text=True, timeout=60)
            output = (r.stdout + r.stderr).strip()
            return output[:50000] if output else "(empty output)"
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 60 seconds."
        except Exception as e:
            return f"Error: {e}"

    if name == "read_file":
        try:
            # 使用 safe_path 确保 AI 不会读取到项目文件夹以外的文件
            return safe_path(args["path"]).read_text(encoding="utf-8")[:50000]
        except Exception as e:
            return f"Error reading file: {e}"

    if name == "write_file":
        try:
            p = safe_path(args["path"])
            p.parent.mkdir(parents=True, exist_ok=True) # 自动创建不存在的目录
            p.write_text(args["content"], encoding="utf-8")
            return f"Successfully wrote {len(args['content'])} bytes to {args['path']}"
        except Exception as e:
            return f"Error writing file: {e}"

    if name == "edit_file":
        try:
            p = safe_path(args["path"])
            content = p.read_text(encoding="utf-8")
            old_text = args["old_text"]
            if old_text not in content:
                return f"Error: The exact text to replace was not found in {args['path']}. Check indentation and hidden characters."
            
            # 只替换第一次出现的匹配项，防止误伤
            new_content = content.replace(old_text, args["new_text"], 1)
            p.write_text(new_content, encoding="utf-8")
            return f"Successfully edited {args['path']}"
        except Exception as e:
            return f"Error editing file: {e}"

    return f"Unknown tool: {name}"

def agent(prompt: str, history: list = None) -> str:
    """运行 Agent 循环 - 适配 OpenAI/Ollama 协议"""
    if history is None:
        history = []
    
    # 记录用户输入
    history.append({"role": "user", "content": prompt})

    while True:
        # 发起请求 (注意：系统提示词 SYSTEM 放在开头)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM}] + history,
            tools=TOOLS,
            temperature=0
        )

        msg = response.choices[0].message
        
        # 核心：必须将完整的 message 对象存入历史，以便保留其中的 tool_calls 结构
        history.append(msg.model_dump())

        # 如果没有工具调用，说明任务完成了，直接返回文本内容
        if not msg.tool_calls:
            return msg.content or ""

        # 处理本轮所有的工具调用
        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            
            # 解析参数
            import json
            try:
                args = json.loads(tool_call.function.arguments)
            except Exception:
                args = {}

            # 执行工具
            print(f"> {name}: {str(args)[:80]}...")
            output = execute(name, args)
            print(f"  Result: {str(output)[:80]}...")

            # 按照 OpenAI 规范，将工具执行结果回传给 history
            # 注意：role 必须是 "tool"，且必须提供 tool_call_id
            history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": name,
                "content": str(output),
            })
        
        # 循环继续，Qwen 将带着工具结果进行下一步思考

if __name__ == "__main__":
    print(f"Agent '{name}' - Level 1 (Qwen/Ollama Edition)")
    print(f"Working Directory: {WORKDIR}")
    print("Type 'q' or 'exit' to quit.\\n")
    
    h = []
    while True:
        try:
            query = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not query or query.lower() in ("q", "quit", "exit"):
            break
            
        answer = agent(query, h)
        print(f"\\nAssistant: {answer}\\n")
''',
}

ENV_TEMPLATE = '''# API Configuration (Ollama / Local Edition)
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://localhost:11434/v1
MODEL_NAME=qwen2.5:latest
'''

import json
def create_agent(name: str, level: int, output_dir: Path):
    """创建新的 Agent 项目 - 生产线逻辑"""
    # 1. 校验等级
    # 如果你还没写好 Level 2-4 的模板，就先提示还没实现
    if level not in TEMPLATES:
        print(f"Error: Level {level} templates are not yet refactored for Qwen/Ollama.")
        print("Available levels: 0 (Minimal), 1 (Standard)")
        sys.exit(1)

    # 2. 创建项目文件夹
    agent_dir = output_dir / name
    agent_dir.mkdir(parents=True, exist_ok=True)

    # 3. 写入 Agent 主程序 (核心：这里已经用了 .replace)
    agent_file = agent_dir / f"{name}.py"
    template = TEMPLATES.get(level)
    agent_file.write_text(template.replace("{name}", name), encoding="utf-8")
    print(f"Created: {agent_file}")

    # 4. 写入环境变量模板
    # 注意：我们这里直接写成 .env 吧，省去你手动 cp 的麻烦，或者保留 .env.example 也行
    env_file = agent_dir / ".env"
    env_file.write_text(ENV_TEMPLATE, encoding="utf-8")
    print(f"Created: {env_file}")

    # 5. 写入 .gitignore
    gitignore = agent_dir / ".gitignore"
    gitignore.write_text(".env\n__pycache__/\n*.pyc\n.DS_Store\n", encoding="utf-8")
    print(f"Created: {gitignore}")

    print(f"\n✨ Agent '{name}' (Level {level}) created successfully at {agent_dir}")
    print(f"\nNext steps:")
    print(f"  1. cd {agent_dir}")
    print(f"  2. (Optional) Check .env settings: MODEL_NAME={os.getenv('MODEL_NAME', 'qwen2.5:latest')}")
    print(f"  3. pip install openai python-dotenv") # 换成 OpenAI
    print(f"  4. Make sure Ollama is running (`ollama serve`) ") # 增加 Ollama 提醒
    print(f"  5. python {name}.py")
    return f"成功在 {output_dir}/{name} 初始化项目"


def main():
    # --- 1. 优先尝试处理来自 S05 的 JSON 参数 ---
    if len(sys.argv) > 1:
        try:
            # 探测第一个参数是不是 JSON
            data = json.loads(sys.argv[1])
            # 兼容多种可能的键名：project_name, name 等
            name = data.get("project_name") or data.get("name")
            
            # 如果解析出了名字，才执行逻辑
            if name:
                level = int(data.get("level", 1))
                path = Path(data.get("path", "."))
                result = create_agent(name, level, path)
                # print(result) # create_agent 内部已经 print 过了，这里可以只打印返回值
                return # 成功后立即退出，千万不要往下走！
        except (json.JSONDecodeError, ValueError, TypeError):
            # 如果第一个参数不是 JSON，说明是人在敲命令行，忽略错误继续往下走
            pass

    # --- 2. 处理来自人类的命令行参数 (argparse) ---
    parser = argparse.ArgumentParser(
        description="Scaffold a new Qwen/Ollama coding agent project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Levels (Qwen-Ready):
  0  Minimal (~50 lines) - Single bash tool. Fast and lightweight.
  1  Standard (~200 lines) - Core 4 tools (Bash, Read, Write, Edit).
  2-4 (Coming soon) - Specialized logic for planning and skills.
        """
    )
    parser.add_argument("name", help="Name of the agent to create")
    parser.add_argument("--level", type=int, default=1, choices=[0, 1, 2, 3, 4],
                       help="Complexity level (default: 1)")
    parser.add_argument("--path", type=Path, default=Path.cwd(),
                       help="Output directory (default: current directory)")

    args = parser.parse_args()
    create_agent(args.name, args.level, args.path)


if __name__ == "__main__":
    main()