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

PLANNER_SYSTEM_PROMPT = """
You are the Planner Agent in a Plan-to-Do architecture. Decompose the user's goal into logical, linear micro-tasks (milestones).

[CRITICAL RULES]
1. NO SPECIFIC CODE/COMMANDS: Do NOT generate shell commands, python snippets, or precise tool inputs. The Executor figures out the implementation details.
2. STATELESS EXECUTOR: The Executor has no long-term memory. Each task must explicitly bundle:
   - Milestone Objective: What needs to be done.
   - Required Context: Specific files/variables inherited from prior tasks.
   - Definition of Done (DoD): Exact physical verification criteria (what contents/files must exist to succeed, or what patterns mean failure).

[OUTPUT FORMAT SPECIFICATION]
Output a root-level JSON object with a single 'tasks' array. Do not wrap in markdown code blocks. Output pure raw JSON.

Format Template (Inject Milestone, Context, and DoD strictly into the 'task' field string):
{
  "tasks": [
    {
      "id": 1,
      "task": "Milestone: [Action objective]. Context: [Data source/files]. DoD: SUCCESS if [exact file exists / text pattern matches], FAILURE if [file missing / unexpected output].",
      "status": "pending"
    }
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
        
        self.logger.audit("PLANNER", "SYSTEM", "Status Audit", f"{event_description}\n{table_md}")

    def generate_initial_plan(self, user_goal: str) -> list:
        self.logger.log_harness_to_planner(f"{user_goal}")
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Generate a JSON task list for: {user_goal}"}
        ]
    
        response = client.chat.completions.create(model=MODEL, messages=messages, response_format={"type": "json_object"})
        
        plan_data = json.loads(response.choices[0].message.content)
        self.tasks = plan_data.get("tasks", plan_data)
        self._audit_tasks("Initial task plan generated, ask executor to start")
        
        # self.logger.log_harness_to_user(f"Generated {len(self.tasks)} tasks, ask executor to start")
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
        print(f"DEBUG: Current model being invoked: {MODEL}")
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


EXECUTOR_SYSTEM_PROMPT = """
You are an automated, stateless execution agent. Your sole mission is to physically execute the single micro-task assigned by the Planner. You have no long-term memory.

[OPERATIONAL PROTOCOLS]
1. NATIVE TOOL CALLS ONLY: You MUST interact with the environment exclusively via the system's native Tool Call feature. Every action must select a specific tool from STATIC_SCHEMAS.
2. ZERO TEXT JSON: You are STRICTLY FORBIDDEN from outputting raw JSON objects, tool structures, or Markdown JSON blocks inside your plain text (message.content). Natural text output must NEVER contain strings starting with '{' or containing '"arguments":'.
3. SINGLE ATOMIC ACTION ONLY: You are STRICTLY FORBIDDEN from executing multiple steps or chaining actions (e.g., writing a file AND running a bash command) in one turn. Output EXACTLY ONE native tool call per round and wait for feedback.
4. PERFECT EDIT MATCHING: Before using 'edit_file', you must read the file first. 'old_text' must match the file content perfectly.
5. VERIFICATION MANDATE: You MUST physically run the verification command (e.g., `bash` with `python3 math_ops.py`) in the shell first, read the actual terminal output Observation, and verify it works before finishing.

[EXIT PROTOCOL]
Only when the micro-task is physically verified as successful via prior tool outputs, invoke the native 'task_completed' tool from your function list.
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
        self.logger.log_executor_to_harness(f"Enter Stage1 ReAct, task is: {task}")

        while step_count < self.max_react_steps:
            step_count += 1
            try:
                # 1. 运行 AgentLoop
                # 注意：确保 agent_loop 返回的是模型解析后的完整内容
                raw_response = agent_loop(messages, logger=self.logger)
                
                # 2. 防御性获取模型输出 (直接访问属性，避免 .get() 报错)
                # 这里假设 response 遵循 OpenAI 结构
                content = getattr(raw_response, 'content', str(raw_response))

                # 4. “成功协议”握手 (JSON 协议优先)
                if "task_completed" in content.lower() or "completed" in content.lower() or '"status": "completed"' in content:
                    self.logger.log_executor_to_harness("Task completed.")
                    return True, content

                # 5. 必须将本轮输出追加回 messages，这是维持 ReAct 逻辑链条的关键！
                messages.append({"role": "assistant", "content": content})
                
            except Exception as e:
                error_msg = f"Round {step_count} crashed: {str(e)}"
                self.logger.log_system_to_harness("EXECUTOR", error_msg, is_error=True)
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
        logger.log_harness_to_user(f"Task {current_step['id']} marked as {status}.")
        
        if not success:
            # 重规划时，让 Planner 直接基于当前的 self.tasks 重新计算
            planner.tasks = planner.replan_on_failure(planner.tasks, current_step["id"], final_observation)