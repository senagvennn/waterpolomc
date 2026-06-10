from pathlib import Path
import os

PROJECT_ROOT = Path("waterpolo_pipeline")

CONFIG_YAML = """pipeline:
  name: "Water Polo Digitalisation Pipeline"
  version: "3.1"
  core_model: "sam3"

paths:
  raw_dir: "data/raw"
  processed_dir: "data/processed"
  manifests_dir: "data/manifests"
  sampled_frames_dir: "data/sampled_frames"

quality_gates:
  g1_blur_threshold: 80.0
  g2_shake_threshold: 15.0
  g3_pool_ratio_min: 0.12
  g4_glare_saturation_min: 30.0
  g5_splash_bright_max: 0.35
  g5_cap_area_min: 200

video_processing:
  target_width: 1280
  target_height: 720
  qa_sample_count: 200
  stabilization_smoothing_window: 30
"""


def create_directory_structure() -> None:
    directories = [
        PROJECT_ROOT,
        PROJECT_ROOT / "config",
        PROJECT_ROOT / "data",
        PROJECT_ROOT / "data" / "raw",
        PROJECT_ROOT / "data" / "processed",
        PROJECT_ROOT / "data" / "sampled_frames",
        PROJECT_ROOT / "data" / "manifests",
        PROJECT_ROOT / "data" / "outputs",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "pipeline",
        PROJECT_ROOT / "analytics",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def create_config_files() -> None:
    config_dir = PROJECT_ROOT / "config"

    (config_dir / "config.yaml").write_text(
        CONFIG_YAML,
        encoding="utf-8",
    )

    (config_dir / "credentials.json").write_text(
        "",
        encoding="utf-8",
    )

    (config_dir / "token.json").write_text(
        "",
        encoding="utf-8",
    )


def create_python_files() -> None:
    files = [
        PROJECT_ROOT / "scripts" / "gdrive_catalog.py",
        PROJECT_ROOT / "scripts" / "quality_assessor.py",
        PROJECT_ROOT / "pipeline" / "sam31_tracker.py",
        PROJECT_ROOT / "pipeline" / "pixel_features.py",
        PROJECT_ROOT / "pipeline" / "homography.py",
        PROJECT_ROOT / "pipeline" / "zoom_detector.py",
        PROJECT_ROOT / "analytics" / "kinematics.py",
        PROJECT_ROOT / "analytics" / "heatmaps.py",
    ]

    for file_path in files:
        file_path.touch(exist_ok=True)


def main() -> None:
    create_directory_structure()
    create_config_files()
    create_python_files()


if __name__ == "__main__":
    main()
