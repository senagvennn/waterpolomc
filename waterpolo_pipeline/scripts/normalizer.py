from __future__ import annotations

import logging
import os
from pathlib import Path
import ffmpeg
import pandas as pd
import yaml


def configure_logging(log_dir: Path) -> logging.Logger:
    logger = logging.getLogger("normalizer")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        file_handler = logging.FileHandler(log_dir / "normalizer.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger


def main():
    project_root = Path(__file__).resolve().parent.parent.parent
    with open(project_root / "waterpolo_pipeline" / "config" / "config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    p = config["paths"]
    logger = configure_logging(project_root / "waterpolo_pipeline" / p["logs_dir"])
    logger.info("Starting native FFmpeg normalization stage.")
    
    inventory_path = project_root / "waterpolo_pipeline" / p["outputs_dir"] / "inventory.csv"
    quality_path = project_root / "waterpolo_pipeline" / p["outputs_dir"] / "quality_scores.csv"
    
    if not inventory_path.exists() or not quality_path.exists():
        return
        
    inv_df = pd.read_csv(inventory_path)
    q_df = pd.read_csv(quality_path)
    merged = pd.merge(inv_df, q_df, on="video_id")
    
    processed_dir = project_root / "waterpolo_pipeline" / p["processed_dir"]
    vp = config["video_processing"]
    
    for _, row in merged.iterrows():
        v_id = row["video_id"]
        tier = row["quality_tier"]
        
        if tier == "REJECT":
            continue
            
        # Select input based on stabilization rule matrix
        if tier in ["Tier B", "Tier C"]:
            source_file = processed_dir / f"{v_id}_stabilized.mp4"
            if not source_file.exists():
                source_file = project_root / "waterpolo_pipeline" / p["raw_data_dir"] / str(row["file_name"])
        else:
            source_file = project_root / "waterpolo_pipeline" / p["raw_data_dir"] / str(row["file_name"])
            
        output_file = processed_dir / f"{v_id}_normalized.mp4"
        tmp_output = processed_dir / f"tmp_{v_id}_normalized.mp4"
        
        logger.info("Normalizing track stream layout for asset %s to H.264 standard", v_id)
        try:
            stream = ffmpeg.input(str(source_file))
            stream = ffmpeg.filter(stream, "scale", vp["target_width"], vp["target_height"])
            stream = ffmpeg.filter(stream, "fps", fps=vp["target_fps"])
            output = ffmpeg.output(stream, str(tmp_output), vcodec="libx264", crf=18, pix_fmt="yuv420p", acodec="aac", loglevel="error")
            ffmpeg.run(output, overwrite_output=True)
            
            if tmp_output.exists():
                os.replace(tmp_output, output_file)
                logger.info("Normalization completely successful for %s", v_id)
        except Exception as e:
            logger.error("FFmpeg core process rejected execution for %s: %s", v_id, e)
            if tmp_output.exists(): os.remove(tmp_output)


if __name__ == "__main__":
    main()
