import time
import re
import json
from pathlib import Path

class AgentLogger():
    # Identity Color Protocol
    C_USER = '\033[36m'      # Cyan (user interface)
    C_PLANNER = '\033[93m'   # Bright Yellow (strategic planning)
    C_EXECUTOR = '\033[95m'  # Purple (tactical execution)
    C_HARNESS = '\033[92m'   # Bright Green (orchestration)
    C_SYSTEM = '\033[90m'    # Grey (system message)
    C_SYSTEM_ERROR = '\033[91m'    # Red (sandbox/runtime error)
    C_INFO = '\033[94m'      # Blue (general info)
    C_RESET = '\033[0m'

    COLORS = {
        "USER": C_USER, "PLANNER": C_PLANNER, "EXECUTOR": C_EXECUTOR,
        "HARNESS": C_HARNESS, "SYSTEM_ERROR": C_SYSTEM_ERROR
    }
    
    def __init__(self, save_log: bool = False, stage_name: str = "", base_log_dir: str = "logger_history"):
        self.save_log = save_log
        self.stage_name = stage_name
        self.base_log_dir = base_log_dir
        self.log_file_path = self._prepare_log_path()
        self.log_buffer = []    
        self.message_history = [] 
        self.event_count = 0  
        self.step_count = 0

    def _prepare_log_path(self):
        log_dir = Path(self.base_log_dir) / self.stage_name
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d_%H-%M", time.localtime())
        file_path = log_dir / f"{timestamp}.log"
        return file_path

    def _get_timestamp(self):
        return time.strftime("%H:%M:%S", time.localtime())

    def _append_to_disk(self, content):
        if self.save_log and hasattr(self, 'log_file_path'):
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(content + "\n")

    def audit(self, source: str, target: str, payload_type: str, content: str, result: str = None, color: str = None):
            self.event_count += 1
            self.step_count += 1
            
            # Auto-select color by source; explicit color overrides it
            color = color or self.COLORS.get(source, self.C_RESET)
            
            # Build header
            header = f"\n[{self._get_timestamp()}] 🔗 [EVENT #{self.event_count}] : {source} ➔ {target}"
            
            # Build audit body
            body_lines = [
                f"Type: {payload_type}",
                f"Content: {content.strip()}"
            ]
            if result:
                body_lines.append(f"Result: {result.strip()}")
                
            full_log = f"{color}{header}\n" + "\n".join(body_lines) + f"\n{'-'*60}{self.C_RESET}"
            
            # Print and archive
            print(full_log)
            if self.save_log:
                clean_text = re.sub(r'\033\[[0-9;]*m', '', full_log)
                self.log_buffer.append(clean_text)
                self._append_to_disk(clean_text)
    def log_info(self, type, message: str,color=None):
        self.audit("INFO", "LOG", type, message, color=color or self.C_INFO)

    # ==========================================
    # STAGE 1 roles: user -- harness -- LLM -- system
    # ==========================================
    def log_user_to(self, target, type, query: str):
        self.audit("USER", target, type, query, color=self.C_USER)

    def log_harness_to(self, target, type, final_answer: str):
        self.audit("HARNESS", target, type, final_answer, color=self.C_HARNESS)

    def log_harness_to_llm(self, target, type, messages: list):
        total_messages = len(messages) if isinstance(messages, list) else 1
        summary = f"{total_messages} messages, latest: '{messages[-1].get('content', '')}'" if isinstance(messages, list) else str(messages)
        self.audit("HARNESS", target, type, summary, color=self.C_HARNESS)

    def log_harness_to_system(self, tool_name: str, args: str):
        content = f"Executing Tool: {tool_name}\nArguments: {args}"
        self.audit("HARNESS", "SYSTEM", "Tool Call", content, color=self.C_HARNESS) 

    def log_llm_to(self, start, target, type, raw_output: str):
        self.audit(start, target, type, raw_output, color=self.C_PLANNER)

    def log_system_to_harness(self, tool_name, observation, is_error=False):
        color = self.C_SYSTEM_ERROR if is_error else self.C_SYSTEM
        self.audit("SYSTEM", "HARNESS", "System Result", f"Tool: {tool_name}", result=observation, color=color)

    # ==========================================
    # STAGE 2 roles: user -- harness -- planner -- executor(LLM) -- system
    # ==========================================

    def log_planner_to(self, target, type, task: str):
        self.audit("PLANNER", target, type, task, color=self.C_PLANNER)
