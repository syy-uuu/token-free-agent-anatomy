import time
import re

class AgentLogger:
    # 身份色彩协议定义 (Identity Color Protocol)
    C_USER = '\033[36m'      # Cyan (用户接口)
    C_PLANNER = '\033[93m'   # Bright Yellow (战略指挥)
    C_EXECUTOR = '\033[95m'  # Purple (战术执行)
    C_HARNESS = '\033[92m'   # Bright Green (物理调度)
    C_SYSTEM = '\033[91m'    # Red (物理沙盒异常)
    C_RESET = '\033[0m'

    COLORS = {
        "USER": C_USER, "PLANNER": C_PLANNER, "EXECUTOR": C_EXECUTOR,
        "HARNESS": C_HARNESS, "SYSTEM": C_SYSTEM
    }

    def __init__(self, save_log: bool = False):
        self.save_log = save_log
        self.log_buffer = []    
        self.message_history = [] 
        self.event_count = 0  
        self.step_count = 0

    def _get_timestamp(self):
        return time.strftime("%H:%M:%S", time.localtime())

    def _get_prefix(self, name: str) -> str:
        self.event_count += 1
        return f"[{self._get_timestamp()}] 🔗 [EVENT #{self.event_count}] : {name}"

    def _format_log(self, prefix: str, color: str, content: str) -> str:
        """统一的日志格式协议"""
        header = f"\n{color}{self._get_prefix(prefix)}{self.C_RESET}"
        body = f"{color}{content.strip()}{self.C_RESET}\n" + "—"*60
        return f"{header}\n{body}"

    def _record_and_print(self, colored_text: str, summary: str = ""):
        print(colored_text)
        if self.save_log:
            clean_text = re.sub(r'\033\[[0-9;]*m', '', colored_text)
            self.log_buffer.append(clean_text)
            if summary: self.message_history.append(summary)

    def audit(self, source: str, target: str, payload_type: str, content: str, result: str = None, color: str = None):
            """
            [核心审计协议]
            强制规范：所有交互必须经过此管道，确保 Event ID, 角色, 类型, 内容, 结果对齐。
            """
            self.event_count += 1
            self.step_count += 1
            
            # 根据 source 自动匹配颜色，如果指定了 color 则覆盖
            color = color or self.COLORS.get(source, self.C_RESET)
            
            # 构建头部
            header = f"\n[{self._get_timestamp()}] 🔗 [EVENT #{self.event_count}] : {source} ➔ {target}"
            
            # 构建审计正文
            body_lines = [
                f"Type: {payload_type}",
                f"Content: {content.strip()}"
            ]
            if result:
                body_lines.append(f"Result: {result.strip()}")
                
            full_log = f"{color}{header}\n" + "\n".join(body_lines) + f"\n{'-'*60}{self.C_RESET}"
            
            # 打印并归档
            print(full_log)
            if self.save_log:
                clean_text = re.sub(r'\033\[[0-9;]*m', '', full_log)
                self.log_buffer.append(clean_text)

    # ==========================================
    # STAGE 1 roles: user -- harness -- LLM -- system
    # ==========================================
    def log_user_to_harness(self, query: str):
        self.audit("USER", "HARNESS", "Message", query, color=self.C_USER)

    def log_harness_to_user(self, final_answer: str):
        self.audit("HARNESS", "USER", "Message", final_answer, color=self.C_HARNESS)

    def log_harness_to_llm(self, messages: list):
        total_messages = len(messages) if isinstance(messages, list) else 1
        summary = f"{total_messages} messages, latest: '{messages[-1].get('content', '')}'" if isinstance(messages, list) else str(messages)
        self.audit("HARNESS", "LLM", "Message History", summary, color=self.C_HARNESS)

    def log_llm_to_harness(self, raw_output: str):
        self.audit("LLM", "HARNESS", "Raw Output", raw_output, color=self.C_PLANNER)

    def log_harness_to_system(self, tool_name: str, args: str):
        content = f"Executing Tool: {tool_name}\nArguments: {args}"
        self.audit("HARNESS", "SYSTEM", "Tool Call", content, color=self.C_HARNESS) 


    def log_system_to_harness(self, tool_name, observation, is_error=False):
        color = self.C_SYSTEM if is_error else self.C_HARNESS
        self.audit("SYSTEM", "HARNESS", "Observation", f"Tool: {tool_name}", result=observation, color=color)

    # ==========================================
    # STAGE 2 roles: user -- harness -- planner -- executor -- system
    # ==========================================

    def log_planner_to_executor(self, task: str):
        self.audit("PLANNER", "EXECUTOR", "Task Directive", task, color=self.C_PLANNER)
    
    def log_executor_to_planner(self, result: str):
        self.audit("EXECUTOR", "PLANNER", "Execution Result", result, color=self.C_EXECUTOR)
    
    def log_planner_to_harness(self, directive: str):
        self.audit("PLANNER", "HARNESS", "Directive", directive, color=self.C_PLANNER)
    
    def log_harness_to_planner(self, response: str):
        self.audit("HARNESS", "PLANNER", "Execution Feedback", response, color=self.C_HARNESS)
    
    def log_harness_to_executor(self, tool_name: str, args: str):
        content = f"Requesting execution of Tool: {tool_name}\nWith Arguments: {args}"
        self.audit("HARNESS", "EXECUTOR", "Execution Request", content, color=self.C_HARNESS)

    def log_executor_to_harness(self, observation: str):
        self.audit("EXECUTOR", "HARNESS", "Execution Observation", observation, color=self.C_EXECUTOR)



    # ==========================================
    # 磁盘归档
    # ==========================================
    def flush_to_disk(self, file_name="sample_log.txt"):
        if self.save_log and self.log_buffer:
            with open(file_name, "w", encoding="utf-8") as f:
                f.write("\n".join(self.log_buffer))
            print(f"\n💾 [SYSTEM INFO]: logger saved to: {file_name}")