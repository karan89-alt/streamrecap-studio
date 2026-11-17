import os
import shutil
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
CLIPS_DIR = STORAGE_DIR / "clips"
SCRIPTS_DIR = STORAGE_DIR / "scripts"
AUDIO_DIR = STORAGE_DIR / "audio"
EXPORTS_DIR = STORAGE_DIR / "exports"
TEMP_DIR = STORAGE_DIR / "temp"

# Ensure all directories exist
for folder in [CLIPS_DIR, SCRIPTS_DIR, AUDIO_DIR, EXPORTS_DIR, TEMP_DIR]:
    folder.mkdir(parents=True, exist_ok=True)


def find_executable(name: str) -> str:
    """Finds an executable in PATH or known WinGet / local installation locations."""
    # 1. Direct which lookup
    exe = shutil.which(name)
    if exe and os.path.exists(exe):
        return exe

    # 2. Check WinGet Gyan.FFmpeg installation directory
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_pattern = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_pattern.exists():
            for match in winget_pattern.glob(f"**/{name}.exe"):
                if match.is_file():
                    return str(match)

    # 3. Check C:\ProgramData or C:\ffmpeg
    for candidate in [
        Path(f"C:\\ffmpeg\\bin\\{name}.exe"),
        Path(f"C:\\Program Files\\ffmpeg\\bin\\{name}.exe"),
    ]:
        if candidate.exists():
            return str(candidate)

    return name  # fallback to name


class Settings(BaseSettings):
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ELEVENLABS_API_KEY: Optional[str] = None
    ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"  # Default expressive voice
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = True
    FFMPEG_PATH: str = find_executable("ffmpeg")
    FFPROBE_PATH: str = find_executable("ffprobe")

    class Config:
        env_file = str(BASE_DIR / ".env")
        extra = "ignore"


settings = Settings()
