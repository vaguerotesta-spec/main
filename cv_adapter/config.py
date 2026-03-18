import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-6"
BASE_DIR = Path(__file__).parent
STORAGE_DIR = BASE_DIR / "storage"
OUTPUTS_DIR = STORAGE_DIR / "outputs"
ORIGINAL_CV_PATH = STORAGE_DIR / "original_cv.pdf"
PROMPTS_DIR = BASE_DIR / "prompts"
STORAGE_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)
