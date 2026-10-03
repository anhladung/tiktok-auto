from __future__ import annotations

import csv
import os
import subprocess
import sys
import time

from pathlib import Path
from datetime import datetime


# ============================================================
# PROJECT ROOT
# ============================================================

PROJECT_ROOT = Path(
    __file__
).resolve().parent


WORKERS_DIR = (
    PROJECT_ROOT
    / "workers"
)


QUEUE_DIR = (
    PROJECT_ROOT
    / "queue"
)


LOG_DIR = (
    PROJECT_ROOT
    / "logs"
    / "pipeline"
)


LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# SETTINGS
# ============================================================

# Nếu một worker crash với exit code != 0:
#
# True:
#   dừng pipeline ngay.
#
# False:
#   tiếp tục worker sau.
#
STOP_ON_ERROR = True


# Nghỉ giữa browser workers để Chrome đóng sạch.
STAGE_DELAY = 3


# Sau những worker nặng/browser có thể nghỉ lâu hơn.
BROWSER_STAGE_DELAY = 7


# ============================================================
# PIPELINE
# ============================================================

PIPELINE = [

    {
        "name": "IDEA GENERATION",
        "file": "idea_worker.py",
        "type": "normal",
    },

    {
        "name": "MOMENT GENERATION",
        "file": "moment_worker.py",
        "type": "normal",
    },

    {
        "name": "PROMPT GENERATION",
        "file": "prompt_worker.py",
        "type": "normal",
    },

    {
        "name": "START FRAME GENERATION",
        "file": "pov_image_worker.py",
        "type": "browser",
    },

    {
        "name": "POV VIDEO GENERATION",
        "file": "pov_video_worker.py",
        "type": "browser",
    },

    {
        "name": "LAST FRAME EXTRACTION",
        "file": "extract_last_frame_worker.py",
        "type": "normal",
    },

    {
        "name": "HERO FRAME REMASTER",
        "file": "pov_remaster_worker.py",
        "type": "browser",
    },

    {
        "name": "FINAL RENDER",
        "file": "final_render_worker.py",
        "type": "normal",
    },
]


# ============================================================
# CONSOLE
# ============================================================

def print_header(
    title,
):

    print()

    print(
        "=" * 72
    )

    print(
        title
    )

    print(
        "=" * 72
    )


# ============================================================
# LOG
# ============================================================

def get_log_file():

    timestamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    return (
        LOG_DIR
        / (
            f"pipeline_"
            f"{timestamp}.log"
        )
    )


# ============================================================
# CHECK WORKERS
# ============================================================

def validate_workers():

    missing = []

    for stage in PIPELINE:

        path = (
            WORKERS_DIR
            / stage["file"]
        )

        if not path.is_file():

            missing.append(
                str(
                    path
                )
            )

    if missing:

        print_header(
            "MISSING WORKERS"
        )

        for file in missing:

            print(
                "-",
                file,
            )

        raise FileNotFoundError(
            "One or more pipeline workers "
            "are missing."
        )


# ============================================================
# QUEUE STATUS
# ============================================================

def read_csv(
    path,
):

    if not path.is_file():

        return []

    try:

        with open(
            path,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            return list(
                csv.DictReader(
                    file
                )
            )

    except Exception:

        return []


def print_moment_queue_summary():

    queue_file = (
        QUEUE_DIR
        / "moment_queue.csv"
    )

    rows = read_csv(
        queue_file
    )

    if not rows:

        return

    counts = {}

    for row in rows:

        status = (
            row.get(
                "status",
                ""
            )
            .strip()
            or "(empty)"
        )

        counts[
            status
        ] = (
            counts.get(
                status,
                0,
            )
            + 1
        )

    print()

    print(
        "Moment queue:"
    )

    for (
        status,
        count,
    ) in sorted(
        counts.items()
    ):

        print(
            f"  {status}: {count}"
        )


# ============================================================
# RUN WORKER
# ============================================================

def run_worker(
    stage,
    log_file,
):

    worker_path = (
        WORKERS_DIR
        / stage["file"]
    )

    stage_name = (
        stage["name"]
    )

    print_header(
        stage_name
    )

    print(
        "Worker:"
    )

    print(
        worker_path
    )

    print()

    print(
        "Python:"
    )

    print(
        sys.executable
    )

    print()

    start_time = (
        time.time()
    )

    # ========================================================
    # CREATE PROCESS
    #
    # Quan trọng:
    # sys.executable = chính Python đang chạy pipeline_runner.
    #
    # Nếu bạn chạy pipeline_runner bằng:
    #
    # .venv\Scripts\python.exe
    #
    # thì tất cả workers cũng dùng đúng .venv đó.
    # ========================================================

    process = subprocess.Popen(

        [
            sys.executable,
            str(
                worker_path
            ),
        ],

        cwd=str(
            PROJECT_ROOT
        ),

        stdout=
            subprocess.PIPE,

        stderr=
            subprocess.STDOUT,

        text=True,

        encoding="utf-8",

        errors="replace",

        bufsize=1,
    )

    # ========================================================
    # LIVE OUTPUT + LOG
    # ========================================================

    with open(
        log_file,
        "a",
        encoding="utf-8",
    ) as log:

        log.write(
            "\n"
            + "=" * 72
            + "\n"
        )

        log.write(
            stage_name
            + "\n"
        )

        log.write(
            "=" * 72
            + "\n"
        )

        if process.stdout:

            for line in process.stdout:

                print(
                    line,
                    end="",
                    flush=True,
                )

                log.write(
                    line
                )

                log.flush()

    return_code = (
        process.wait()
    )

    elapsed = (
        time.time()
        - start_time
    )

    print()

    print(
        f"Stage duration: "
        f"{elapsed:.1f}s"
    )

    print(
        f"Exit code: "
        f"{return_code}"
    )

    return (
        return_code
    )


# ============================================================
# STAGE DELAY
# ============================================================

def wait_after_stage(
    stage,
):

    if (
        stage.get(
            "type"
        )
        == "browser"
    ):

        delay = (
            BROWSER_STAGE_DELAY
        )

    else:

        delay = (
            STAGE_DELAY
        )

    if (
        delay
        <= 0
    ):

        return

    print(
        f"Stage complete. "
        f"Waiting {delay}s before next stage..."
    )

    time.sleep(
        delay
    )


# ============================================================
# FINAL SUMMARY
# ============================================================

def print_final_summary():

    print_header(
        "PIPELINE RESULT"
    )

    final_dir = (
        PROJECT_ROOT
        / "final_videos"
    )

    if not final_dir.exists():

        print(
            "No final_videos folder."
        )

        return

    videos = sorted(
        final_dir.glob(
            "*.mp4"
        )
    )

    if not videos:

        print(
            "No final videos generated."
        )

        return

    print(
        f"Final videos: "
        f"{len(videos)}"
    )

    print()

    for video in videos:

        try:

            size_mb = (
                video.stat().st_size
                / 1024
                / 1024
            )

        except Exception:

            size_mb = 0

        print(
            f"- {video.name} "
            f"({size_mb:.1f} MB)"
        )

        print(
            f"  {video}"
        )


# ============================================================
# RUN PIPELINE
# ============================================================

def main():

    print_header(
        "YOUTUBE POV — FULL AUTO PIPELINE"
    )

    print(
        "Project:"
    )

    print(
        PROJECT_ROOT
    )

    print()

    print(
        "Python environment:"
    )

    print(
        sys.executable
    )

    # ========================================================
    # VALIDATE
    # ========================================================

    validate_workers()

    # ========================================================
    # LOG FILE
    # ========================================================

    log_file = (
        get_log_file()
    )

    print()

    print(
        "Pipeline log:"
    )

    print(
        log_file
    )

    # ========================================================
    # RUN
    # ========================================================

    total_start = (
        time.time()
    )

    completed_stages = []

    failed_stage = None

    for (
        index,
        stage,
    ) in enumerate(
        PIPELINE,
        start=1,
    ):

        print()

        print(
            f"[{index}/{len(PIPELINE)}]"
        )

        return_code = (
            run_worker(
                stage,
                log_file,
            )
        )

        print_moment_queue_summary()

        if (
            return_code
            != 0
        ):

            failed_stage = (
                stage["name"]
            )

            print()

            print(
                "[ERROR] Stage failed:"
            )

            print(
                failed_stage
            )

            if STOP_ON_ERROR:

                print()

                print(
                    "Pipeline stopped."
                )

                break

        else:

            completed_stages.append(
                stage["name"]
            )

        wait_after_stage(
            stage
        )

    # ========================================================
    # COMPLETE
    # ========================================================

    total_elapsed = (
        time.time()
        - total_start
    )

    print_header(
        "PIPELINE FINISHED"
    )

    print(
        "Completed stages:"
    )

    for name in completed_stages:

        print(
            "✓",
            name,
        )

    if failed_stage:

        print()

        print(
            "Failed stage:"
        )

        print(
            "✗",
            failed_stage,
        )

    print()

    print(
        f"Total runtime: "
        f"{total_elapsed:.1f}s"
    )

    print()

    print(
        "Log:"
    )

    print(
        log_file
    )

    print_final_summary()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    main()