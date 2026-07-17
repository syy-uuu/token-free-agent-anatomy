import os
import sys
from utils.config import config, get_multiline_input
from utils.env_utils import clean_directory

# Tell Pydantic to ignore expected type warnings during serialization
os.environ["PYDANTIC_ERRORS_OMIT_URL"] = "1" 
import warnings
# Force Python's warnings module to silence various unexpected-value serialization warnings from Pydantic
warnings.filterwarnings("ignore", message="Pydantic serializer warnings")

# 1. Physical safeguard: since execution starts at the repo root, this ensures all subdirectories (agents, utils) are importable
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
    

    print(f"Current model: {config.model}")
    print("select agent:")
    print(" [1] Stage 1: Standard ReAct Loop)")
    print(" [2] Stage 2: Plan to do")
    print(" [q] Quit")
    print("-" * 50)
    
    choice = input("Type your choice [1/2/q]: ").strip()
    
    if choice == '1':
        logger = AgentLogger(save_log=SHOULD_SAVE, stage_name="stage1")
        # clean_directory("test/stage1")
        config.set_stage_workdir("stage1")
        print("\n🚀  in processing: Stage 1 ReAct ...\n")
        from agents.s1_ReAct import agent_loop
        SYSTEM = (
                f"You are a hardcore token-free coding agent at {config.workdir}. Use tools to solve tasks.\n"
                f"CRITICAL RULES:\n"
                f"1. ACT, DO NOT EXPLAIN. Never just type code blocks in text (content). YOU MUST use tool_calls method in your messageswhen you want to use any tools.\n"
                f"2. CLI ENTRYPOINT REQUIREMENT: Any Python script you write MUST contain a proper '__main__' block or executing logic that explicitly prints (sys.stdout) the results to the terminal, otherwise bash will return no output.\n"
                f"3. BUG LOOP PREVENTION: If your bash command returns no output or unexpected results, do not repeat the same command. You must check the file content, rewrite the script to add print statements or debugging info, and re-run."
                        )
        history = [{"role":"system","content":SYSTEM}]

        while True:
            try:
                prompt = f"{AgentLogger.C_USER}Enter query (Press Enter twice to send, 'q' to quit):\n {AgentLogger.C_RESET}"
                user_goal = get_multiline_input(prompt)
            except (EOFError, KeyboardInterrupt):
                break
                
            if user_goal.strip().lower() in ("q", "exit", ""):
                break
            if len(history) > 20:
                history = [history[0]] + history[-10:]                
            #1. USER ➔ HARNESS
            logger.log_user_to("HARNESS ➔ LLM", "Message", user_goal)
            history.append({"role": "user", "content": user_goal})
            agent_loop(history, logger)
            print()

            
    elif choice == '2':
        logger = AgentLogger(save_log=SHOULD_SAVE, stage_name="stage2")
        # clean_directory("test/stage2")
        config.set_stage_workdir("stage2")
        print("\n🚀  in processing: Stage 2 Plan to Do...\n")
        # Import the Dual-Loop Orchestrator core
        from agents.s2_Plantodo import run_orchestrator
        
        try:
            prompt = f"{AgentLogger.C_USER}Enter your query (Press Enter twice to send, 'q' to quit):\n {AgentLogger.C_RESET}"
            user_goal = get_multiline_input(prompt)
        except (EOFError, KeyboardInterrupt):
            return
            
        if user_goal.strip().lower() in ("q", "exit", ""):
            return
        
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