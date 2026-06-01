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
You are the Strategic Planner. Your job is to break down user requests into concise, modular, and dependency-clear sub-tasks for a no-long-memory execution agent.

[MACRO STRATEGY: THREE-STAGE LIFECYCLE]
You MUST design the task list sequentially across these three immutable phases:

- Phase 1: Objective Explanation & Architecture Alignment
  - Objective: You MUST describe the final goal concisely and clearly first, and then assign the first task to the executor agent.
  - Action: Determine the project file structure (modular multi-file or directory structure) and run baseline environment probes (e.g., check Python/package availability).

- Phase 2: Modular Implementation & Progressive Coding
  - Objective: You MUST implement functional logic progressively.
  - Action: Break code creation into independent, decoupled subtasks. Enforce modular design constraints (do NOT guide specific function names, but clarify file responsibilities) and pass verified context to successive tasks.

- Phase 3: Rigid Physical Verification
  - Objective: Final black-box/integration verification.
  - Action: Execute main entry files or test scripts, capture physical terminal output, and ensure zero-hallucination validation before closing out the loop.

[MICRO TASK FORMATTING SPECIFICATION]
Output ONLY a strict JSON block matching this structure. No conversational filler or markdown wrappers outside the JSON block.

{
  "tasks": [
    {
      "id": 1,
      "context": "",
      "task": "",
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
        table_md = "\n| ID | Task | Context | Status |\n|:---|:---|:---|:---|\n"
        for t in self.tasks:
            context = t.get("context", "")
            table_md += f"| {t['id']} | {t['task']} | {context} | {t['status']} |\n"
        
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
3. You MUST use execute_text tool to check the effectiveness of your code (only python file), never pretend you have successfully completed the task without physical verification.
4. You MUST physically write in json format in the content "{ "status": "completed" }" and explain current status to planner to declare the success of the task. This is the ONLY valid success declaration protocol.
5. If error occurs for one tool_call, NEVER retry the same command, you can use the same tool but with different arguments.
"""
class LocalExecutorAgent:
    def __init__(self, logger):
        self.system_prompt = EXECUTOR_SYSTEM_PROMPT
        self.logger = logger
        self.max_react_steps = 5
    
    def execute_single_task(self, task_id: str, task: str) -> tuple[bool, str]:
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        messages.append({"role": "user", "content": task})
                # 2. 执行
        # self.logger.log_harness_to("EXECUTOR", "Message", f"Task ID {task_id}: {task}")
        step_count = 0

        while step_count < self.max_react_steps:
            step_count += 1
            try:
                # 1. 运行 AgentLoop
                # 注意：确保 agent_loop 返回的是模型解析后的完整内容
                self.logger.log_harness_to_llm(f"Stage1 ReAct agent, round {step_count}, task ID {task_id}","Task Execution", messages)
                raw_response = agent_loop(messages, logger=self.logger)
                
                # 2. 防御性获取模型输出 (直接访问属性，避免 .get() 报错)
                # 这里假设 response 遵循 OpenAI 结构
                content = getattr(raw_response, 'content', str(raw_response))

                # 4. “成功协议”握手 (JSON 协议优先)
                if '"status": "completed"' in content:
                    return True, content

                # 5. 必须将本轮输出追加回 messages，这是维持 ReAct 逻辑链条的关键！
                messages.append({"role": "last result", "content": content})
                messages.append({"role":"system", "content":"if you think the task is finished, write in json format in the content \"{ \"status\": \"completed\" }\" to declare the success of the task. if task is not finished, find the true reason why the task failed, and fix with tool_calls"})
                
            except Exception as e:
                error_msg = f"Round {step_count} crashed: {str(e)}"
                self.logger.log_info("Max steps reached, return to planner", error_msg, color=self.logger.C_SYSTEM_ERROR)
                # [工业熔断]：代码级崩溃，必须立即停止，将控制权交还 Orchestrator 进行重规划
                return False, error_msg
        
        return False, "Max steps reached."


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
        task_description = {"context": current_step["task"], "task": current_step["context"], "status": current_step["status"]} 
        
        if not current_step:
            break
        
        success, final_observation = executor.execute_single_task(current_step["id"], task_description)
        
        # 3. 闭环更新（这一步最丝滑）
        status = "success" if success else "failure"
        planner.update_task_status(current_step["id"], status, final_observation)
        # logger.log_harness_to("USER",f"Task {current_step['id']} marked as {status}.")
        
        if not success:
            # 重规划时，让 Planner 直接基于当前的 self.tasks 重新计算
            planner.tasks = planner.replan_on_failure(planner.tasks, current_step["id"], final_observation)