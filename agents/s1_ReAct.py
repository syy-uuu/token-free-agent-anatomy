import json

from utils.logger import AgentLogger
from utils.config import config
from static_tools import STATIC_SCHEMAS, STATIC_HANDLERS


client = config.client
MODEL = config.model
SYSTEM = (
    f"You are a hardcore token-free coding agent at {config.workdir}. Use tools to solve tasks.\n"
    f"CRITICAL RULES:\n"
    f"1. ACT, DO NOT EXPLAIN. Never just type code blocks in text (content). You must physically write files using 'write_file' and physically execute commands using 'bash'.\n"
    f"2. CLI ENTRYPOINT REQUIREMENT: Any Python script you write MUST contain a proper '__main__' block or executing logic that explicitly prints (sys.stdout) the results to the terminal, otherwise bash will return no output.\n"
    f"3. BUG LOOP PREVENTION: If your bash command returns no output or unexpected results, do not repeat the same command. You must check the file content, rewrite the script to add print statements or debugging info, and re-run."
)


def agent_loop(state: list, logger):
    turn_counter = 0
    while True:
        turn_counter += 1
        
        # 2. HARNESS ➔ LLM
        logger.log_harness_to_llm(state)
        
        current_tool_choice = "required" if turn_counter == 1 else "auto"
        response = client.chat.completions.create(
            model=MODEL,
            messages=state,
            tools=STATIC_SCHEMAS,
            tool_choice=current_tool_choice,
        )

        message = response.choices[0].message
        state.append(message)
        
        # 3. LLM ➔ HARNESS
        raw_brain_output = ""
        if message.content:
            raw_brain_output += f"[Message]: {message.content}\n"
        if message.tool_calls:
            for tc in message.tool_calls:
                raw_brain_output += f"[Tool Call]: {tc.function.name}({tc.function.arguments})"
        
        logger.log_llm_to_harness(raw_brain_output)

        # 4. LLM ➔ USER / HARNESS ➔ SYSTEM 决策点
        if message.content and not message.tool_calls:
            logger.log_harness_to_user(message.content)

            if turn_counter == 1:
                state.append({"role": "user", "content": "Please proceed with the tool executions now."})
                continue

        if message.tool_calls:
            tool_call = message.tool_calls[0]  
            
            # 4-1. HARNESS ➔ SYSTEM
            logger.log_harness_to_system(tool_name=tool_call.function.name, args=tool_call.function.arguments)
            
            is_error = False
            try:
                if tool_call.function.name in STATIC_HANDLERS:
                    result = STATIC_HANDLERS[tool_call.function.name](**json.loads(tool_call.function.arguments))
                else:
                    result = f"Error: Unknown tool '{tool_call.function.name}'"
                    is_error = True
            except Exception as e:
                result = f"Runtime Error during execution: {str(e)}"
                is_error = True
            
            # 5. SYSTEM ➔ HARNESS
            logger.log_system_to_harness(tool_name=tool_call.function.name, observation=result, is_error=is_error)
            
            state.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })
            continue
        break  
