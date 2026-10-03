from __future__ import annotations

import csv
import os
import subprocess

from pathlib import Path


# ============================================================
# PROJECT ROOT
# ============================================================

def find_project_root() -> Path:

    current = Path(__file__).resolve()

    for parent in current.parents:

        if (
            (parent / "queue").exists()
            and
            (parent / "prompts").exists()
        ):
            return parent

    raise RuntimeError(
        "Could not find PROJECT_ROOT."
    )


PROJECT_ROOT = find_project_root()


# ============================================================
# PATHS
# ============================================================

MOMENT_QUEUE_FILE = (
    PROJECT_ROOT
    / "queue"
    / "moment_queue.csv"
)


GENERATED_ASSETS_ROOT = (
    PROJECT_ROOT
    / "generated_assets"
)


DEBUG_DIR = (
    PROJECT_ROOT
    / "debug"
    / "extract_last_frame_worker"
)


DEBUG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# SETTINGS
# ============================================================

MAX_ATTEMPTS = 3


# ============================================================
# FFMPEG
# ============================================================

FFMPEG_DIR = (
    r"C:\Users\Thinkbook 14G2\Downloads"
    r"\ffmpeg-2026-06-29-git-de6bcf5c05-full_build"
    r"\ffmpeg-2026-06-29-git-de6bcf5c05-full_build"
    r"\bin"
)


FFMPEG = os.path.join(
    FFMPEG_DIR,
    "ffmpeg.exe"
)


if not os.path.isfile(
    FFMPEG
):

    raise FileNotFoundError(
        f"FFmpeg not found:\n{FFMPEG}"
    )


print(
    "FFmpeg:",
    FFMPEG,
)


# ============================================================
# QUEUE
# ============================================================

def load_queue():

    if not MOMENT_QUEUE_FILE.exists():

        raise FileNotFoundError(
            "Moment queue not found:\n"
            f"{MOMENT_QUEUE_FILE}"
        )

    with open(
        MOMENT_QUEUE_FILE,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        return list(
            csv.DictReader(file)
        )


def get_fieldnames(
    rows,
):

    fieldnames = []

    for row in rows:

        for key in row.keys():

            if (
                key
                and key not in fieldnames
            ):

                fieldnames.append(
                    key
                )

    additional = [
        "extract_attempts",
        "last_frame_file",
        "error",
    ]

    for field in additional:

        if field not in fieldnames:

            fieldnames.append(
                field
            )

    return fieldnames


def save_queue(
    rows,
):

    if not rows:
        return

    fieldnames = (
        get_fieldnames(
            rows
        )
    )

    temporary_file = Path(
        str(MOMENT_QUEUE_FILE)
        + ".temporary"
    )

    with open(
        temporary_file,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()

        writer.writerows(
            rows
        )

    os.replace(
        temporary_file,
        MOMENT_QUEUE_FILE,
    )


def update_job(
    moment_id,
    **updates,
):

    rows = load_queue()

    found = False

    for row in rows:

        if (
            row.get(
                "moment_id",
                ""
            ).strip()
            != moment_id
        ):

            continue

        for key, value in updates.items():

            row[key] = str(
                value
            )

        found = True

        break

    if not found:

        raise KeyError(
            f"Moment not found: {moment_id}"
        )

    save_queue(
        rows
    )


# ============================================================
# RESET INTERRUPTED
# ============================================================

def reset_interrupted(
    rows,
):

    changed = False

    for row in rows:

        status = (
            row.get(
                "status",
                ""
            )
            .strip()
            .lower()
        )

        if (
            status
            == "processing_last_frame"
        ):

            row["status"] = (
                "clip_generated"
            )

            row["error"] = ""

            changed = True

    if changed:

        save_queue(
            rows
        )


# ============================================================
# PATH HELPERS
# ============================================================

def resolve_project_path(
    raw_path,
):

    raw_path = (
        str(
            raw_path or ""
        )
        .strip()
    )

    if not raw_path:
        return ""

    raw_path = (
        os.path.expandvars(
            os.path.expanduser(
                raw_path
            )
        )
    )

    raw_path = raw_path.replace(
        "/",
        os.sep,
    )

    if os.path.isabs(
        raw_path
    ):

        return os.path.normpath(
            raw_path
        )

    return os.path.normpath(
        os.path.join(
            PROJECT_ROOT,
            raw_path,
        )
    )


# ============================================================
# OUTPUT PATH
# ============================================================

def get_last_frame_output_path(
    row,
):

    topic_id = (
        row.get(
            "topic_id",
            ""
        )
        .strip()
    )

    moment_id = (
        row.get(
            "moment_id",
            ""
        )
        .strip()
    )

    if not topic_id:

        raise ValueError(
            "Missing topic_id."
        )

    if not moment_id:

        raise ValueError(
            "Missing moment_id."
        )

    output_dir = (
        GENERATED_ASSETS_ROOT
        / topic_id
        / moment_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    return (
        output_dir
        / "last_frame_raw.png"
    )


# ============================================================
# RUN ONE FFMPEG ATTEMPT
# ============================================================

def run_ffmpeg_extract(
    video_file,
    output_file,
    seconds_from_end,
):

    # Xóa output cũ trước mỗi lần thử.
    if os.path.exists(
        output_file
    ):

        try:

            os.remove(
                output_file
            )

        except OSError:

            pass

    command = [
        FFMPEG,

        "-y",

        # Seek từ cuối video.
        "-sseof",
        f"-{seconds_from_end}",

        "-i",
        video_file,

        # Chỉ lấy video stream.
        "-map",
        "0:v:0",

        # Một frame duy nhất.
        "-frames:v",
        "1",

        # Ép output PNG.
        "-f",
        "image2",

        output_file,
    ]

    print()

    print(
        "Running FFmpeg:"
    )

    print(
        " ".join(
            command
        )
    )

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    print(
        "FFmpeg return code:",
        result.returncode,
    )

    # FFmpeg thường ghi log vào stderr,
    # kể cả khi chạy thành công.
    if result.stderr:

        print(
            "FFmpeg output:"
        )

        print(
            result.stderr[-3000:]
        )

    if (
        result.returncode
        != 0
    ):

        return False

    if not os.path.isfile(
        output_file
    ):

        return False

    if (
        os.path.getsize(
            output_file
        )
        <= 0
    ):

        return False

    return True


# ============================================================
# EXTRACT LAST FRAME
# ============================================================

def extract_last_frame(
    video_file,
    output_file,
):
    """
    Lấy frame gần cuối clip Flow.

    Một số MP4 không decode được frame ở -0.05 giây,
    nên worker tự fallback:

        -0.20
        -0.35
        -0.50

    Frame vẫn nằm rất gần cuối clip 4 giây,
    đủ phù hợp để làm Hero Frame.
    """

    video_file = os.path.abspath(
        video_file
    )

    output_file = os.path.abspath(
        output_file
    )

    if not os.path.isfile(
        video_file
    ):

        raise FileNotFoundError(
            f"Video file not found:\n{video_file}"
        )

    video_size = os.path.getsize(
        video_file
    )

    if (
        video_size
        <= 0
    ):

        raise RuntimeError(
            "Video file is empty."
        )

    print(
        "Video size:",
        video_size,
        "bytes",
    )

    os.makedirs(
        os.path.dirname(
            output_file
        ),
        exist_ok=True,
    )

    # ========================================================
    # FALLBACK POSITIONS
    # ========================================================

    seek_positions = [
        0.20,
        0.35,
        0.50,
    ]

    for seconds_from_end in seek_positions:

        print()

        print(
            "=" * 60
        )

        print(
            "Trying frame at:",
            f"-{seconds_from_end}s from end"
        )

        success = (
            run_ffmpeg_extract(
                video_file=
                    video_file,

                output_file=
                    output_file,

                seconds_from_end=
                    seconds_from_end,
            )
        )

        if success:

            frame_size = (
                os.path.getsize(
                    output_file
                )
            )

            print()

            print(
                "Extracted last frame:"
            )

            print(
                output_file
            )

            print(
                "Frame size:",
                frame_size,
                "bytes",
            )

            print(
                "Used position:",
                f"-{seconds_from_end}s"
            )

            return

        print(
            "No valid frame produced at",
            f"-{seconds_from_end}s",
        )

    # ========================================================
    # ALL FAILED
    # ========================================================

    raise RuntimeError(
        "FFmpeg could not extract a frame "
        "from any fallback position."
    )


# ============================================================
# PENDING JOBS
# ============================================================

def get_pending_jobs(
    rows,
):
    """
    Chỉ nhận:

        status = clip_generated

    VÀ

        video_file không rỗng

    Như vậy moment chưa download được clip
    sẽ không bị extract worker retry vô ích.
    """

    pending = []

    for row in rows:

        status = (
            row.get(
                "status",
                ""
            )
            .strip()
            .lower()
        )

        video_file = (
            row.get(
                "video_file",
                ""
            )
            .strip()
        )

        if (
            status
            != "clip_generated"
        ):

            continue

        if not video_file:

            print(
                "[SKIP] clip_generated but "
                "video_file is empty:",
                row.get(
                    "moment_id",
                    "",
                ),
            )

            continue

        pending.append(
            row
        )

    pending.sort(
        key=lambda row: (
            row.get(
                "topic_id",
                "",
            ),
            int(
                row.get(
                    "moment_order",
                    ""
                )
                or 0
            ),
        )
    )

    return pending


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=" * 60
    )

    print(
        "POV — EXTRACT LAST FRAME WORKER"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # RESET INTERRUPTED JOBS
    # --------------------------------------------------------

    rows = (
        load_queue()
    )

    reset_interrupted(
        rows
    )

    # ========================================================
    # LOOP
    # ========================================================

    while True:

        rows = (
            load_queue()
        )

        pending_jobs = (
            get_pending_jobs(
                rows
            )
        )

        if not pending_jobs:

            print()

            print(
                "=" * 60
            )

            print(
                "No pending last-frame jobs left."
            )

            break

        job = (
            pending_jobs[0]
        )

        # ====================================================
        # JOB DATA
        # ====================================================

        moment_id = (
            job.get(
                "moment_id",
                ""
            )
            .strip()
        )

        topic_id = (
            job.get(
                "topic_id",
                ""
            )
            .strip()
        )

        person = (
            job.get(
                "person",
                ""
            )
            .strip()
        )

        moment_order = (
            job.get(
                "moment_order",
                ""
            )
            .strip()
        )

        video_file = (
            resolve_project_path(
                job.get(
                    "video_file",
                    ""
                )
            )
        )

        output_file = str(
            get_last_frame_output_path(
                job
            )
        )

        print()

        print(
            "=" * 60
        )

        print(
            "Extracting last frame:"
        )

        print(
            "Moment:",
            moment_id,
        )

        print(
            "Topic:",
            topic_id,
        )

        print(
            "Person:",
            person,
        )

        print(
            "Moment order:",
            moment_order,
        )

        print(
            "Video:",
            video_file,
        )

        print(
            "Output:",
            output_file,
        )

        # ====================================================
        # ATTEMPTS
        # ====================================================

        try:

            attempts = int(
                job.get(
                    "extract_attempts",
                    ""
                )
                or 0
            )

        except ValueError:

            attempts = 0

        # ====================================================
        # PROCESSING
        # ====================================================

        update_job(
            moment_id,

            status=
                "processing_last_frame",

            error="",
        )

        try:

            # =================================================
            # VALIDATE
            # =================================================

            if not moment_id:

                raise ValueError(
                    "Missing moment_id."
                )

            if not video_file:

                raise ValueError(
                    "Missing video_file."
                )

            if not os.path.isfile(
                video_file
            ):

                raise FileNotFoundError(
                    "Video file does not exist:\n"
                    f"{video_file}"
                )

            # =================================================
            # EXISTING FRAME
            # =================================================

            if (
                os.path.isfile(
                    output_file
                )
                and
                os.path.getsize(
                    output_file
                )
                > 0
            ):

                print(
                    "Existing last frame found."
                )

                print(
                    "Skipping FFmpeg extraction."
                )

            else:

                # =================================================
                # EXTRACT
                # =================================================

                extract_last_frame(
                    video_file=
                        video_file,

                    output_file=
                        output_file,
                )

            # =================================================
            # FINAL VALIDATION
            # =================================================

            if not os.path.isfile(
                output_file
            ):

                raise RuntimeError(
                    "Last frame output does not exist."
                )

            if (
                os.path.getsize(
                    output_file
                )
                <= 0
            ):

                raise RuntimeError(
                    "Last frame output is empty."
                )

            # =================================================
            # SUCCESS
            # =================================================

            update_job(
                moment_id,

                status=
                    "last_frame_extracted",

                extract_attempts=
                    str(
                        attempts + 1
                    ),

                last_frame_file=
                    output_file,

                error="",
            )

            print()

            print(
                "[OK] Last-frame job done:",
                moment_id,
            )

        # =====================================================
        # FAILURE
        # =====================================================

        except Exception as error:

            error_text = str(
                error
            )

            print()

            print(
                "[ERROR] Last-frame job failed:",
                moment_id,
            )

            print(
                "Error:",
                error_text,
            )

            attempts += 1

            if (
                attempts
                >= MAX_ATTEMPTS
            ):

                next_status = (
                    "last_frame_failed"
                )

            else:

                next_status = (
                    "clip_generated"
                )

            update_job(
                moment_id,

                status=
                    next_status,

                extract_attempts=
                    str(
                        attempts
                    ),

                error=
                    error_text,
            )

    # ========================================================
    # FINISH
    # ========================================================

    print()

    print(
        "=" * 60
    )

    print(
        "Last-frame extraction batch finished."
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    main()