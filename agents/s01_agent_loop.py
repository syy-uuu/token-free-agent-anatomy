import os
import subprocess
from dataclasses import dataclass
from openai import OpenAI
import json

try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
    readline.parse_and_bind('set input-meta on')
    readline.parse_and_bind('set output-meta on')
    readline.parse_and_bind('set convert-meta off')
    readline.parse_and_bind('set enable-meta-keybindings on')
except ImportError:
    pass

# 定义颜色常量
BLUE = "\033[94m"   # System
GREEN = "\033[92m"  # User
YELLOW = "\033[93m" # Protocol/Tool Call
RED = "\033[91m"    # Physical Action
PURPLE = "\033[95m" # Feedback
CYAN = "\033[96m"   # Semantic Response
RESET = "\033[0m"

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)
MODEL = "qwen2.5:latest"

SYSTEM = (
    f"You are a coding agent at {os.getcwd()}. "
    "When asked to do something, you MUST use the 'bash' tool to perform the action FIRST. "
    "Do not explain what you will do in text without calling the tool. "
    "After you receive the tool output, report the results clearly to the user."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command in the current workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to run"}
                },
                "required": ["command"]
            }
        }
    }
]


@dataclass
class LoopState:
    messages: list
    turn_count: int = 1
    transition_reason: str | None = None


def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(item in command for item in dangerous):
        return "Error: Dangerous command blocked"
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"

    output = (result.stdout + result.stderr).strip()
    return output[:50000] if output else "(no output)"

def execute_tool_calls(tool_calls) -> list[dict]:
    results = []
    
    if not isinstance(tool_calls, list):
        tool_calls = [tool_calls]
    
    for tool_call in tool_calls:
        if isinstance(tool_call, tuple):
            tool_call = tool_call[-1]

        func_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)

        if func_name == "bash":
            command = args.get("command")
            print(f"\033[33m🚀 正在执行命令: {command}\033[0m")
            print(f"{RED}[命令为{command}]{RESET}")

            output_msg = run_bash(command)
        else:
            output_msg = "错误：AI 尝试调用了一个未定义的工具。"
        
        results.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": output_msg
        })
    
    return results

def run_one_turn(state) -> bool:
    print(f"\n{BLUE}--- [Harness] 收到用户的上下文 (消息为: {state.messages}) ---{RESET}")
    
    payload = [{"role": "system", "content": SYSTEM}] + state.messages
    print(f"\n{BLUE}--- [Harness] 正在向 Qwen2.5 提交当前上下文 (消息为: {payload}) ---{RESET}")
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": SYSTEM}] + state.messages,
        tools=TOOLS,
        tool_choice="auto",
    )
    message = response.choices[0].message
    state.messages.append(message)

    print(f"{GREEN}AI 响应: {state.messages}{RESET}")

    if message.content:
        print(f"{CYAN}AI (语义层): {message.content}{RESET}")

    # 2. 协议层检查：AI 要动弹（核心拦截逻辑）
    if message.tool_calls:
        for tool_call in message.tool_calls:
            # 曝光原文协议
            print(f"{YELLOW}[协议工具] {tool_call.function.name}{RESET}")
            print(f"{YELLOW}[原文内容] {tool_call.function.arguments}{RESET}")
            
            tool_results = execute_tool_calls(message.tool_calls)
            state.messages.extend(tool_results)
            return True


    return False 

def agent_loop(state: LoopState) -> None:
    while run_one_turn(state):
        pass


if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36ms01 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break

        history.append({"role": "user", "content": query})
        state = LoopState(messages=history)
        agent_loop(state)

        print(f"\n任务完成！")
