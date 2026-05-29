import json
import os
from utils.config import config
from agents.s1_ReAct import agent_loop
import time
from datetime import datetime

# Initialize global configuration and logger micro-scope
client = config.client
MODEL = config.model

# =====================================================================
# 🧠 DISSECTING ROLE 1: THE PLANNER (System Architect & Task Allocator)
# =====================================================================

PLANNER_SYSTEM_PROMPT = """You are a pragmatic, lean, and highly efficient Software Engineering Project Manager.
Your sole mission is to analyze a user's macro goal and translate it into a minimal, clean, and direct sequence of sub-tasks.

[CRITICAL PLANNING COGNITION]
1. TASK COMPLEXITY ANALYSIS (Crucial First Step):
   Before generating the plan, analyze the complexity of the user's request:
   - SIMPLE TASK (e.g., querying environment, editing a single file, creating a configuration file, basic shell query):
     Do NOT over-complicate it. Do NOT generate helper scripts (like 'write_info.py' or temporary runners). Solve it in EXACTLY 1 to 2 direct steps using raw tools or one-line bash commands.
   - COMPLEX TASK (e.g., building an entire system module, scaffolding a multi-file architecture, creating mock data plus testing):
     Decompose it logically into atomic, sequential milestones (typically 2 to 4 steps max).

2. THE EXECUTOR'S STATELESS MEMORY CONSTRAINT (Read Carefully):
   You are assigning tasks to a stateless, silent Executor agent. 
   - The Executor has NO long-term memory. It does NOT know your macro plan, does NOT remember previous tasks, and does NOT know what tasks are coming next.
   - For every task, the Executor is spun up with a completely fresh context.
   - Therefore, each task description you write MUST be self-contained, explicit, and physically descriptive. Avoid vague instructions like "Verify the previous results" or "Append based on the last python script output". Explicitly state paths, filenames, and exactly what physical output to look for.

3. ZERO SCRIPT SCAFFOLDING (Anti-Overengineering Rule):
   NEVER assign a task to create temporary python execution wrappers or redundant utility scripts just to write static text or run simple diagnostics. If a file can be written directly or a bash command can be run inline, order the Executor to do it directly.

4. MANDATORY PHYSICAL AUDIT STEP (The Final Gatekeeper):
   Your plan MUST always end with a dedicated physical verification task. The final task of any plan must explicitly instruct the Executor to physically verify the results—such as by reading the final created/edited file via file-reading tools, running `cat` or `grep` via bash, or running a test suite (pytest). Never assume success based on the Executor's word. The last task is strictly to confirm that the changes are physically present, accurate, and correct.

[THE EXECUTOR'S PHYSICAL TOOLBOX (KNOW YOUR WORKER)]
You are assigning tasks to a stateless, silent Executor agent. You MUST plan tasks that perfectly align with the Executor's actual physical capabilities. The Executor has ONLY the following 6 tools:
1. 'read_file': Reads the physical content of a specific file.
2. 'write_file': Writes a complete new file or overwrites an entire file.
3. 'edit_file': Modifies specific text blocks in an existing file using an exact 'old_text'/'new_text' match.
4. 'mkdir': Explicitly creates directories.
5. 'bash': Runs raw terminal/shell commands (the ultimate lever for diagnostics, Python execution, and tests).
6. 'task_completed': Declares the micro-task finished and returns the final answer.

[JSON OUTPUT SCHEMA FORMAT SPECIFICATION]
Output a root-level JSON array named 'tasks' containing the sequence. Do not wrap in markdown blocks, output pure JSON.

Format Template:
{
  "tasks": [
    {"id": 1, "task": "A physically clear, self-contained instruction stating exactly what to do, what tool/bash command approach to use, and where to write the file.", "status": "pending"},
    {"id": 2, "task": "Physically read and audit the created/edited file (e.g., using cat or file read tools) to ensure the contents match specifications perfectly.", "status": "pending"}
  ]
}
"""


class LocalPlannerAgent:
    def __init__(self, logger):
        self.system_prompt = PLANNER_SYSTEM_PROMPT
        self.logger = logger

    def _audit_tasks(self, event_description: str):
        """
        [审计日志渲染器]：这里是你的审计核心，保证每次状态变动都有一份清晰的清单
        """
        table_md = "\n| ID | Task | Status |\n|:---|:---|:---|\n"
        for t in self.tasks:
            table_md += f"| {t['id']} | {t['task']} | {t['status'].upper()} |\n"
        
        self.logger.audit("Planner", "System", "Status Audit", f"{event_description}\n{table_md}")

    def generate_initial_plan(self, user_goal: str) -> list:
        self.logger.log_harness_to_planner(f"{user_goal}")
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Generate a JSON task list for: {user_goal}"}
        ]
    
        response = client.chat.completions.create(model=MODEL, messages=messages, response_format={"type": "json_object"})
        
        plan_data = json.loads(response.choices[0].message.content)
        self.tasks = plan_data.get("tasks", plan_data)
        self._audit_tasks("Initial task plan generated.")
        
        self.logger.log_harness_to_user(f"Generated {len(self.tasks)} tasks, ask executor to start")
        return self.tasks
    
    def update_task_status(self, task_id: int, new_status: str, result: str = ""):
        for task in self.tasks:
            if task["id"] == task_id:
                old_status = task.get("status", "unknown")
                task["status"] = new_status
                if result:
                    task["result"] = result
                
                self._audit_tasks(f"Task {task_id} Update: {old_status} -> {new_status}")
                break


    def replan_on_failure(self, current_todo: list, failed_step_id: int, error_log: str) -> list:
        """[SELF-HEALING MECHANISM] Re-route and re-compile remaining plans upon front-line execution failure."""
        self.logger.log_harness_to_planner(f"CRASH: Step {failed_step_id} failed. Error: {error_log}")
        
        context_prompt = f"""The current execution snapshot of the task graph is:
                                {json.dumps(current_todo, ensure_ascii=False, indent=2)}

                                Crucial Alert: Task ID {failed_step_id} crashed with unresolvable errors during execution:
                                {error_log}

                                Analyze the root cause of this failure, consider already completed steps, rewrite or drop the remaining 'pending' tasks, and emit a brand new corrected JSON task array."""

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": context_prompt}
        ]
        
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1
        )
        parsed_data = json.loads(response.choices[0].message.content)
        self.tasks = parsed_data.get("tasks", parsed_data)
        self._audit_tasks(f"Replanned after failure of task ID {failed_step_id}.")
        return self.tasks


# =====================================================================
# 🏎️ DISSECTING ROLE 2: THE EXECUTOR (Front-Line Combat Soldier - ReAct Loop)
# =====================================================================


EXECUTOR_SYSTEM_PROMPT = """You are a cold-blooded, automated execution agent (Executor).
Your sole mission is to physically execute the single micro-task assigned by the Planner. You have no recollection of past tasks. Focus ONLY on your immediate mission.

[CORE OPERATIONAL PROTOCOLS]
1. STRICT TOOL INTERACTION ONLY:
   You must interact with the system EXCLUSIVELY via physical tool calls. NEVER simulate, guess, or assume the state of files or directories. If you do not know what is inside a file, you MUST read it first.

2. PROACTIVE TOOL DISCOVERY & MATCHING (Inspect Before Acting):
   You can ONLY invoke tools that are explicitly declared in your available Tool Specifications. 
   - NEVER hallucinate or invent tool names (e.g., do NOT invent 'os.getcwd' or 'check_architecture' as tool calls).
   - Before choosing an action, inspect your current toolset.
   - If a task requires system diagnostics, file verification, running python snippets, or terminal commands, and you do NOT see a specialized high-level tool for it in your specifications, you MUST use the 'bash' tool to execute it via terminal commands (e.g., `python -c "import os; print(os.getcwd())"`).

3. RIGID JSON FORMAT (Zero Conversational Filler):
   Your output must be a single, valid JSON object containing ONLY "thought" and "action" keys.
   - Do NOT say "Hello", "Ready", or write introductory/concluding remarks.
   - Do NOT wrap your JSON response in markdown code blocks (such as ```json ... ```).
   - Keep the "thought" field strictly technical, detailing only your immediate engineering logic.

   Format:
   {"thought": "Task requires reading path. No custom tool exists. I will use 'bash' to print the environment variable.", "action": {"name": "bash", "arguments": {"command": "echo $PWD"}}}

4. GUARANTEED MATCH FOR edit_file:
   If you must edit a file, you must first read it. The 'old_text' block must match the physical target perfectly, including all indentation, newlines, spaces, and punctuation, to ensure matching does not fail.

5. DEFINITIVE EXIT PROTOCOL:
   When you have physically verified that the assigned micro-task is completed, execute the exit action immediately:
   {"thought": "The micro-task is fully accomplished and physically verified.", "action": {"name": "task_completed", "arguments": {"final_answer": "Detailed physical outcome summary here"}}}
"""
class LocalExecutorAgent:
    def __init__(self, logger):
        self.system_prompt = EXECUTOR_SYSTEM_PROMPT
        self.logger = logger
        self.max_react_steps = 5
    
    def execute_single_task(self, task: str) -> tuple[bool, str]:
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        messages.append({"role": "user", "content": f"Execute the task: {task}"})
        
        step_count = 0
        self.logger.audit("EXECUTOR", "HARNESS", "Task Start", f"Executing task: {task}")

        while step_count < self.max_react_steps:
            step_count += 1
            try:
                # 1. 运行 AgentLoop
                # 注意：确保 agent_loop 返回的是模型解析后的完整内容
                raw_response = agent_loop(messages, logger=self.logger)
                
                # 2. 防御性获取模型输出 (直接访问属性，避免 .get() 报错)
                # 这里假设 response 遵循 OpenAI 结构
                content = getattr(raw_response, 'content', str(raw_response))
                
                # 3. 记录日志 (使用 audit 协议进行审计)
                self.logger.audit("LLM", "EXECUTOR", "Observation", f"Round {step_count}", result=content)

                # 4. “成功协议”握手 (JSON 协议优先)
                if "task_completed" in content.lower() or '"status": "completed"' in content:
                    self.logger.audit("EXECUTOR", "PLANNER", "Success", "Task completed.")
                    return True, content

                # 5. 必须将本轮输出追加回 messages，这是维持 ReAct 逻辑链条的关键！
                messages.append({"role": "assistant", "content": content})
                
            except Exception as e:
                error_msg = f"Round {step_count} crashed: {str(e)}"
                self.logger.audit("SYSTEM", "EXECUTOR", "CRITICAL_ERROR", error_msg)
                # [工业熔断]：代码级崩溃，必须立即停止，将控制权交还 Orchestrator 进行重规划
                return False, error_msg
        
        return False, "Max steps reached."


# =====================================================================
# ⚙️ THE CONTROL HUB: DUAL-LOOP STATE MACHINE (Orchestrator Core)
# =====================================================================

def run_orchestrator(user_goal: str, logger):
    planner = LocalPlannerAgent(logger)
    executor = LocalExecutorAgent(logger)
    planner.generate_initial_plan(user_goal)

    while True:
        current_step = next((s for s in planner.tasks if s["status"] == "pending"), None)
        
        if not current_step:
            break
        
        # 2. 执行
        logger.log_planner_to_executor(f"Task ID {current_step['id']}: {current_step['task']}")
        success, final_observation = executor.execute_single_task(current_step["task"])
        
        # 3. 闭环更新（这一步最丝滑）
        status = "success" if success else "failure"
        planner.update_task_status(current_step["id"], status, final_observation)
        logger.audit("Harness", "User", "Status Update", f"Task {current_step['id']} marked as success.")
        
        if not success:
            # 重规划时，让 Planner 直接基于当前的 self.tasks 重新计算
            planner.tasks = planner.replan_on_failure(planner.tasks, current_step["id"], final_observation)