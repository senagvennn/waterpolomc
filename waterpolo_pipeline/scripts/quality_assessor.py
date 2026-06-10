from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import cv2
import numpy as np
import pandas as pd
import yaml

QUALITY_COLUMNS = [
    "video_id",
    "q1_score",
    "q1_fail_fraction",
    "q2_score",
    "q2_fail_fraction",
    "q3_score",
    "q3_fail_fraction",
    "q4_score",
    "q4_fail_fraction",
    "q5_score",
    "q5_fail_fraction",
    "composite_score",
    "quality_tier",
    "assessment_date"
]

FINAL_CATALOG_COLUMNS = [
    "video_id", "drive_file_id", "file_name", "file_size_bytes", "duration_s",
    "fps", "width", "height", "codec", "match_date", "team_a", "team_b", "period_cam",
    "q1_score", "q2_score", "q3_score", "q4_score", "q5_score", "composite_score",
    "quality_tier", "stabilized", "normalized", "stable_path", "phase2_ready", "last_modified_date"
]


def configure_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("quality_assessor")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        file_handler = logging.FileHandler(log_dir / "quality_assessor.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    return logger


def load_strict_config() -> Tuple[Path, dict]:
    """
    Script'in kendi fiziksel konumundan (waterpolo_pipeline/scripts/quality_assessor.py)
    yola çıkarak tam projedeki config.yaml dosyasını hatasız ve manipülasyonsuz yükler.
    """
    script_dir = Path(__file__).resolve().parent
    # scripts dizininin bir üstü 'waterpolo_pipeline' dizinidir.
    pipeline_root = script_dir.parent 
    # Proje ana kök dizini ise onun da bir üstüdür.
    project_root = pipeline_root.parent

    config_path = pipeline_root / "config" / "config.yaml"
    
    if not config_path.exists():
        # Fallback alternatifi: Proje root altında aranır
        config_path = project_root / "waterpolo_pipeline" / "config" / "config.yaml"
        
    if not config_path.exists():
        raise FileNotFoundError(f"Kritik config.yaml dosyası bulunamadı: {config_path}")
        
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
        
    if not cfg or "quality_thresholds" not in cfg:
        raise KeyError(f"Yüklenen config dosyasında ({config_path}) 'quality_thresholds' parametre bloğu bulunamadı!")
        
    return project_root, cfg


def analyze_blur(frame: np.ndarray, thresh_min: float) -> bool:
    if len(frame.shape) == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    return bool(variance < thresh_min)


def analyze_shake(prev_frame: np.ndarray, curr_frame: np.ndarray, thresh_max: float) -> bool:
    if prev_frame is None or curr_frame is None:
        return False
    p_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    c_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(p_gray, c_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    mean_mag = np.mean(mag)
    return bool(mean_mag > thresh_max)


def analyze_pool(frame: np.ndarray, th: dict) -> Tuple[bool, float, np.ndarray]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower = np.array([th["pool_hsv_hue_low"], th["pool_hsv_sat_low"], th["pool_hsv_val_low"]], dtype=np.uint8)
    upper = np.array([th["pool_hsv_hue_high"], 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    
    total_pixels = frame.shape[0] * frame.shape[1]
    pool_pixels = np.count_nonzero(mask)
    ratio = pool_pixels / total_pixels
    
    return bool(ratio < th["pool_coverage_min"]), ratio, mask


def analyze_glare(frame: np.ndarray, pool_mask: np.ndarray, th: dict) -> Tuple[bool, float]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    s_ch = hsv[:, :, 1]
    v_ch = hsv[:, :, 2]
    
    glare_condition = (s_ch <= th["glare_saturation_max"]) & (v_ch >= th["glare_value_min"])
    glare_mask = np.zeros_like(v_ch, dtype=np.uint8)
    glare_mask[glare_condition] = 255
    
    if pool_mask is not None:
        glare_mask = cv2.bitwise_and(glare_mask, pool_mask)
        
    glare_pixels = np.count_nonzero(glare_mask)
    total_roi_pixels = np.count_nonzero(pool_mask) if pool_mask is not None else (frame.shape[0] * frame.shape[1])
    
    if total_roi_pixels == 0:
        return False, 0.0
    density = glare_pixels / total_roi_pixels
    return bool(density > th["glare_density_max"]), density


def analyze_splash(frame: np.ndarray, pool_mask: np.ndarray, th: dict) -> Tuple[bool, float]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h_ch = hsv[:, :, 0]
    s_ch = hsv[:, :, 1]
    v_ch = hsv[:, :, 2]
    
    white_condition = (h_ch <= th["splash_hue_max"]) & (s_ch <= th["splash_sat_max"]) & (v_ch >= th["splash_value_min"])
    splash_mask = np.zeros_like(v_ch, dtype=np.uint8)
    splash_mask[white_condition] = 255
    
    if pool_mask is not None:
        splash_mask = cv2.bitwise_and(splash_mask, pool_mask)
        
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(splash_mask, connectivity=8)
    splash_pixel_count = 0
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= 10:
            splash_pixel_count += stats[i, cv2.CC_STAT_AREA]
            
    total_roi_pixels = np.count_nonzero(pool_mask) if pool_mask is not None else (frame.shape[0] * frame.shape[1])
    if total_roi_pixels == 0:
        return False, 0.0
    density = splash_pixel_count / total_roi_pixels
    return bool(density > th["splash_density_max"]), density


def run_assessment_engine(video_path: Path, config: dict, logger: logging.Logger) -> Dict:
    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        return {}
        
    sample_max = config["frame_sampling"]["max_frames_per_video"]
    indices = np.linspace(0, total_frames - 1, min(sample_max, total_frames), dtype=int)
    
    th = config["quality_thresholds"]
    
    g1_fails, g2_fails, g3_fails, g4_fails, g5_fails = 0, 0, 0, 0, 0
    prev_frame = None
    processed_count = 0
    
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
            
        processed_count += 1
        
        if analyze_blur(frame, th["blur_laplacian_min"]): g1_fails += 1
        if prev_frame is not None and analyze_shake(prev_frame, frame, th["shake_flow_mag_max"]): g2_fails += 1
        
        g3_fail, _, pool_mask = analyze_pool(frame, th)
        if g3_fail: g3_fails += 1
        
        g4_fail, _ = analyze_glare(frame, pool_mask, th)
        if g4_fail: g4_fails += 1
        
        g5_fail, _ = analyze_splash(frame, pool_mask, th)
        if g5_fail: g5_fails += 1
        
        prev_frame = frame.copy()
        
    cap.release()
    
    if processed_count == 0:
        return {}
        
    f1 = g1_fails / processed_count
    f2 = g2_fails / max(1, processed_count - 1)
    f3 = g3_fails / processed_count
    f4 = g4_fails / processed_count
    f5 = g5_fails / processed_count
    
    s1 = max(0.0, 1.0 - (f1 / th["blur_fail_fraction"]))
    s2 = max(0.0, 1.0 - (f2 / th["shake_fail_fraction"]))
    s3 = max(0.0, 1.0 - (f3 / th["pool_fail_fraction"]))
    s4 = max(0.0, 1.0 - (f4 / th["glare_fail_fraction"]))
    s5 = max(0.0, 1.0 - (f5 / th["splash_fail_fraction"]))
    
    comp_score = (0.30 * s1 + 0.25 * s2 + 0.20 * s3 + 0.15 * s4 + 0.10 * s5)
    
    if comp_score < 0.30: quality_tier = "REJECT"
    elif comp_score < 0.50: quality_tier = "Tier C"
    elif comp_score < 0.75: quality_tier = "Tier B"
    else: quality_tier = "Tier A"
    
    return {
        "q1_score": round(s1, 4), "q1_fail_fraction": round(f1, 4),
        "q2_score": round(s2, 4), "q2_fail_fraction": round(f2, 4),
        "q3_score": round(s3, 4), "q3_fail_fraction": round(f3, 4),
        "q4_score": round(s4, 4), "q4_fail_fraction": round(f4, 4),
        "q5_score": round(s5, 4), "q5_fail_fraction": round(f5, 4),
        "composite_score": round(comp_score, 4), "quality_tier": quality_tier
    }


def main():
    # 1. Konfigürasyonu doğrudan script'in kendi hiyerarşisinden yükle
    project_root, config = load_strict_config()
    
    # 2. Logger başlat
    logger = configure_logging(project_root / "waterpolo_pipeline" / config["paths"]["logs_dir"])
    logger.info("Starting quality assessment stage with static relative path strict resolver.")
    
    p = config["paths"]
    inventory_path = project_root / "waterpolo_pipeline" / p["outputs_dir"] / "inventory.csv"
    quality_path = project_root / "waterpolo_pipeline" / p["outputs_dir"] / "quality_scores.csv"
    catalog_path = project_root / "waterpolo_pipeline" / p["manifests_dir"] / "video_catalog.csv"
    
    if not inventory_path.exists():
        logger.error(f"Master inventory.csv ledger missing at: {inventory_path}")
        return
        
    inventory_df = pd.read_csv(inventory_path)
    qa_rows = []
    catalog_rows = []
    
    processed_dir = project_root / "waterpolo_pipeline" / p["processed_dir"]
    
    for _, row in inventory_df.iterrows():
        v_id = row["video_id"]
        raw_path = project_root / "waterpolo_pipeline" / p["raw_data_dir"] / str(row["file_name"])
        
        if not raw_path.exists():
            logger.warning(f"File asset missing from disk: {raw_path.name}")
            continue
            
        metrics = run_assessment_engine(raw_path, config, logger)
        if not metrics:
            continue
            
        metrics["video_id"] = v_id
        metrics["assessment_date"] = datetime.utcnow().isoformat()
        qa_rows.append(metrics)
        
        tier = metrics["quality_tier"]
        stabilized = "TRUE" if tier in ["Tier B", "Tier C"] and (processed_dir / f"{v_id}_stabilized.mp4").exists() else "FALSE"
        normalized = "TRUE" if tier != "REJECT" and (processed_dir / f"{v_id}_normalized.mp4").exists() else "FALSE"
        phase2_ready = "TRUE" if normalized == "TRUE" else "FALSE"
        stable_path_str = str((processed_dir / f"{v_id}_stabilized.mp4").relative_to(project_root)) if stabilized == "TRUE" else "NONE"
        
        catalog_rows.append({
            "video_id": v_id, "drive_file_id": row["drive_file_id"], "file_name": row["file_name"],
            "file_size_bytes": row["file_size_bytes"], "duration_s": row["duration_s"], "fps": row["fps"],
            "width": row["width"], "height": row["height"], "codec": row["codec"], "match_date": row["match_date"],
            "team_a": row["team_a"], "team_b": row["team_b"], "period_cam": row["period_cam"],
            "q1_score": metrics["q1_score"], "q2_score": metrics["q2_score"], "q3_score": metrics["q3_score"],
            "q4_score": metrics["q4_score"], "q5_score": metrics["q5_score"],
            "composite_score": metrics["composite_score"], "quality_tier": tier, "stabilized": stabilized,
            "normalized": normalized, "stable_path": stable_path_str, "phase2_ready": phase2_ready,
            "last_modified_date": datetime.utcnow().isoformat()
        })
        
    quality_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(qa_rows, columns=QUALITY_COLUMNS).to_csv(quality_path, index=False)
    logger.info("quality_scores.csv report generated successfully.")
    
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(catalog_rows, columns=FINAL_CATALOG_COLUMNS).to_csv(catalog_path, index=False)
    logger.info("Nihai 25 sütunlu video_catalog.csv başarıyla güncellendi.")


if __name__ == "__main__":
    main()
