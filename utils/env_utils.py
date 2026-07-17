import os
import sys
import json
import re
from static_tools.base import safe_path
import shutil

def clean_and_parse_json_line(line: str):
    """
    Production-grade defensive probe: cleans malformed JSON artifacts caused by LLM attention dilution.
    Example: {"name": "...", "arguments": {...}}} -> one extra trailing }.
    """
    line = line.strip()
    if not line:
        return None
        
    # Try direct parsing first
    try:
        return json.loads(line)
    except Exception:
        pass

    # Defensive self-healing: if parsing fails due to an extra closing brace, trim it
    # Check from the right side for the last valid JSON closure
    if line.endswith("}}}"):
        try:
            return json.loads(line[:-1]) # Remove the final extra }
        except Exception:
            pass

    # Fallback: use regex to extract the outermost matching {} block
    try:
        match = re.search(r'(\{.*?\})(?=\s*$)|\{.*\}', line)
        if match:
            return json.loads(match.group(0))
    except Exception:
        pass
        
    return None


def generate_dynamic_tree(start_dir=".", max_depth=3):
    # Folders/files to ignore
    ignored_dirs = {'.git', '__pycache__', '.venv', 'node_modules', '.pytest_cache'}
    
    tree_lines = ["."]
    
    def _build_tree(current_dir, depth):
        if depth > max_depth:
            return
        
        try:
            # Get all files/folders in the current directory and sort for stable output
            items = sorted(os.listdir(current_dir))
        except PermissionError:
            return

        for index, item in enumerate(items):
            if item in ignored_dirs:
                continue
                
            path = os.path.join(current_dir, item)
            is_last = (index == len(items) - 1)
            connector = "└── " if is_last else "├── "
            
            # Add current line
            tree_lines.append(f"{'    ' * (depth - 1)}{connector}{item}")
            
            # If this is a directory, recurse into it
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
                    shutil.rmtree(item_path)  # Recursively delete subdirectories
                else:
                    os.remove(item_path)      # Delete files
            except Exception as e:
                print(f"⚠️ Failed to delete {item_path}: {e}")


# Called when the Harness assembles the Executor prompt:
# current_tree_str = generate_dynamic_tree(workdir)