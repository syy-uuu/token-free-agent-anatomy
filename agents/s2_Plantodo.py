import json
import os
from utils.config import config
from agents.s1_ReAct import agent_loop

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
        self.logger = logger  # 依赖注入

    def generate_initial_plan(self, user_goal: str) -> list:
        self.logger.log_harness_to_planner(f"Dissecting user goal: '{user_goal}'")
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Generate a JSON task list for: {user_goal}"}
        ]
        
        # [统计] 交互 Message count: 2
        response = client.chat.completions.create(model=MODEL, messages=messages, response_format={"type": "json_object"})
        
        plan_data = json.loads(response.choices[0].message.content)
        todo_list = plan_data.get("tasks", plan_data)
        
        # 记录：Planner 告知 Harness 计划生成完毕
        self.logger.log_harness_to_user(f"Generated {len(todo_list)} tasks.")
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

EXECUTOR_SYSTEM_PROMPT = """You are a cold-blooded execution agent (Executor) working in the trenches.
Your sole mission is to complete the given micro-task by any means necessary, using your assigned tools.

[OPERATIONAL PROTOCOL]
1. You MUST interact with the environment exclusively via Tool Calls (Thought -> Action -> Observation).
2. Your current execution context is completely clean. Ignore macro-level strategies, focus ONLY on the immediate file or terminal command.
3. Every single round, you must output your reasoning via Thought, choose a tool via Action, and wait for the physical feedback.
4. Once the micro-task is fully validated (e.g., tests pass, file writes complete), declare victory and output your final answer to stop the loop.
"""

class LocalExecutorAgent:
    def __init__(self, logger):
        self.system_prompt = EXECUTOR_SYSTEM_PROMPT
        self.logger = logger
        self.max_react_steps = 5  

    def execute_single_task(self, task: str) -> tuple[bool, str]:
        self.logger.log_planner_to_executor(f"Start micro-task: {task}")
        
        step_count = 0
        while step_count < self.max_react_steps:
            step_count += 1
            # 记录：Executor ➔ Harness (物理操作)
            self.logger.log_executor_to_harness(f"Round {step_count}: Requesting tool use for {task}")
            
            try:
                # 假设这里是你的执行逻辑
                observation = agent_loop(task,logger=self.logger)  
                # 记录：Harness ➔ Executor (物理观测)
                self.logger.log_harness_to_executor(f"Round {step_count}: Observation: {observation}")
                
                if "success" in observation.lower():
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
    
    # 交互统计
    total_interaction_messages = 0

    # 1. 初始规划
    todo_list = planner.generate_initial_plan(user_goal)
    total_interaction_messages += 2 # (Planner <-> Harness)

    # 2. Outer Loop
    while True:
        current_step = next((s for s in todo_list if s["status"] == "pending"), None)
        if not current_step: break
            
        # [仪表盘展示]
        print(f"\n⚡ CURRENT STATUS: Steps Done | Total Interactions: {total_interaction_messages}")
        
        success, final_observation = executor.execute_single_task(current_step["task"])
        total_interaction_messages += 4 # (P->E, E->H, H->E, E->P) 每一轮交互更新
        
        if not success:
            todo_list = planner.replan_on_failure(todo_list, current_step["id"], final_observation)
            total_interaction_messages += 2