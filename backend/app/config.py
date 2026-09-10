import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.environ["DB_URL"]

# paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SCRIPTS_DIR = BASE_DIR / "scripts"