import os
from pathlib import Path

# Layout (Render's workdir is repo root: /opt/render/project/src)
PROJECT_ROOT = Path(__file__).resolve().parents[1]               # repo root
BP_ROOT      = Path(os.environ.get("BP_REPO_ROOT", PROJECT_ROOT / "BubblePanel-main")).resolve()

# Uploads live under backend/data/uploads by default (customize via env)
UPLOAD_DIR   = Path(os.environ.get("BP_UPLOAD_DIR", PROJECT_ROOT / "backend" / "data" / "uploads")).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Child process config
PY_EXE  = os.environ.get("BP_PYTHON", "python")
SCRIPT  = os.environ.get("BP_SCRIPT", "smoke_test.py")  # relative to BP_ROOT

# Utility: normalize slashes
def norm(p: str | None) -> str | None:
    return None if p is None else p.replace("\\", "/")

# Map the UI's "/app/uploads/<name>" to the real upload directory
def map_ui_upload_path(ui_path: str) -> Path:
    ui_path = norm(ui_path) or ""
    if ui_path.startswith("/app/uploads/"):
        return UPLOAD_DIR / Path(ui_path).name
    p = Path(ui_path)
    if p.is_absolute():
        return p
    # treat relative paths as inside BubblePanel-main/
    return (BP_ROOT / ui_path.lstrip("./")).resolve()
