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
    
    logger = AgentLogger(save_log=SHOULD_SAVE)
    
    print("select agent:")
    print(" [1] Stage 1: Standard ReAct Loop)")
    print(" [2] Stage 2: Plan to do (coming soon)")
    print(" [q] Quit")
    print("-" * 50)
    
    choice = input("请输入编号 [1/2/q]: ").strip()
    
    if choice == '1':
        config.set_stage_workdir("stage1")
        print("\n🚀  in processing: Stage 1 ReAct ...\n")
        from agents.s1_ReAct import agent_loop
        history = []
        while True:
            try:
                prompt = f"{AgentLogger.COLOR_QUERY}Enter query (Press Enter twice to send, 'q' to quit):\n {AgentLogger.COLOR_RESET}"
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
            if SHOULD_SAVE:
                history_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logger_history")
                os.makedirs(history_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M")
                log_filename = f"stage1_{timestamp}.txt"               
                full_log_path = os.path.join(history_dir, log_filename)
                logger.flush_to_disk(full_log_path)
            
    elif choice == '2':
        config.set_stage_workdir("stage2")
        print("\n🚀  in processing: Stage 2 Plan to Do...\n")
        
        # Import the Dual-Loop Orchestrator core
        from agents.s2_Plantodo import run_orchestrator
        
        try:
            prompt = f"{AgentLogger.COLOR_QUERY}Enter your complex macro-level goal (Press Enter twice to send, 'q' to quit):\n {AgentLogger.COLOR_RESET}"
            user_goal = get_multiline_input(prompt)
        except (EOFError, KeyboardInterrupt):
            return
            
        if user_goal.strip().lower() in ("q", "exit", ""):
            return
            
        # 1. Capture the macro-intent and route it to the Orchestrator
        logger.log_user_to_harness(user_goal)
        
        # Trigger the Dual-Loop execution (Planner -> todo.json -> Executor ReAct)
        run_orchestrator(user_goal)
        print()
        
        # Save the full execution transcript if specified
        if SHOULD_SAVE:
            history_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logger_history")
            os.makedirs(history_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            log_filename = f"stage2_{timestamp}.txt"               
            full_log_path = os.path.join(history_dir, log_filename)
            logger.flush_to_disk(full_log_path)
        
    elif choice.lower() == 'q':
        print("Goodbye! 。")
        return
    else:
        print("🚨 Invalid input, exiting program.")

if __name__ == "__main__":
    main()