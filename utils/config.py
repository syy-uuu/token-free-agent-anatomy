import os
from dotenv import load_dotenv
from openai import OpenAI
from pathlib import Path
import time
from datetime import datetime

# Load variables from .env file
load_dotenv()

class Config:
    def __init__(self):
        # Base settings
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.api_key = os.getenv("OLLAMA_API_KEY", "ollama")
        self.model = os.getenv("DEFAULT_MODEL", "qwen2.5:latest")
        
        # Pre-configured OpenAI client
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )
        self.workdir = Path.cwd() / "test"

    def set_stage_workdir(self, stage_name: str):
        self.workdir = Path.cwd() / "test" / stage_name
        self.workdir.mkdir(parents=True, exist_ok=True)



config = Config()

def get_multiline_input(prompt_text: str) -> str:
    print(prompt_text, end="")
    lines = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            print("\n[SYSTEM]: Goddbye!")
            import sys; sys.exit(0)
        
        if line.strip().lower() in ('q', 'exit'):
            if len(lines) == 0:  
                import sys; print("Goodbye!"); sys.exit(0)
            else:
                break

        if line == "":
            if len(lines) > 0:
                break
            else:
                continue
                
        lines.append(line)
        
    return "\n".join(lines).strip()