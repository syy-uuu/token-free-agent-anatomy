from pathlib import Path
from typing import Union
from utils.config import config

def safe_path(p: Union[str, Path, None]) -> Path:
    """
    Ensure the path is within the workspace and resolve it.
    Safely handles None and empty string inputs.
    """
    # 卫士代码：如果传进来的是 None 或者空字符串，立刻物理熔断
    if p is None or not str(p).strip():
        raise ValueError("Path validation failed: Path argument cannot be None or empty.")

    # 确保转换为字符串进行处理
    str_p = str(p).lstrip("/")
    
    # 假设你的 config.workdir 已经在别处定义好
    base_dir = config.workdir.resolve()
    path = (base_dir / str_p).resolve()
    
    if not path.is_relative_to(base_dir):
        raise ValueError(f"Path escapes workspace: {p}")
        
    return path


