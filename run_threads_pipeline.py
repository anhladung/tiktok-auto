import os
import subprocess
import sys
import time


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


# ============================================================
# SETTINGS
# ============================================================

# Dùng chính Python/venv đang chạy file này
PYTHON_EXECUTABLE = sys.executable

# Nghỉ giữa các worker
BETWEEN_STAGES_DELAY = 3


# ============================================================
# PIPELINE
# ============================================================

PIPELINE = [
    {
        "name": "BUILD READING QUEUE",
        "script": "build_threads_reading_queue.py",
    },
    {
        "name": "GENERATE READINGS",
        "script": "threads_reading_worker.py",
    },
    {
        "name": "UPLOAD / SCHEDULE THREADS",
        "script": "threads_upload_worker.py",
    },
]


# ============================================================
# RUN SCRIPT
# ============================================================

def run_script(
    name,
    script_name,
):
    script_path = os.path.join(
        BASE_DIR,
        script_name,
    )

    # --------------------------------------------------------
    # CHECK FILE
    # --------------------------------------------------------

    if not os.path.isfile(
        script_path
    ):
        raise FileNotFoundError(
            f"Script not found: "
            f"{script_path}"
        )

    print()
    print(
        "=" * 70
    )

    print(
        f"[START] {name}"
    )

    print(
        f"[SCRIPT] {script_name}"
    )

    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # RUN
    # --------------------------------------------------------

    process = subprocess.Popen(
        [
            PYTHON_EXECUTABLE,
            script_path,
        ],

        cwd=BASE_DIR,

        stdout=None,

        stderr=None,
    )

    return_code = (
        process.wait()
    )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    if return_code != 0:

        print()
        print(
            "=" * 70
        )

        print(
            f"[FAILED] {name}"
        )

        print(
            f"[EXIT CODE] "
            f"{return_code}"
        )

        print(
            "=" * 70
        )

        raise RuntimeError(
            f"{script_name} failed "
            f"with exit code "
            f"{return_code}"
        )

    print()
    print(
        f"[OK] {name} finished."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "=" * 70
    )

    print(
        "THREADS READING PIPELINE"
    )

    print(
        "=" * 70
    )

    print(
        f"[ROOT] "
        f"{BASE_DIR}"
    )

    print(
        f"[PYTHON] "
        f"{PYTHON_EXECUTABLE}"
    )

    # ========================================================
    # RUN PIPELINE
    # ========================================================

    for index, stage in enumerate(
        PIPELINE,
        start=1,
    ):

        print()
        print(
            f"[STAGE "
            f"{index}/"
            f"{len(PIPELINE)}]"
        )

        try:

            run_script(
                stage["name"],
                stage["script"],
            )

        except Exception as exc:

            print()
            print(
                "=" * 70
            )

            print(
                "[PIPELINE STOPPED]"
            )

            print(
                f"[ERROR] "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            print(
                "=" * 70
            )

            return

        # ----------------------------------------------------
        # WAIT BEFORE NEXT STAGE
        # ----------------------------------------------------

        if index < len(
            PIPELINE
        ):

            print(
                f"[WAIT] Next stage in "
                f"{BETWEEN_STAGES_DELAY}s..."
            )

            time.sleep(
                BETWEEN_STAGES_DELAY
            )

    # ========================================================
    # DONE
    # ========================================================

    print()
    print(
        "=" * 70
    )

    print(
        "[DONE] THREADS PIPELINE FINISHED"
    )

    print(
        "=" * 70
    )


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":
    main()