import os
from pathlib import Path

# Render Docker listens on port 10000; your Dockerfile already uses that.
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # repo root (/app)
BP_ROOT      = Path(os.environ.get("BP_REPO_ROOT", PROJECT_ROOT / "BubblePanel-main")).resolve()

# Upload dir (mapped from /app/uploads)
UPLOAD_DIR   = Path(os.environ.get("BP_UPLOAD_DIR", "/app/uploads")).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Child process config
PY_EXE  = os.environ.get("BP_PYTHON", "python")
SCRIPT  = os.environ.get("BP_SCRIPT", "smoke_test.py")  # relative to BP_ROOT

def norm(p: str | None) -> str | None:
    return None if p is None else p.replace("\\", "/")

def map_ui_upload_path(ui_path: str) -> Path:
    """Map UI path (/app/uploads/xxx) or relative paths to real files."""
    ui_path = norm(ui_path) or ""
    if ui_path.startswith("/app/uploads/"):
        return UPLOAD_DIR / Path(ui_path).name
    p = Path(ui_path)
    if p.is_absolute():
        return p
    return (BP_ROOT / ui_path.lstrip("./")).resolve()
