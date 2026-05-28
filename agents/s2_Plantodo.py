import json
import os
from utils.logger import AgentLogger
from utils.config import config
from static_tools import STATIC_SCHEMAS, STATIC_HANDLERS

# Initialize global configuration and logger micro-scope
client = config.client
MODEL = config.model
logger = AgentLogger()

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
    def __init__(self):
        self.system_prompt = PLANNER_SYSTEM_PROMPT

    def generate_initial_plan(self, user_goal: str) -> list:
        """Analyze the macro user goal and output the first-generation task graph."""
        logger.log_orchestrator_info(f"🔮 [Planner] Dissecting strategic user goal: '{user_goal}'...")
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Generate a strict JSON task checklist for the following macro goal:\n{user_goal}"}
        ]
        
        # Enforce strict JSON Mode supported by OpenAI / Ollama standard protocols
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            response_format={"type": "json_object"}, 
            temperature=0.1
        )
        
        plan_raw = response.choices[0].message.content
        parsed_data = json.loads(plan_raw)
        
        # Handle cases where model wraps the array inside a top-level "tasks" key
        return parsed_data.get("tasks", parsed_data)

    def replan_on_failure(self, current_todo: list, failed_step_id: int, error_log: str) -> list:
        """[SELF-HEALING MECHANISM] Re-route and re-compile remaining plans upon front-line execution failure."""
        logger.log_orchestrator_warning(f"🚨 [Planner] Front-line report: Task ID {failed_step_id} failed completely. Initiating dynamic replanning...")
        
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
    def __init__(self):
        self.system_prompt = EXECUTOR_SYSTEM_PROMPT
        self.max_react_steps = 5  # Deadlock prevention guardian inside the inner loop

    def execute_single_task(self, task_description: str) -> tuple[bool, str]:
        """Inner Loop: Granular ReAct runtime loop with local self-healing capability."""
        logger.log_orchestrator_info(f"🏃 [Executor] Processing isolated task directive: '{task_description}'")
        
        # [MANDATE s06] Cold-start memory reset: context is 100% clean of prior tasks' noise
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Execute and fulfill this exact micro-task now: {task_description}"}
        ]
        
        step_count = 0
        last_observation = ""
        
        while step_count < self.max_react_steps:
            step_count += 1
            logger.log_executor_round(f"Executor ReAct Round [{step_count}/{self.max_react_steps}]")
            
            # -----------------------------------------------------------------
            # 🔌 TO BE FILLED: WIRE UP YOUR STAGE 1 LOGIC HERE
            # -----------------------------------------------------------------
            # 1. Feed `messages` to client.chat.completions.create with STATIC_SCHEMAS.
            # 2. Extract model's text/tool_calls. Append model's response to `messages`.
            # 3. If it's a tool_call, dispatch via STATIC_HANDLERS, get `observation`.
            # 4. Append `observation` back to `messages` as a 'tool' role.
            # 5. Local Self-Healing: If a tool errors out, let the model read the error stack and try fixing it.
            # 6. Success Condition: When model outputs final answer text declaring completion, return True, "Fulfillment Message".
            # -----------------------------------------------------------------
            
            # TEMPORARY PLACEHOLDER FOR INITIAL TEST RUNS:
            pass
        
        # If execution hits max steps without a clean exit, treat as an environmental crash
        return False, f"Executor failed after reaching max {self.max_react_steps} steps. Last known feedback: {last_observation or 'Timeout'}"


# =====================================================================
# ⚙️ THE CONTROL HUB: DUAL-LOOP STATE MACHINE (Orchestrator Core)
# =====================================================================

def run_orchestrator(user_goal: str):
    planner = LocalPlannerAgent()
    executor = LocalExecutorAgent()
    
    # 1. Macro strategic planning phase
    todo_list = planner.generate_initial_plan(user_goal)
    
    # [MANDATE s12] State persistence
    with open("todo.json", "w", encoding="utf-8") as f:
        json.dump(todo_list, f, ensure_ascii=False, indent=2)
        
    # Using our new strict English logger methods!
    logger.log_orchestrator_success(f"Task graph successfully deployed to local file memory: todo.json")

    # 2. Outer Loop: Finite State Machine Scheduler
    while True:
        current_step = None
        for step in todo_list:
            if step["status"] == "pending":
                current_step = step
                break
                
        if not current_step:
            logger.log_orchestrator_success("Task board fully cleared! All micro-steps successfully delivered!")
            break
            
        current_step["status"] = "running"
        logger.log_orchestrator_info(f"Dispatching Step ID {current_step['id']} -> [Task: {current_step['task']}]")
        
        # 3. Inner Loop execution activation with strict memory isolation
        success, final_observation = executor.execute_single_task(current_step["task"])
        
        if success:
            current_step["status"] = "completed"
            logger.log_orchestrator_info(f"Step ID {current_step['id']} completed successfully.")
        else:
            # 4. [SYSTEM-LEVEL SELF-HEALING] Front-line failed.
            current_step["status"] = "failed"
            logger.log_orchestrator_warning(
                f"Step ID {current_step['id']} crashed unrecoverably. Activating system self-healing dynamic re-routing..."
            )
            
            # Re-compile remaining plans
            todo_list = planner.replan_on_failure(todo_list, current_step["id"], final_observation)
            
            with open("todo.json", "w", encoding="utf-8") as f:
                json.dump(todo_list, f, ensure_ascii=False, indent=2)
                
            logger.log_orchestrator_info("Task graph updated and persistence files re-synced. Restarting scheduler...")