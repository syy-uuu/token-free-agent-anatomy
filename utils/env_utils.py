import os
import sys
import json
import re
from static_tools.base import safe_path
import shutil

def clean_and_parse_json_line(line: str):
    """
    工业级防御性探针：专门清洗大模型由于 Attention 稀释导致的非标 JSON 连击毛刺
    例如：{"name": "...", "arguments": {...}}} -> 尾部多了一个 }
    """
    line = line.strip()
    if not line:
        return None
        
    # 尝试直接解析
    try:
        return json.loads(line)
    except Exception:
        pass

    # 算法防御自愈：如果是由于尾部多写了闭合括号导致的报错，进行物理裁剪
    # 从右侧查找最后一个完美的 JSON 闭合结构
    if line.endswith("}}}"):
        try:
            return json.loads(line[:-1]) # 切掉最后一个多余的 }
        except Exception:
            pass

    # 备用方案：通过正则强行提取最外层匹配的 {} 块
    try:
        match = re.search(r'(\{.*?\})(?=\s*$)|\{.*\}', line)
        if match:
            return json.loads(match.group(0))
    except Exception:
        pass
        
    return None


def generate_dynamic_tree(start_dir=".", max_depth=3):
    # 需要忽略的文件夹或文件
    ignored_dirs = {'.git', '__pycache__', '.venv', 'node_modules', '.pytest_cache'}
    
    tree_lines = ["."]
    
    def _build_tree(current_dir, depth):
        if depth > max_depth:
            return
        
        try:
            # 获取当前目录下所有文件和文件夹，并排序以保持稳定输出
            items = sorted(os.listdir(current_dir))
        except PermissionError:
            return

        for index, item in enumerate(items):
            if item in ignored_dirs:
                continue
                
            path = os.path.join(current_dir, item)
            is_last = (index == len(items) - 1)
            connector = "└── " if is_last else "├── "
            
            # 添加当前行
            tree_lines.append(f"{'    ' * (depth - 1)}{connector}{item}")
            
            # 如果是文件夹，递归扫描
            if os.path.isdir(path):
                _build_tree(path, depth + 1)

    _build_tree(start_dir, 1)
    return "\n".join(tree_lines)

def clean_directory(path):
    full_path = safe_path(path)
    if os.path.exists(full_path):
        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)  # 递归删除子文件夹
                else:
                    os.remove(item_path)      # 删除文件
            except Exception as e:
                print(f"⚠️ Failed to delete {item_path}: {e}")


# 在 Harness 组装 Executor Prompt 时调用：
# current_tree_str = generate_dynamic_tree(workdir)