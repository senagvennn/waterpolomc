from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np
import pandas as pd
import yaml


def configure_logging(log_dir: Path) -> logging.Logger:
    logger = logging.getLogger("scene_filter")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        file_handler = logging.FileHandler(log_dir / "scene_filter.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger


def main():
    project_root = Path(__file__).resolve().parent.parent.parent
    with open(project_root / "waterpolo_pipeline" / "config" / "config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    p = config["paths"]
    logger = configure_logging(project_root / "waterpolo_pipeline" / p["logs_dir"])
    logger.info("Starting frame level scene filtration stage.")
    
    inventory_path = project_root / "waterpolo_pipeline" / p["outputs_dir"] / "inventory.csv"
    if not inventory_path.exists():
        return
        
    inv_df = pd.read_csv(inventory_path)
    th = config["quality_thresholds"]
    manifest_dir = project_root / "waterpolo_pipeline" / p["manifests_dir"]
    manifest_dir.mkdir(parents=True, exist_ok=True)
    
    for _, row in inv_df.iterrows():
        v_id = row["video_id"]
        raw_path = project_root / "waterpolo_pipeline" / p["raw_data_dir"] / str(row["file_name"])
        
        cap = cv2.VideoCapture(str(raw_path))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        valid_segments = []
        in_segment = False
        start_frame = 0
        
        for f_idx in range(total_frames):
            ret, frame = cap.read()
            if not ret:
                break
                
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            lower = np.array([th["pool_hsv_hue_low"], th["pool_hsv_sat_low"], th["pool_hsv_val_low"]])
            upper = np.array([th["pool_hsv_hue_high"], 255, 255])
            mask = cv2.inRange(hsv, lower, upper)
            
            ratio = np.count_nonzero(mask) / (frame.shape[0] * frame.shape[1])
            is_valid_pool = (ratio >= th["pool_coverage_min"])
            
            if is_valid_pool:
                if not in_segment:
                    start_frame = f_idx
                    in_segment = True
            else:
                if in_segment:
                    valid_segments.append({"sample_start_index": start_frame, "sample_end_index": f_idx - 1, "status": "VALID_PLAY_ZONE"})
                    in_segment = False
                    
        if in_segment:
            valid_segments.append({"sample_start_index": start_frame, "sample_end_index": total_frames - 1, "status": "VALID_PLAY_ZONE"})
            
        cap.release()
        
        out_file = manifest_dir / f"segment_manifest_{v_id}.json"
        payload = {"video_id": v_id, "total_frames_scanned": total_frames, "valid_segments": valid_segments, "generated_at": datetime.utcnow().isoformat()}
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
        logger.info("Generated segment manifest validity map for %s", v_id)


if __name__ == "__main__":
    main()
