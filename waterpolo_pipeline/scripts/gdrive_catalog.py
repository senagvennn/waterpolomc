from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yaml

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

FILENAME_PATTERN = re.compile(
    r"^\d{8}_[A-Za-z0-9]+_[A-Za-z0-9]+_P[1-4]_Cam[A-B]$"
)

INVENTORY_COLUMNS = [
    "video_id",
    "drive_file_id",
    "file_name",
    "file_ext",
    "file_size_bytes",
    "duration_s",
    "fps",
    "width",
    "height",
    "codec",
    "date_extracted",
    "match_date",
    "team_a",
    "team_b",
    "period_cam",
]


def configure_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("gdrive_catalog")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        file_handler = logging.FileHandler(
            log_dir / "gdrive_catalog.log", encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    return logger


def load_config(project_root: Path) -> dict:
    config_path = project_root / "waterpolo_pipeline" / "config" / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_drive_service(project_root: Path, config: dict, logger: logging.Logger) -> Optional[tuple]:
    creds = None
    cfg_drive = config["google_drive"]
    token_path = project_root / "waterpolo_pipeline" / cfg_drive["token_file"]
    creds_path = project_root / "waterpolo_pipeline" / cfg_drive["credentials_file"]
    scopes = cfg_drive["scopes"]

    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        except Exception as e:
            logger.warning("Token file validation failed: %s", e)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning("Token refresh failed: %s. Initiating full flow.", e)
                creds = None
        
        if not creds:
            if not creds_path.exists():
                logger.error("credentials.json not found at %s. Falling back to local search.", creds_path)
                return None
            try:
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), scopes)
                creds = flow.run_local_server(port=0)
                with open(token_path, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())
            except Exception as e:
                logger.error("OAuth2 Native Flow failed: %s. Local fallback activated.", e)
                return None

    try:
        service = build("drive", "v3", credentials=creds)
        return service
    except Exception as e:
        logger.error("Failed to build Drive client stub: %s", e)
        return None


def get_video_metadata(video_path: Path, logger: logging.Logger) -> Optional[Dict]:
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate,width,height,codec_name,duration:format=duration,size",
            "-of", "json",
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        stream = data.get("streams", [{}])[0]
        fmt = data.get("format", {})
        
        duration = float(stream.get("duration", fmt.get("duration", 0.0)))
        size = int(fmt.get("size", video_path.stat().st_size))
        width = int(stream.get("width", 0))
        height = int(stream.get("height", 0))
        codec = stream.get("codec_name", "unknown")
        
        fps_raw = stream.get("r_frame_rate", "25/1")
        if "/" in fps_raw:
            num, den = map(int, fps_raw.split("/"))
            fps = round(num / den, 2) if den != 0 else 25.0
        else:
            fps = float(fps_raw)
            
        return {
            "duration_s": duration,
            "file_size_bytes": size,
            "width": width,
            "height": height,
            "codec": codec,
            "fps": fps
        }
    except Exception as e:
        logger.error("ffprobe operational error for %s: %s", video_path.name, e)
        return None


def scan_local_videos(raw_dir: Path, logger: logging.Logger) -> List[Dict]:
    rows = []
    if not raw_dir.exists():
        raw_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Created missing raw directory: %s", raw_dir)
        return rows

    for path in sorted(raw_dir.rglob("*.mp4")):
        stem = path.stem
        if not FILENAME_PATTERN.match(stem):
            logger.warning("Strict filename mismatch regex guard skipped: %s", path.name)
            continue
            
        parts = stem.split("_")
        match_date = parts[0]
        team_a = parts[1]
        team_b = parts[2]
        period_cam = f"{parts[3]}_{parts[4]}"
        
        meta = get_video_metadata(path, logger)
        if meta is None:
            continue
            
        rows.append({
            "video_id": stem,
            "drive_file_id": "LOCAL_FALLBACK",
            "file_name": path.name,
            "file_ext": path.suffix.lower(),
            "file_size_bytes": meta["file_size_bytes"],
            "duration_s": meta["duration_s"],
            "fps": meta["fps"],
            "width": meta["width"],
            "height": meta["height"],
            "codec": meta["codec"],
            "date_extracted": datetime.utcnow().isoformat(),
            "match_date": match_date,
            "team_a": team_a,
            "team_b": team_b,
            "period_cam": period_cam,
        })
    return rows


def save_inventory(rows: List[Dict], inventory_path: Path, logger: logging.Logger) -> None:
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    new_df = pd.DataFrame(rows, columns=INVENTORY_COLUMNS)
    
    if inventory_path.exists():
        try:
            existing_df = pd.read_csv(inventory_path)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df = combined_df.drop_duplicates(subset=["video_id"]).reset_index(drop=True)
        except Exception:
            combined_df = new_df
    else:
        combined_df = new_df

    combined_df.to_csv(inventory_path, index=False)
    logger.info("inventory.csv ledger committed securely: %s unique rows indexed.", len(combined_df))


def main():
    project_root = Path(__file__).resolve().parent.parent.parent
    config = load_config(project_root)
    logger = configure_logging(project_root / "waterpolo_pipeline" / config["paths"]["logs_dir"])
    
    logger.info("Beginning gdrive_catalog build process.")
    
    raw_dir = project_root / "waterpolo_pipeline" / config["paths"]["raw_data_dir"]
    outputs_dir = project_root / "waterpolo_pipeline" / config["paths"]["outputs_dir"]
    inventory_path = outputs_dir / "inventory.csv"
    
    _ = create_drive_service(project_root, config, logger)
    
    inventory_rows = scan_local_videos(raw_dir, logger)
    save_inventory(inventory_rows, inventory_path, logger)


if __name__ == "__main__":
    main()
