from pathlib import Path
from typing import Union
from utils.config import config

def safe_path(p: Union[str, Path, None]) -> Path:
    """
    Ensure the path is within the workspace and resolve it.
    Safely handles None and empty string inputs.
    """
    if p is None or not str(p).strip():
        raise ValueError("Path validation failed: Path argument cannot be None or empty.")

    str_p = str(p).lstrip("/")
    
    base_dir = config.workdir.resolve()
    path = (base_dir / str_p).resolve()
    
    if not path.is_relative_to(base_dir):
        raise ValueError(f"Path escapes workspace: {p}")
        
    return path


