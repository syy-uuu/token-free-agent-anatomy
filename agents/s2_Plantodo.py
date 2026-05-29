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

    def generate_initial_plan(self, user_goal: str) -> list:
        self.logger.log_harness_to_planner(f"{user_goal}")
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Generate a JSON task list for: {user_goal}"}
        ]
    
        response = client.chat.completions.create(model=MODEL, messages=messages, response_format={"type": "json_object"})
        
        plan_data = json.loads(response.choices[0].message.content)
        todo_list = plan_data.get("tasks", plan_data)
        
        self.logger.log_harness_to_user(f"Generated {len(todo_list)} tasks, ask executor to start")
        self.logger.log_harness_to_user(f"task list: {json.dumps(todo_list, ensure_ascii=False, indent=2)}")
        return todo_list


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
        return parsed_data.get("tasks", parsed_data)


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
        self.logger.log_harness_to_user(f"enter stage ReAct loop, round {step_count} for task: {task}")
        while step_count < self.max_react_steps:
            step_count += 1
            try:
                observation = agent_loop(messages, logger=self.logger)  
                obs_str = str(observation) if observation is not None else ""
                self.logger.log_harness_to_executor(f"Round {step_count}: Observation: {obs_str}")
                
                if "success" in obs_str.lower():
                    self.logger.log_executor_to_planner("Task succeeded.")
                    return True, observation
            except Exception as e:
                self.logger.log_harness_to_executor(f"Error: {str(e)}")
        
        return False, "Max steps reached."


# =====================================================================
# ⚙️ THE CONTROL HUB: DUAL-LOOP STATE MACHINE (Orchestrator Core)
# =====================================================================

def run_orchestrator(user_goal: str, logger):
    planner = LocalPlannerAgent(logger)
    executor = LocalExecutorAgent(logger)
    todo_list = planner.generate_initial_plan(user_goal)

    while True:
        # 1. 查找当前待办事项
        current_step = next((s for s in todo_list if s["status"] == "pending"), None)
        if not current_step: 
            logger.audit("Harness", "User", "Finish", "All tasks completed or no pending tasks.")
            break
        
        # 2. 执行任务
        logger.log_planner_to_executor(f"Task ID {current_step['id']}: {current_step['task']}")
        success, final_observation = executor.execute_single_task(current_step["task"])
        
        # 3. 状态闭环逻辑
        if success:
            # 物理更新：直接在 todo_list 对象中原地修改状态
            current_step["status"] = "success"
            current_step["result"] = final_observation # 顺便存一下执行结果
            logger.audit("Harness", "User", "Status Update", f"Task {current_step['id']} marked as success.")
            
        else:
            # 失败逻辑：调用 Planner 的重规划能力
            current_step["status"] = "failure"
            logger.audit("Harness", "User", "Status Update", f"Task {current_step['id']} failed, re-planning...")
            todo_list = planner.replan_on_failure(todo_list, current_step["id"], final_observation)