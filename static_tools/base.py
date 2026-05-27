from pathlib import Path
from utils.config import config

def safe_path(p: str) -> Path:
    """
    Ensure the path is within the workspace and resolve it.
    """

    base_dir = config.workdir.resolve()
    
    relative_p = p.lstrip("/")
    
    path = (base_dir / relative_p).resolve()
    
    if not path.is_relative_to(base_dir):
        raise ValueError(f"Path escapes workspace: {p}")
        
    return path


