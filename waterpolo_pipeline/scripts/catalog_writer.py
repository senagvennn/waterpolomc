from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
import pandas as pd
import yaml

FINAL_CATALOG_COLUMNS = [
    "video_id", "drive_file_id", "file_name", "file_size_bytes", "duration_s",
    "fps", "width", "height", "codec", "match_date", "team_a", "team_b", "period_cam",
    "q1_score", "q2_score", "q3_score", "q4_score", "q5_score", "composite_score",
    "quality_tier", "stabilized", "normalized", "stable_path", "phase2_ready", "last_modified_date"
]


def main():
    project_root = Path(__file__).resolve().parent.parent.parent
    with open(project_root / "waterpolo_pipeline" / "config" / "config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    p = config["paths"]
    inventory_path = project_root / "waterpolo_pipeline" / p["outputs_dir"] / "inventory.csv"
    quality_path = project_root / "waterpolo_pipeline" / p["outputs_dir"] / "quality_scores.csv"
    catalog_path = project_root / "waterpolo_pipeline" / p["manifests_dir"] / "video_catalog.csv"
    
    if not inventory_path.exists() or not quality_path.exists():
        return
        
    inv_df = pd.read_csv(inventory_path)
    q_df = pd.read_csv(quality_path)
    merged = pd.merge(inv_df, q_df, on="video_id")
    
    processed_dir = project_root / "waterpolo_pipeline" / p["processed_dir"]
    rows = []
    
    for _, row in merged.iterrows():
        v_id = row["video_id"]
        tier = row["quality_tier"]
        
        stabilized = "TRUE" if tier in ["Tier B", "Tier C"] and (processed_dir / f"{v_id}_stabilized.mp4").exists() else "FALSE"
        normalized = "TRUE" if tier != "REJECT" and (processed_dir / f"{v_id}_normalized.mp4").exists() else "FALSE"
        phase2_ready = "TRUE" if normalized == "TRUE" else "FALSE"
        
        stable_path_str = str((processed_dir / f"{v_id}_stabilized.mp4").relative_to(project_root)) if stabilized == "TRUE" else "NONE"
        
        rows.append({
            "video_id": v_id, "drive_file_id": row["drive_file_id"], "file_name": row["file_name"],
            "file_size_bytes": row["file_size_bytes"], "duration_s": row["duration_s"], "fps": row["fps"],
            "width": row["width"], "height": row["height"], "codec": row["codec"], "match_date": row["match_date"],
            "team_a": row["team_a"], "team_b": row["team_b"], "period_cam": row["period_cam"],
            "q1_score": row["q1_score"], "q2_score": row["q2_score"], "q3_score": row["q3_score"],
            "q4_score": row["q4_score"], "q5_score": row["q5_score"],
            "composite_score": row["composite_score"], "quality_tier": tier, "stabilized": stabilized,
            "normalized": normalized, "stable_path": stable_path_str, "phase2_ready": phase2_ready,
            "last_modified_date": datetime.utcnow().isoformat()
        })
        
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=FINAL_CATALOG_COLUMNS).to_csv(catalog_path, index=False)


if __name__ == "__main__":
    main()
