"""Build a queue of source videos that need watermark removal."""

import csv
import os
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
VIDEOS_DIR = BASE_DIR / "videos"
QUEUE_FILE = BASE_DIR / "queue" / "watermark_remove_queue.csv"
VIDEO_EXTENSIONS = {".mp4"}  # Erasio upload control accepts MP4 videos.
FIELDNAMES = [
    "job_id",
    "category",
    "product_id",
    "video_path",
    "output_path",
    "status",
    "attempts",
    "error",
    "updated_at",
]


def load_existing_rows():
    if not QUEUE_FILE.is_file():
        return {}

    with QUEUE_FILE.open("r", encoding="utf-8-sig", newline="") as file:
        rows = csv.DictReader(file)
        return {
            (row.get("video_path") or "").replace("\\", "/"): row
            for row in rows
            if row.get("video_path")
        }


def scan_videos():
    if not VIDEOS_DIR.is_dir():
        raise FileNotFoundError(f"Video directory does not exist: {VIDEOS_DIR}")

    for path in sorted(VIDEOS_DIR.rglob("*"), key=lambda item: str(item).casefold()):
        if path.suffix.lower() not in VIDEO_EXTENSIONS or not path.is_file():
            continue
        if path.stat().st_size == 0:
            continue
        yield path


def build_watermark_remove_queue():
    existing = load_existing_rows()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    added = 0
    seen_paths = set()

    for path in scan_videos():
        relative_path = path.relative_to(BASE_DIR).as_posix()
        seen_paths.add(relative_path)
        relative_video_path = path.relative_to(VIDEOS_DIR)
        category = relative_video_path.parts[0] if len(relative_video_path.parts) > 1 else ""
        old = existing.get(relative_path, {})
        if not old:
            added += 1

        rows.append({
            "job_id": old.get("job_id") or f"wr_{relative_video_path.with_suffix('').as_posix().replace('/', '_')}",
            "category": category,
            "product_id": path.stem,
            "video_path": relative_path,
            "output_path": old.get("output_path") or (Path("videos_clean") / relative_video_path).as_posix(),
            "status": old.get("status") or "pending",
            "attempts": old.get("attempts") or "0",
            "error": old.get("error") or "",
            "updated_at": old.get("updated_at") or timestamp,
        })

    # A video can be temporarily moved while another pipeline step runs.
    # Keep its existing job and status; the worker will report a missing source
    # when it actually tries to process that job.
    for relative_path, old in existing.items():
        if relative_path not in seen_paths:
            rows.append({field: old.get(field, "") for field in FIELDNAMES})

    rows.sort(key=lambda row: row["video_path"].casefold())

    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = QUEUE_FILE.with_suffix(".csv.tmp")
    with temporary_file.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary_file, QUEUE_FILE)

    print(f"Queue: {QUEUE_FILE}")
    print(f"Jobs: {len(rows)} | New jobs: {added} | Existing jobs: {len(rows) - added}")
    return rows


if __name__ == "__main__":
    build_watermark_remove_queue()
