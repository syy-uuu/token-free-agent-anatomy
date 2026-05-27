import sys
import time
import json
import re

class AgentLogger:
    COLOR_HUMAN_INTERFACE = '\033[1;36m'   
    COLOR_BRAIN_PROTOCOL = '\033[1;33m'    
    COLOR_PHYSICAL_SANDBOX = '\033[1;35m'  
    COLOR_QUERY = '\033[1;32m'    
    COLOR_SYSTEM_ERROR = '\033[1;31m'      
    COLOR_RESET = '\033[0m'                

    def __init__(self, save_log: bool = False):
        self.save_log = save_log
        self.log_buffer = []    
        self.communication_count = 0  

    def _get_timestamp(self):
        return time.strftime("%H:%M:%S", time.localtime())

    def _record_and_print(self, colored_text: str):
        print(colored_text)
        
        if self.save_log:
            clean_text = re.sub(r'\033\[[0-9;]*m', '', colored_text)
            self.log_buffer.append(clean_text)

    def _get_prefix(self, name: str) -> str:
        self.communication_count += 1
        return f"[{self._get_timestamp()}] 🔗 [EVENT #{self.communication_count}] : {name}"

    def log_user_to_harness(self, query: str):
        """1. USER ➔ HARNESS"""
        header = f"\n{self.COLOR_HUMAN_INTERFACE}{self._get_prefix('USER ➔ HARNESS')}{self.COLOR_RESET}"
        body = f"{self.COLOR_HUMAN_INTERFACE}{query.strip()}{self.COLOR_RESET}\n" + "—"*60
        self._record_and_print(header + "\n" + body)

    def log_harness_to_llm(self, messages: list):
        """2. HARNESS ➔ LLM"""
        total_messages = len(messages) if isinstance(messages, list) else 1
        header = f"\n{self.COLOR_BRAIN_PROTOCOL}{self._get_prefix('HARNESS ➔ LLM (waiting for response)')}{self.COLOR_RESET}"
        meta_info = f"Total {total_messages} messages in this turn, the last message is:"
        if isinstance(messages, list) and len(messages) > 0:
            last_msg = messages[-1]
            content_detail = f"Role: [{last_msg.get('role')}]\nContent:\n{last_msg.get('content', '').strip()}"
        else:
            content_detail = str(messages).strip()
        body = f"{self.COLOR_BRAIN_PROTOCOL}{meta_info}\n{content_detail}{self.COLOR_RESET}\n" + "—"*60
        self._record_and_print(header + "\n" + body)

    def log_llm_to_harness(self, raw_output: str):
        """3. LLM ➔ HARNESS"""
        header = f"\n{self.COLOR_BRAIN_PROTOCOL}{self._get_prefix('LLM ➔ HARNESS (Brain Thought & Action)')}{self.COLOR_RESET}"
        body = f"{self.COLOR_BRAIN_PROTOCOL}{raw_output.strip()}{self.COLOR_RESET}\n" + "—"*60
        self._record_and_print(header + "\n" + body)

    def log_harness_to_system(self, tool_name: str, args: str):
        """4. HARNESS ➔ SYSTEM"""
        header = f"\n{self.COLOR_PHYSICAL_SANDBOX}{self._get_prefix('HARNESS ➔ SYSTEM (Trigger physical action)')}{self.COLOR_RESET}"
        body = f"{self.COLOR_PHYSICAL_SANDBOX}Executing Tool: {tool_name}\nArguments: {args.strip()}{self.COLOR_RESET}\n" + "—"*60
        self._record_and_print(header + "\n" + body)

    def log_system_to_harness(self, tool_name: str, observation: str, is_error: bool = False):
        """5. SYSTEM ➔ HARNESS"""
        color = self.COLOR_SYSTEM_ERROR if is_error else self.COLOR_PHYSICAL_SANDBOX
        prefix = "🚨 CRITICAL EXCEPTION" if is_error else "SUCCESS"
        header = f"\n{color}{self._get_prefix(f'SYSTEM ➔ HARNESS (Observation | {prefix})')}{self.COLOR_RESET}"
        body = f"{color}From Tool: {tool_name}\nResult:\n{observation.strip()}{color}\n" + "—"*100
        self._record_and_print(header + "\n" + body)

    def log_harness_to_user(self, final_answer: str):
        """6. HARNESS ➔ USER"""
        header = f"\n{self.COLOR_HUMAN_INTERFACE}{self._get_prefix('HARNESS ➔ USER (Final Delivery Answer)')}{self.COLOR_RESET}"
        body = f"{self.COLOR_HUMAN_INTERFACE}{final_answer.strip()}{self.COLOR_RESET}\n" + "=================================================="
        self._record_and_print(header + "\n" + body)

    def flush_to_disk(self, file_name="sample_log.txt"):

        if self.save_log and self.log_buffer:
            with open(file_name, "w", encoding="utf-8") as f:
                f.write("\n".join(self.log_buffer))
            print(f"\n💾 [SYSTEM INFO]: logger saved to: {file_name} (totally {self.communication_count} times communication)")