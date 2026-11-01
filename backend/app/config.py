"""Central configuration. Every value can be overridden with an environment
variable (see backend/.env.example). Nothing here is secret."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

# The PhysioNet download unpacks into a folder with this long name. We read the
# CSV files from there directly instead of copying them, so the originals are
# never duplicated or modified.
PHYSIONET_FOLDER = "qol_stress-a-multimodal-dataset-of-physiological-and-self-reported-stress-responses-1.0.0"


def _load_dotenv() -> None:
    """Minimal .env reader so no extra dependency is needed."""
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _default_dataset_dir() -> Path:
    candidates = [
        PROJECT_DIR / "data" / "qol_stress",
        PROJECT_DIR / PHYSIONET_FOLDER / "data",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PreprocessingConfig:
    """Parameters of the segmentation protocol (documented in docs/METHODOLOGY.md)."""

    calibration_minutes: float = float(os.environ.get("CALIBRATION_MINUTES", 3))
    guard_before_questionnaire_minutes: float = float(os.environ.get("GUARD_BEFORE_STAI_MINUTES", 2))
    guard_after_relax_questionnaire_minutes: float = float(os.environ.get("GUARD_AFTER_RELAX_STAI_MINUTES", 1))
    window_seconds: int = int(os.environ.get("WINDOW_SECONDS", 60))
    min_samples_per_window: int = int(os.environ.get("MIN_SAMPLES_PER_WINDOW", 15))
    min_calibration_samples: int = int(os.environ.get("MIN_CALIBRATION_SAMPLES", 45))
    min_phase_minutes: float = float(os.environ.get("MIN_PHASE_MINUTES", 3))
    segment_minutes: float = float(os.environ.get("SEGMENT_MINUTES", 5))
    hr_valid_min: float = 30.0
    hr_valid_max: float = 220.0


@dataclass(frozen=True)
class Settings:
    dataset_dir: Path = field(default_factory=lambda: Path(os.environ.get("QOL_STRESS_DIR", str(_default_dataset_dir()))))
    db_path: Path = field(default_factory=lambda: Path(os.environ.get("APP_DB_PATH", str(BACKEND_DIR / "data" / "app.db"))))
    artifact_dir: Path = field(default_factory=lambda: Path(os.environ.get("ARTIFACT_DIR", str(BACKEND_DIR / "artifacts"))))
    upload_dir: Path = field(default_factory=lambda: Path(os.environ.get("UPLOAD_DIR", str(BACKEND_DIR / "data" / "uploads"))))
    frontend_origin: str = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
    store_screenshots: bool = _bool("STORE_SCREENSHOTS", False)
    tesseract_cmd: str | None = os.environ.get("TESSERACT_CMD") or None
    random_seed: int = int(os.environ.get("RANDOM_SEED", 42))
    cv_folds: int = int(os.environ.get("CV_FOLDS", 5))
    preprocessing: PreprocessingConfig = field(default_factory=PreprocessingConfig)


settings = Settings()


def ensure_dirs() -> None:
    for d in (settings.db_path.parent, settings.artifact_dir, settings.upload_dir):
        d.mkdir(parents=True, exist_ok=True)
