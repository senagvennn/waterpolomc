from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd
import yaml
from vidstab import VidStab


def configure_logging(log_dir: Path) -> logging.Logger:
    logger = logging.getLogger("stabilizer")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        file_handler = logging.FileHandler(log_dir / "stabilizer.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger


def load_config(project_root: Path) -> dict:
    with open(project_root / "waterpolo_pipeline" / "config" / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    project_root = Path(__file__).resolve().parent.parent.parent
    config = load_config(project_root)
    p = config["paths"]
    logger = configure_logging(project_root / "waterpolo_pipeline" / p["logs_dir"])
    
    logger.info("Starting video stabilization stage.")
    inventory_path = project_root / "waterpolo_pipeline" / p["outputs_dir"] / "inventory.csv"
    quality_path = project_root / "waterpolo_pipeline" / p["outputs_dir"] / "quality_scores.csv"
    
    if not inventory_path.exists() or not quality_path.exists():
        logger.error("Required prerequisite ledgers missing.")
        return
        
    inv_df = pd.read_csv(inventory_path)
    q_df = pd.read_csv(quality_path)
    merged = pd.merge(inv_df, q_df, on="video_id")
    
    processed_dir = project_root / "waterpolo_pipeline" / p["processed_dir"]
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    for _, row in merged.iterrows():
        v_id = row["video_id"]
        tier = row["quality_tier"]
        raw_path = project_root / "waterpolo_pipeline" / p["raw_data_dir"] / str(row["file_name"])
        
        if tier == "REJECT":
            continue
            
        if tier in ["Tier B", "Tier C"]:
            logger.info("Initializing motion compensation for asset %s (%s)", v_id, tier)
            stab_path = processed_dir / f"{v_id}_stabilized.mp4"
            
            win = config["video_processing"]["stabilization_smoothing_window_tier_b"] if tier == "Tier B" else config["video_processing"]["stabilization_smoothing_window_tier_c"]
            
            try:
                stabilizer = VidStab(kp_method="GFTT")
                stabilizer.stabilize(input_path=str(raw_path), output_path=str(stab_path), smoothing_window=win, border_type="replicate")
                logger.info("Stabilization successfully completed for %s", v_id)
            except Exception as e:
                logger.error("VidStab core engine crashed on video %s: %s", v_id, e)
        else:
            logger.info("Asset %s is Tier A. Skipping stabilization layer.", v_id)


if __name__ == "__main__":
    main()
