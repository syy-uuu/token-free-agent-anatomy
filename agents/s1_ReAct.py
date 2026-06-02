import json
from utils.config import config
from utils.env_utils import clean_and_parse_json_line
from static_tools import STATIC_SCHEMAS, STATIC_HANDLERS

client = config.client
MODEL = config.model

def agent_loop(state: list, logger):
    turn_counter = 0
    max_turns = 30  
    
    while turn_counter < max_turns:
        turn_counter += 1
        
        if turn_counter > 1:
            logger.log_harness_to_llm(f"Stage1 ReAct agent, turn count {turn_counter}", "Current state", state)
        
        # 1. HARNESS ➔ LLM
        # logger.log_harness_to("LLM", "Message", state)
        
        current_tool_choice = "required" if turn_counter == 1 else "auto"
        
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=state,
                tools=STATIC_SCHEMAS,
                tool_choice=current_tool_choice
            )
        except Exception as ce:
            logger.log_info("error", f"\n[TIMEOUT/ERROR] API Request failed: {str(ce)}\n")
            return f"Harness Interrupt: API Call Failed ({str(ce)})"

        message = response.choices[0].message
        # print(f"\n[Step {turn_counter}] [Debug] LLM Response: {message}\n")
        
        actions_to_execute = []
        raw_brain_output = ""

        # ==================== 【收拢解析层】 ====================

        # 轨 A：处理标准 tool_calls
        if message.tool_calls:
            for tc in message.tool_calls:
                # logger.log_info("debug","Standerd tool call detected")
                raw_brain_output += f"[Standard Tool Call]: {tc.function.name}({tc.function.arguments})\n"
                try:
                    args_dict = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                except Exception:
                    args_dict = tc.function.arguments

                actions_to_execute.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": args_dict if isinstance(args_dict, dict) else {}
                })

        # 轨 B：拦截并清洗大模型在 content 里手写的 JSON 乱象
        if message.content:
            raw_brain_output += f"[Message Text]: {message.content}\n"
            
            if not actions_to_execute:
                content_str = message.content.strip()
                
                # 逐行切开并推入物理清洗探针
                for line_idx, line in enumerate(content_str.split('\n')):
                    parsed_line = clean_and_parse_json_line(line)
                    if not parsed_line:
                        continue
                        
                    try:
                        # 支持直升根节点或嵌套在 action 对象里的定义
                        a_name = parsed_line.get("name") or parsed_line.get("action", {}).get("name")
                        a_args = parsed_line.get("arguments") or parsed_line.get("action", {}).get("arguments")
                        
                        if a_name:
                            if isinstance(a_args, str):
                                try:
                                    a_args = json.loads(a_args)
                                except Exception:
                                    pass
                            logger.log_info("debug","Extracted JSON tool call detected")
                            raw_brain_output += f"[Extracted JSON Tool]: {a_name}({json.dumps(a_args)})\n"
                            actions_to_execute.append({
                                "id": f"call_extracted_{turn_counter}_{line_idx}",
                                "name": a_name,
                                "arguments": a_args if isinstance(a_args, dict) else {}
                            })
                    except Exception:
                        pass

        # ==================== 【上下文记忆协议对齐】 ====================
        
        # 核心防空转自愈：如果抓到了轨 B 工具，在推入上下文历史前，强行转换为标准 tool_calls 格式
        if actions_to_execute and not message.tool_calls:
            aligned_tool_calls = []
            for action in actions_to_execute:
                aligned_tool_calls.append({
                    "id": action["id"],
                    "type": "function",
                    "function": {
                        "name": action["name"],
                        "arguments": json.dumps(action["arguments"], ensure_ascii=False)
                    }
                })
            message.tool_calls = aligned_tool_calls

        # 安全合流推入历史记录
        state.append(message)

        # ==================== 【决策与物理执行层】 ====================

        # 情况 1：无有效工具，属于正常自然语言结束或开场白
        if not actions_to_execute:
            if message.content:
                logger.log_harness_to("USER", "Message", message.content)

                if '{"status": "completed"}' in message.content:
                    final_output = message.content
                    return final_output
                
                if turn_counter == 1:
                    state.append({"role": "user", "content": "Please proceed with the tool executions now."})
                    continue
            
            final_output = message.content if message.content else ""
            break

        # 情况 2：并发/多连击工具物理落地
        for action in actions_to_execute:
            t_id = action["id"]
            t_name = action["name"]
            t_args = action["arguments"]
            
            # 4-1. HARNESS ➔ SYSTEM 广播
            logger.log_harness_to_system(tool_name=t_name, args=t_args)
            
            is_error = False
            try:
                if t_name in STATIC_HANDLERS:
                    # 真正物理击打磁盘和控制台
                    result = STATIC_HANDLERS[t_name](**t_args)
                else:
                    result = f"Error: Unknown tool '{t_name}'"
                    is_error = True
            except Exception as e:
                result = f"Runtime Error during execution: {str(e)}"
                is_error = True
            
            # 5. SYSTEM ➔ HARNESS 观测回传
            logger.log_system_to_harness(tool_name=t_name, observation=result, is_error=is_error)
            
            # 物理拼装回传协议树（保证每个伪造 ID 和原始定义绝对绑定）
            state.append({
                "role": "tool",
                "tool_call_id": t_id,
                "name": t_name,
                "content": str(result)
            })

        # 完成多连击，继续推进循环大盘
        continue

    else:
        final_output = f"Error: Max steps ({max_turns}) reached. Process terminated by Harness Guard."
        logger.log_info("error", final_output)
    # logger.log_info("Stage1 ReAct agent exit", message.content if message.content else "no message in this round")
    return final_output