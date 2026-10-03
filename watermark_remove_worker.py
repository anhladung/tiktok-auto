"""Remove video watermarks through Erasio using persistent Flow Chrome profiles.

Run build_watermark_remove_queue.py first, then run this script. Clean files are
saved under videos_clean/ so the original videos remain available.
"""

import csv
import os
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_DIR = Path(__file__).resolve().parent
QUEUE_FILE = BASE_DIR / "queue" / "watermark_remove_queue.csv"
PROFILE_STATE_FILE = BASE_DIR / "erasio_profile_state.txt"
ERASIO_URL = "https://erasio.io/tool"
PROFILES = [Path(fr"C:\flow_auto_profile_{number:02d}") for number in range(1, 11)]
CREDITS_PER_VIDEO = 3
REFRESH_AFTER = 3
PROCESS_TIMEOUT_MS = 10 * 60 * 1000
DOWNLOAD_TIMEOUT_MS = 3 * 60 * 1000
MAX_ATTEMPTS = 3
FIELDNAMES = [
    "job_id", "category", "product_id", "video_path", "output_path",
    "status", "attempts", "error", "updated_at",
]


def load_queue():
    if not QUEUE_FILE.is_file():
        raise FileNotFoundError(f"Build the queue first: {QUEUE_FILE}")
    with QUEUE_FILE.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def save_queue(rows):
    temporary_file = QUEUE_FILE.with_suffix(".csv.tmp")
    with temporary_file.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary_file, QUEUE_FILE)


def update_job(rows, row, status, error=""):
    row["status"] = status
    row["error"] = error
    row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_queue(rows)


def get_profile_index():
    try:
        return int(PROFILE_STATE_FILE.read_text(encoding="utf-8").strip()) % len(PROFILES)
    except (FileNotFoundError, ValueError):
        return 0


def save_profile_index(index):
    temporary_file = PROFILE_STATE_FILE.with_suffix(".tmp")
    temporary_file.write_text(str(index % len(PROFILES)), encoding="utf-8")
    os.replace(temporary_file, PROFILE_STATE_FILE)


def resolve_queue_path(value):
    path = Path(str(value or "").replace("/", os.sep))
    return path if path.is_absolute() else BASE_DIR / path


def get_remaining_credits(page):
    quota = page.locator("p:has-text('Free quota:')").first
    quota.wait_for(state="visible", timeout=30000)
    text = quota.inner_text()
    match = re.search(r"Remaining\s*(\d+)", text, re.IGNORECASE)
    if not match:
        raise RuntimeError(f"Cannot read Erasio credits: {text!r}")
    return int(match.group(1))


def get_clean_card(page, filename):
    # The filename and Save button live in the same rounded video card.
    name = page.locator("p.text-sm.font-semibold").filter(has_text=filename).first
    card = name.locator(
        "xpath=ancestor::div[contains(@class,'rounded-2xl') and "
        "contains(@class,'overflow-hidden')][1]"
    )
    card.locator("div:has-text('Clean')").first.wait_for(
        state="visible", timeout=PROCESS_TIMEOUT_MS
    )
    card.locator('button[title="Download clean MP4"]').wait_for(
        state="visible", timeout=PROCESS_TIMEOUT_MS
    )
    return card


def process_video(context, page, source, output):
    # Refresh before each upload is deliberately avoided: Erasio retains the
    # last three cards, then the caller refreshes as requested.
    old_cards = page.locator('button[title="Download clean MP4"]').count()
    page.locator('input[type="file"][accept*="video/mp4"]').set_input_files(str(source))

    # Wait for a new card, then identify it by its filename.
    page.wait_for_function(
        "oldCount => document.querySelectorAll('button[title=\"Download clean MP4\"]').length > oldCount",
        arg=old_cards,
        timeout=PROCESS_TIMEOUT_MS,
    )
    card = get_clean_card(page, source.name)

    downloads = []
    popup_pages = []

    def watch_page(new_page):
        if new_page != page:
            popup_pages.append(new_page)
        new_page.on("download", lambda download: downloads.append(download))

    def on_download(download):
        downloads.append(download)

    page.on("download", on_download)
    context.on("page", watch_page)
    temporary_output = output.with_name(output.stem + ".downloading" + output.suffix)
    try:
        card.locator('button[title="Download clean MP4"]').click()
        deadline = time.monotonic() + DOWNLOAD_TIMEOUT_MS / 1000
        while not downloads and time.monotonic() < deadline:
            page.wait_for_timeout(500)
        if not downloads:
            raise TimeoutError("Erasio Save did not start a download")
        if not downloads[0].suggested_filename.lower().endswith(".mp4"):
            raise RuntimeError(
                f"Unexpected download: {downloads[0].suggested_filename}"
            )

        output.parent.mkdir(parents=True, exist_ok=True)
        downloads[0].save_as(str(temporary_output))
        if not temporary_output.is_file() or temporary_output.stat().st_size == 0:
            raise RuntimeError("Downloaded video is empty")
        with temporary_output.open("rb") as file:
            if file.read(12)[4:8] != b"ftyp":
                raise RuntimeError("Downloaded file is not an MP4 video")
        os.replace(temporary_output, output)
    finally:
        page.remove_listener("download", on_download)
        context.remove_listener("page", watch_page)
        if temporary_output.exists():
            temporary_output.unlink()
        for popup in popup_pages:
            if not popup.is_closed():
                popup.close()


def next_job(rows, attempted_ids=None):
    attempted_ids = attempted_ids or set()
    for wanted_status in ("pending", "error", "processing"):
        for row in rows:
            if row.get("job_id") in attempted_ids:
                continue
            status = (row.get("status") or "pending").lower()
            attempts = int(row.get("attempts") or 0)
            if status == wanted_status and attempts < MAX_ATTEMPTS:
                return row
    return None


def run():
    rows = load_queue()
    if not next_job(rows):
        print("No pending watermark removal jobs.")
        return

    start = get_profile_index()
    attempted_ids = set()
    with sync_playwright() as playwright:
        for offset in range(len(PROFILES)):
            index = (start + offset) % len(PROFILES)
            profile = PROFILES[index]
            if not next_job(rows, attempted_ids):
                break
            save_profile_index(index)
            if not profile.is_dir():
                print(f"Skip missing profile: {profile}")
                save_profile_index(index + 1)
                continue

            print(f"Opening profile: {profile}")
            try:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile), channel="chrome", headless=False,
                    accept_downloads=True, args=["--window-size=1500,1000"],
                )
            except Exception as exc:
                print(f"Cannot open {profile}: {exc}")
                save_profile_index(index + 1)
                continue

            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(ERASIO_URL, wait_until="domcontentloaded", timeout=60000)
                credits = get_remaining_credits(page)
                print(f"Remaining credits: {credits} | Capacity: {credits // CREDITS_PER_VIDEO} videos")
                completed_since_refresh = 0

                while credits >= CREDITS_PER_VIDEO:
                    row = next_job(rows, attempted_ids)
                    if row is None:
                        return
                    if completed_since_refresh >= REFRESH_AFTER:
                        page.reload(wait_until="domcontentloaded", timeout=60000)
                        completed_since_refresh = 0

                    source = resolve_queue_path(row.get("video_path"))
                    output_value = row.get("output_path") or (
                        Path("videos_clean") / source.relative_to(BASE_DIR / "videos")
                    ).as_posix()
                    output = resolve_queue_path(output_value)
                    row["output_path"] = output_value
                    attempted_ids.add(row["job_id"])
                    row["attempts"] = str(int(row.get("attempts") or 0) + 1)
                    update_job(rows, row, "processing")
                    try:
                        if not source.is_file() or source.stat().st_size == 0:
                            raise FileNotFoundError(f"Source video missing or empty: {source}")
                        process_video(context, page, source, output)
                    except Exception as exc:
                        update_job(rows, row, "error", str(exc)[:500])
                        print(f"Failed {row['job_id']}: {exc}")
                        # A failed upload may still have spent credits. Read the
                        # live balance before using this profile again.
                        try:
                            page.reload(wait_until="domcontentloaded", timeout=60000)
                            credits = get_remaining_credits(page)
                            completed_since_refresh = 0
                        except Exception:
                            break
                    else:
                        update_job(rows, row, "done")
                        credits -= CREDITS_PER_VIDEO
                        completed_since_refresh += 1
                        print(f"Done {row['job_id']}: {output}")
            except Exception as exc:
                print(f"Profile {profile} unavailable: {exc}")
            finally:
                context.close()
                save_profile_index(index + 1)


if __name__ == "__main__":
    run()
