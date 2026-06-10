#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

def run_stage(script_name: str):
    print(f"[STAGE] Executing: {script_name}...")
    cmd = [sys.executable, f"waterpolo_pipeline/scripts/{script_name}"]
    res = subprocess.run(cmd, capture_output=False)
    if res.returncode != 0:
        print(f"[ERROR] Stage {script_name} returned non-zero exit code: {res.returncode}")
        sys.exit(res.returncode)

def main():
    print("=== STARTING WATER POLO PIPELINE - PHASE 1 FULL RUN ===")
    run_stage("gdrive_catalog.py")
    run_stage("quality_assessor.py")
    run_stage("stabilizer.py")
    run_stage("scene_filter.py")
    run_stage("normalizer.py")
    run_stage("catalog_writer.py")
    print("=== PHASE 1 COMPLETED SUCCESSFULLY - ALL LEDGERS COMMITTED ===")

if __name__ == "__main__":
    main()
