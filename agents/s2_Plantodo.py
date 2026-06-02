import json
import os
from utils.config import config
from utils.env_utils import generate_dynamic_tree
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
You are the Strategic Planner. Your job is to break down user requests into concise, modular, and dependency-clear sub-tasks for a no-long-memory execution agent.

[CRITICAL MANDATE]
You MUST generate the FULL multi-step roadmap containing ALL tasks covering all 3 phases from start to finish at once. DO NOT just output the first task.

[MACRO STRATEGY: THREE-STAGE LIFECYCLE]
You MUST design the task list sequentially across these three immutable phases in a single list:

- Phase 1: Objective Explanation & Architecture Alignment (Typically Task 1)
  - context: Describe the final goal concisely and clearly.
  - task: Layout the project directories, setup entrypoints or files (e.g., main.py).

- Phase 2: Modular Implementation & Progressive Coding (Typically Tasks 2-4)
  - context: The incremental progress and decoupled module requirements.
  - task: Break code creation into independent, decoupled subtasks. Define clear file responsibilities.

- Phase 3: Rigid Physical Verification (Typically Last Task)
  - context: Describe the target final testing scenario.
  - task: Execute testing scripts or run verification tools to validate correctness.

[MICRO TASK FORMATTING SPECIFICATION]
Output ONLY a strict JSON block matching this structure. Ensure your "tasks" array contains ALL planned tasks (usually 3 to 6 tasks total to complete the entire goal).

{
  "tasks": [
    {
      "id": 1,
      "context": "Context for Phase 1...",
      "task": "Task for Phase 1...",
      "status": "pending"
    },
    {
      "id": 2,
      "context": "Context for Phase 2...",
      "task": "First coding task...",
      "status": "pending"
    },
    {
      "id": 3,
      "context": "Context for Phase 3...",
      "task": "Verification task...",
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
        table_md = "\n| ID | Context | Task | Status |\n|:---|:---|:---|:---|\n"
        for t in self.tasks:
            context = t.get("context", "")
            table_md += f"| {t['id']} | {context} | {t['task']} | {t['status']} |\n"
        
        self.logger.audit("PLANNER", "HARNESS ➔ EXECUTOR", event_description, table_md, color=self.logger.C_PLANNER)

    def generate_initial_plan(self, user_goal: str) -> list:
       
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Generate a JSON task list for: {user_goal}"}
        ]
    
        response = client.chat.completions.create(model=MODEL, messages=messages, response_format={"type": "json_object"})
        
        plan_data = json.loads(response.choices[0].message.content)
        self.tasks = plan_data.get("tasks", plan_data)
        self._audit_tasks("Initial task plan generated")
        
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
        # self.logger.log_harness_to_planner(f"CRASH: Step {failed_step_id} failed. Error: {error_log}")
        
        context_prompt = f"""
                        Task ID {failed_step_id} failed, details:
                        {error_log}
                        Analyze the root cause of this failure, and DO NOT give the same plan as before. Re-plan the remaining pending tasks with necessary adjustments, and output the updated full task list in the same JSON format as before.
                        The goal is to fix the failure and complete the original user goal. Here is the current pending task list for your reference:
                        {json.dumps(current_todo, ensure_ascii=False, indent=2)}
                        """

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": context_prompt}
        ]
        # print(f"DEBUG: Current model being invoked: {MODEL}")
        self.logger.log_info("DEBUG", error_log)
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
You are an coding agent. your job is to finish the sub-task assigned by the Planner. 
[OPERATIONAL PROTOCOLS]
1. You MUST understand current status of the whole task from planner, and then start current sub-task based on the project situation.
2. Every action must select a specific tool from tools, NEVER generate raw code blocks or shell commands in the content. The tools are your only interface to interact with the environment and files.
3. You MUST use execute_test tool to check the effectiveness of your code (only python file), never pretend you have successfully completed the task without physical verification.
4. You MUST physically write in json format in the content "{ "status": "completed" }" and explain current status to planner to declare the success of the task. This is the ONLY valid success declaration protocol.
5. If error occurs for one tool_call, NEVER retry the same command, you can use the same tool but with different arguments.
"""
class LocalExecutorAgent:
    def __init__(self, logger):
        self.system_prompt = EXECUTOR_SYSTEM_PROMPT
        self.logger = logger
        self.max_react_steps = 10
    
    def execute_single_task(self, task_id: str, task: str) -> tuple[bool, str]:
            current_tree_str = generate_dynamic_tree(config.workdir)
            
            # 1. 初始 Prompt 组装：确保规则、目录、任务层级清晰
            messages = [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user", 
                    "content": f"1. CURRENT PROJECT TREE\n{current_tree_str}\n\n"
                            f"2. YOUR TASK\n{task}\n\n"
                }
            ]
        
            step_count = 0
            
            last_tool_call_args = None  # 用于追踪连续重复的工具调用

            while step_count < self.max_react_steps:
                self.logger.log_info("current project tree", current_tree_str)
                step_count += 1
                try:
                    self.logger.log_harness_to_llm(f"Stage1 ReAct agent, task ID {task_id}, round {step_count}", "Task Execution", messages)
                    
                    # 2. 运行大模型拿到思考和工具意图
                    raw_response = agent_loop(messages, logger=self.logger)
                    content = getattr(raw_response, 'content', str(raw_response)) or ""
                    tool_calls = getattr(raw_response, 'tool_calls', None)

                    # 4. “成功协议”握手 (JSON 优先)
                    if '"status": "completed"' in content or (isinstance(content, str) and "status" in content and "completed" in content):
                        return True, content
                    
                    # 5. 工具执行核心分流
                    if tool_calls:
                        # 💡 注意：这里需要你实际执行工具的逻辑。下面是示意：
                        for tool_call in tool_calls:
                            tool_name = tool_call.function.name
                            tool_args = tool_call.function.arguments
                            
                            # 执行你的真实工具，拿到结果字符串
                            tool_result = self.execute_static_tool(tool_name, tool_args) 
                            
                            # 🌟 6. 正确的死循环/错误拦截点：检查【工具返回结果】是否包含错误
                            tool_result_lower = str(tool_result).lower()
                            error_indicators = ["error", "exception", "traceback", "not found", "failed", "could not find"]
                            
                            if any(indicator in tool_result_lower for indicator in error_indicators):
                                # 上一次工具挂了，立刻给模型发送强力的置顶警告（以 user 身份注入）
                                messages.append({
                                    "role": "user", 
                                    "content": """⚠️ [CRITICAL HARNESS NOTICE] ⚠️
                                    Your previous action failed with an error! 
                                    To break the loop, you are STRICTLY PROHIBITED from executing the exact same tool call with the same arguments. 

                                    If 'edit_file_by_lines' failed, you MUST:
                                    1. Call 'view_file_with_line_numbers' FIRST to check the latest line layout.
                                    2. Re-calculate the correct line numbers.
                                    3. Then try editing again."""
                                })
                    else:
                        # 如果大模型既没有宣布结束，又没有调用工具，说明它在梦游
                        messages.append({
                            "role": "user",
                            "content": "You did not output any tool call or declare completion. If the task is done, output {\"status\": \"completed\"}. Otherwise, invoke a tool to proceed."
                        })
                    
                except Exception as e:
                    error_msg = f"Round {step_count} crashed: {str(e)}"
                    self.logger.log_info("Max steps reached, return to planner", error_msg, color=self.logger.C_SYSTEM_ERROR)
                    return False, error_msg
            
            return False, "Max steps reached without completion declaration."


# =====================================================================
# ⚙️ THE CONTROL HUB: DUAL-LOOP STATE MACHINE (Orchestrator Core)
# =====================================================================

def run_orchestrator(user_goal: str, logger):
    planner = LocalPlannerAgent(logger)
    executor = LocalExecutorAgent(logger)
    # 1. Capture the macro-intent and route it to the Orchestrator
    logger.log_user_to("HARNESS ➔ PLANNER(get initial plan)", "User query", user_goal)
    planner.generate_initial_plan(user_goal)

    while True:
        current_step = next((s for s in planner.tasks if s["status"] == "pending"), None)
        if not current_step:
            break
        task_description = json.dumps({
            "context": current_step["context"],
            "task": current_step["task"],
            "status": current_step["status"]
        }, ensure_ascii=False)
        
        
        success, final_observation = executor.execute_single_task(current_step["id"], task_description)
        
        # 3. 闭环更新（这一步最丝滑）
        status = "success" if success else "failure"
        planner.update_task_status(current_step["id"], status, final_observation)
        # logger.log_harness_to("USER",f"Task {current_step['id']} marked as {status}.")
        
        if not success:
            # 重规划时，让 Planner 直接基于当前的 self.tasks 重新计算
            planner.tasks = planner.replan_on_failure(planner.tasks, current_step["id"], final_observation)