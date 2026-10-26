"""Configuration for the Risk Governance Agent (Gemma / Ollama small build)."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()

# ---------------------------------------------------------------------------
# Ollama – single Gemma model for all phases (no local fine-tuned weights in this package)
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_FALLBACK_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:2b")
OLLAMA_TIMEOUT_SECONDS = 300
OLLAMA_MAX_RETRIES = 2

# All phases use the same model (after: ollama pull gemma2:2b)
PHASE_MODELS = {
    "phase_1": "gemma2:2b",
    "phase_2": "gemma2:2b",
    "phase_3": "gemma2:2b",
    "summary": "gemma2:2b",
}

# ---------------------------------------------------------------------------
# Prompt / context budget (approximate token counts)
# ---------------------------------------------------------------------------
CHUNK_TOKEN_BUDGET = 800
MAX_OUTPUT_TOKENS = 8192
MAX_OUTPUT_TOKENS_FEEDBACK = 8192
MAX_OUTPUT_TOKENS_PHASE_1 = 4096

# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------
SUPPORTED_FILE_TYPES = [".txt", ".md", ".pdf", ".csv", ".xlsx", ".xls", ".docx"]
CHUNK_SIZE_CHARS = 3000
CHUNK_OVERLAP_CHARS = 300
CONTROL_CHUNK_SIZE_CHARS = 6000
CONTROL_CHUNK_OVERLAP_CHARS = 400

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = PROJECT_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
OUTPUTS_DIR = DATA_DIR / "outputs"

# ---------------------------------------------------------------------------
# ID prefixes
# ---------------------------------------------------------------------------
RISK_ID_PREFIX = "RISK"
CONTROL_ID_PREFIX = "CTRL"
PROCESS_ID_PREFIX = "PROC"
INPUT_RISK_MAPPING_PREFIX = "UI"
RISK_CONTROL_MAPPING_PREFIX = "RC"
CONTROL_PROCESS_MAPPING_PREFIX = "CP"

# ---------------------------------------------------------------------------
# Severity options
# ---------------------------------------------------------------------------
SEVERITY_OPTIONS = ["High", "Medium", "Low"]

# ---------------------------------------------------------------------------
# Risk categories
# ---------------------------------------------------------------------------
RISK_CATEGORIES = [
    "Compliance",
    "Operational",
    "Reporting",
    "Governance",
    "Access / Security",
    "Data / Evidence",
    "Third Party",
    "Other",
]
