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

PLANNER_SYSTEM_PROMPT = """You are a rigorous Software Engineering Project Manager and Chief Architect.
Your sole mission is to split a user's complex macro goal into a sequence of small, decoupled, and micro-level sub-tasks.

[CRITICAL BEHAVIORAL MANDATES]
[CRITICAL MANDATES]
1. Granularity: DO NOT output macro-level tasks. Each ID must represent a single, atomic file operation or test verification.
2. Exhaustiveness: You MUST break down the request into AT LEAST 3 to 5 steps. If a task involves creating a directory, initializing a file, and writing code, these MUST be split into separate IDs.
3. Logical Depth: Do not be lazy. If you identify a multi-part process, list every single part explicitly.
4. Output Format: Output a root-level JSON array named 'tasks' containing the sequence.

[JSON OUTPUT SCHEMA FORMAT SPECIFICATION]
[
  {"id": 1, "task": "Create directory structure and initialize empty static_tools/file_ops.py", "status": "pending"},
  {"id": 2, "task": "Write comprehensive pytest unit tests inside test/stage2/ folder", "status": "pending"}
]
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

EXECUTOR_SYSTEM_PROMPT = """You are an execution agent (Executor).
Your mission is to perform the specific micro-task assigned by the Planner.

[OPERATIONAL RULES]
1. OUTPUT FORMAT: Every response MUST be in JSON format: {"thought": "...", "action": {"name": "...", "arguments": {...}}}.
2. CONSTRAINTS: 
   - NO conversational filler. 
   - NO summary of previous steps.
   - Output ONLY the next logical command.
3. ENVIRONMENT: Access the system ONLY via tools. Do not simulate output.
4. TASK COMPLETION: 
   - If the task is finished successfully, you MUST output a JSON object with a specific field: 
     {"status": "completed", "final_answer": "..."}
   - Do NOT use conversational language like "I have finished". Use the protocol above.
"""

class LocalExecutorAgent:
    def __init__(self, logger):
        self.system_prompt = EXECUTOR_SYSTEM_PROMPT
        self.logger = logger
        self.max_react_steps = 5

    # def execute_single_task(self, task: str) -> tuple[bool, str]:
    #     messages = [
    #         {"role": "system", "content": self.system_prompt}
    #     ]
    #     messages.append({"role": "user", "content": f"Execute the task: {task}"})
    #     step_count = 0
    #     self.logger.log_harness_to_user(f"enter stage ReAct loop, round {step_count} for task: {task}")
    #     while step_count < self.max_react_steps:
    #         step_count += 1
    #         try:
    #             observation = agent_loop(messages, logger=self.logger)  
    #             obs_str = str(observation) if observation is not None else ""
    #             self.logger.log_harness_to_executor(f"Round {step_count}: Observation: {obs_str}")
                
    #             if "success" in obs_str.lower():
    #                 self.logger.log_executor_to_planner("Task succeeded.")
    #                 return True, observation
    #         except Exception as e:
    #             self.logger.log_harness_to_executor(f"Error: {str(e)}")
        
    #     return False, "Max steps reached."
    
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
                # 建议：如果 LLM 输出里包含 {"status": "completed"}，视为胜利
                if "success" in content.lower() or '"status": "completed"' in content:
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