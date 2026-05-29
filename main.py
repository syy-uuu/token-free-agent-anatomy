import os
import sys
from datetime import datetime

from utils.config import config, get_multiline_input

# 1. 物理防线：由于在根目录启动，这一行将确保所有子目录（agents, utils）完美互通
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.logger import AgentLogger

def print_banner():
    banner = """
==================================================
 🔬  Token-Free Agent Anatomy
==================================================
    """
    print(banner)

def main():
    print_banner()
    
    # True to save logs to disk, False to only print in terminal.
    SHOULD_SAVE = True  
    

    
    print("select agent:")
    print(" [1] Stage 1: Standard ReAct Loop)")
    print(" [2] Stage 2: Plan to do (coming soon)")
    print(" [q] Quit")
    print("-" * 50)
    
    choice = input("请输入编号 [1/2/q]: ").strip()
    
    if choice == '1':
        logger = AgentLogger(save_log=SHOULD_SAVE, stage_name="stage1")
        config.set_stage_workdir("stage1")
        print("\n🚀  in processing: Stage 1 ReAct ...\n")
        from agents.s1_ReAct import agent_loop
        SYSTEM = (
                f"You are a hardcore token-free coding agent at {config.workdir}. Use tools to solve tasks.\n"
                f"CRITICAL RULES:\n"
                f"1. ACT, DO NOT EXPLAIN. Never just type code blocks in text (content). You must physically write files using 'write_file' and physically execute commands using 'bash'.\n"
                f"2. CLI ENTRYPOINT REQUIREMENT: Any Python script you write MUST contain a proper '__main__' block or executing logic that explicitly prints (sys.stdout) the results to the terminal, otherwise bash will return no output.\n"
                f"3. BUG LOOP PREVENTION: If your bash command returns no output or unexpected results, do not repeat the same command. You must check the file content, rewrite the script to add print statements or debugging info, and re-run."
                        )
        history = [{"role":"system","content":SYSTEM}]
        if len(history) > 20:
            history = [history[0]] + history[-10:]
        while True:
            try:
                prompt = f"{AgentLogger.C_USER}Enter query (Press Enter twice to send, 'q' to quit):\n {AgentLogger.C_RESET}"
                query = get_multiline_input(prompt)
            except (EOFError, KeyboardInterrupt):
                break
                
            if query.strip().lower() in ("q", "exit", ""):
                break
                
            #1. USER ➔ HARNESS
            logger.log_user_to_harness(query)
            history.append({"role": "user", "content": query})
            agent_loop(history, logger)
            print()

            
    elif choice == '2':
        logger = AgentLogger(save_log=SHOULD_SAVE, stage_name="stage2")
        config.set_stage_workdir("stage2")
        print("\n🚀  in processing: Stage 2 Plan to Do...\n")
        
        # Import the Dual-Loop Orchestrator core
        from agents.s2_Plantodo import run_orchestrator
        
        try:
            prompt = f"{AgentLogger.C_USER}Enter your complex macro-level goal (Press Enter twice to send, 'q' to quit):\n {AgentLogger.C_RESET}"
            user_goal = get_multiline_input(prompt)
        except (EOFError, KeyboardInterrupt):
            return
            
        if user_goal.strip().lower() in ("q", "exit", ""):
            return
            
        # 1. Capture the macro-intent and route it to the Orchestrator
        logger.log_user_to_harness(user_goal)
        
        # Trigger the Dual-Loop execution (Planner -> todo.json -> Executor ReAct)
        run_orchestrator(user_goal, logger)
        print()
    

        
    elif choice.lower() == 'q':
        print("Goodbye! 。")
        return
    else:
        print("🚨 Invalid input, exiting program.")

if __name__ == "__main__":
    main()