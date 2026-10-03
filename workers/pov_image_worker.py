from __future__ import annotations

from playwright.sync_api import sync_playwright
from PIL import Image, ImageOps

import csv
import os
import random
import re
import time

from pathlib import Path


# ============================================================
# PROJECT ROOT
# ============================================================

def find_project_root() -> Path:
    """
    Tự tìm project root.

    Worker có thể nằm ở:
        workers/pov_image_worker.py

    hoặc:
        workers/pov/pov_image_worker.py
    """

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

CHATGPT_URL = (
    "https://chatgpt.com/"
    "g/g-p-6a59ccfe43208191a8a880795664b046/project"
)


CHATGPT_PROFILE_DIR = (
    r"C:\chatgpt_auto_profile"
)


MOMENT_QUEUE_FILE = (
    PROJECT_ROOT
    / "queue"
    / "moment_queue.csv"
)


OUTPUT_ROOT = (
    PROJECT_ROOT
    / "generated_assets"
)


DEBUG_DIR = (
    PROJECT_ROOT
    / "debug"
    / "pov_image_worker"
)


DEBUG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


OUTPUT_ROOT.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# SETTINGS
# ============================================================

MAX_ATTEMPTS = 3


# ------------------------------------------------------------
# IMAGE GENERATION
# ------------------------------------------------------------

# 450 giây = 7 phút 30 giây
MAX_RENDER_TIME = 450


# ------------------------------------------------------------
# CHATGPT PAGE
# ------------------------------------------------------------

PAGE_LOAD_WAIT = 8

PROMPT_READY_WAIT = 2

AFTER_SEND_WAIT = 2

IMAGE_READY_BEFORE_SAVE_WAIT = 12

AFTER_FULLSCREEN_OPEN_WAIT = 3

AFTER_FULLSCREEN_CLOSE_WAIT = 3


# ------------------------------------------------------------
# RESTART
# ------------------------------------------------------------

# Giữ đúng logic worker cũ:
# sau MỖI ảnh thành công đóng Chrome và mở lại ở job sau.
RESTART_AFTER_EACH_IMAGE = True

BROWSER_RESTART_DELAY = 0


# ============================================================
# RATE LIMIT
# ============================================================

RATE_LIMIT_COOLDOWNS = [
    300,
    600,
    1200,
    1800,
]

RATE_LIMIT_JITTER_MIN_SECONDS = 15
RATE_LIMIT_JITTER_MAX_SECONDS = 60


# ============================================================
# PLUS IMAGE GENERATION LIMIT
# ============================================================

IMAGE_LIMIT_RESET_BUFFER_SECONDS = 120

IMAGE_LIMIT_FALLBACK_WAIT_SECONDS = 3600


# ============================================================
# CUSTOM ERRORS
# ============================================================

class TooManyRequestsError(RuntimeError):
    """
    ChatGPT đang rate limit.

    Không tăng attempts.
    Job được đưa lại về prompts_generated.
    """


class ImageGenerationLimitError(RuntimeError):
    """
    ChatGPT Plus hết hạn mức tạo ảnh.
    """

    def __init__(
        self,
        message,
        wait_seconds,
        reset_description="",
    ):
        super().__init__(message)

        self.wait_seconds = int(
            wait_seconds
        )

        self.reset_description = str(
            reset_description or ""
        )


# ============================================================
# GENERAL HELPERS
# ============================================================

def sanitize_filename(value):
    return re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        str(value),
    )


def read_text(path):
    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        return (
            file.read()
            .strip()
        )


def resolve_saved_path(raw_path):
    """
    image_prompt_file có thể là absolute hoặc relative.

    Relative path được tính từ PROJECT_ROOT.
    """

    raw_path = (
        str(
            raw_path or ""
        )
        .strip()
    )

    if not raw_path:
        return None

    expanded = os.path.expandvars(
        os.path.expanduser(
            raw_path
        )
    )

    path = Path(
        expanded
    )

    if path.is_absolute():
        return path

    return (
        PROJECT_ROOT
        / path
    ).resolve()


# ============================================================
# MOMENT QUEUE
# ============================================================

def load_queue():

    if not MOMENT_QUEUE_FILE.exists():

        raise FileNotFoundError(
            "Không tìm thấy moment queue:\n"
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


def get_fieldnames(rows):

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

    additional_fields = [
        "image_attempts",
        "start_frame_file",
        "error",
    ]

    for field in additional_fields:

        if field not in fieldnames:

            fieldnames.append(
                field
            )

    return fieldnames


def save_queue(rows):
    """
    Ghi qua temporary file trước.
    """

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
            "Không tìm thấy moment_id: "
            f"{moment_id}"
        )

    save_queue(
        rows
    )


# ============================================================
# RESET INTERRUPTED
# ============================================================

def reset_interrupted(rows):

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
            == "processing_start_frame"
        ):

            row["status"] = (
                "prompts_generated"
            )

            row["error"] = ""

            changed = True

    if changed:

        save_queue(
            rows
        )


# ============================================================
# OUTPUT PATH
# ============================================================

def build_output_path(row):

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
        OUTPUT_ROOT
        / topic_id
        / moment_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    return (
        output_dir
        / "start.png"
    )


# ============================================================
# GET NEXT JOB
# ============================================================

def parse_moment_order(row):

    try:

        return int(
            row.get(
                "moment_order",
                ""
            )
            or 0
        )

    except ValueError:

        return 0


def get_next_pending_job(rows):
    """
    Chỉ xử lý moment đã có prompt:

        status = prompts_generated
    """

    pending = [
        row
        for row in rows
        if (
            row.get(
                "status",
                ""
            )
            .strip()
            .lower()
            == "prompts_generated"
        )
    ]

    print(
        "Pending POV start frames:",
        len(pending),
    )

    pending.sort(
        key=lambda row: (
            row.get(
                "topic_id",
                "",
            ),
            parse_moment_order(
                row
            ),
        )
    )

    for job in pending:

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

        prompt_file_raw = (
            job.get(
                "image_prompt_file",
                ""
            )
            .strip()
        )

        print(
            "=" * 60
        )

        print(
            "Checking:",
            moment_id,
        )

        # ----------------------------------------------------
        # BASIC VALIDATION
        # ----------------------------------------------------

        if not moment_id:

            print(
                "SKIP REASON: missing moment_id"
            )

            continue

        if not topic_id:

            print(
                "SKIP REASON: missing topic_id"
            )

            continue

        if not person:

            print(
                "SKIP REASON: missing person"
            )

            continue

        if not prompt_file_raw:

            print(
                "SKIP REASON: missing image_prompt_file"
            )

            continue

        prompt_file = (
            resolve_saved_path(
                prompt_file_raw
            )
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
            "Prompt:",
            prompt_file,
            bool(
                prompt_file
                and prompt_file.is_file()
            ),
        )

        if (
            prompt_file is None
            or not prompt_file.is_file()
        ):

            print(
                "SKIP REASON: image prompt file does not exist"
            )

            continue

        output_path = (
            build_output_path(
                job
            )
        )

        runnable = dict(
            job
        )

        runnable[
            "prompt_file"
        ] = prompt_file

        runnable[
            "output_path"
        ] = output_path

        print(
            "Output:",
            output_path,
        )

        print(
            "Runnable job found:",
            moment_id,
        )

        return runnable

    return None


# ============================================================
# PLUS IMAGE GENERATION LIMIT
# ============================================================

def parse_relative_reset_seconds(
    message_text,
):

    normalized = " ".join(
        str(
            message_text or ""
        )
        .lower()
        .split()
    )

    reset_match = re.search(
        r"limit\s+resets?\s+in\s+([^\.\n]+)",
        normalized,
        flags=re.IGNORECASE,
    )

    if not reset_match:

        return (
            None,
            "",
        )

    reset_description = (
        reset_match.group(1)
        .strip()
    )

    unit_patterns = [
        (
            86400,
            r"(\d+)\s*(?:days?|d)\b",
        ),
        (
            3600,
            r"(\d+)\s*(?:hours?|hrs?|h)\b",
        ),
        (
            60,
            r"(\d+)\s*(?:minutes?|mins?|min|m)\b",
        ),
        (
            1,
            r"(\d+)\s*(?:seconds?|secs?|sec|s)\b",
        ),
    ]

    total_seconds = 0
    found_any = False

    for multiplier, pattern in unit_patterns:

        unit_match = re.search(
            pattern,
            reset_description,
            flags=re.IGNORECASE,
        )

        if not unit_match:
            continue

        found_any = True

        total_seconds += (
            int(
                unit_match.group(1)
            )
            * multiplier
        )

    if (
        not found_any
        or total_seconds <= 0
    ):

        return (
            None,
            reset_description,
        )

    return (
        total_seconds,
        reset_description,
    )


def format_wait_duration(
    total_seconds,
):

    total_seconds = max(
        0,
        int(
            total_seconds
        ),
    )

    days, remainder = divmod(
        total_seconds,
        86400,
    )

    hours, remainder = divmod(
        remainder,
        3600,
    )

    minutes, seconds = divmod(
        remainder,
        60,
    )

    parts = []

    if days:

        parts.append(
            f"{days} day(s)"
        )

    if hours:

        parts.append(
            f"{hours} hour(s)"
        )

    if minutes:

        parts.append(
            f"{minutes} minute(s)"
        )

    if (
        seconds
        or not parts
    ):

        parts.append(
            f"{seconds} second(s)"
        )

    return " ".join(
        parts
    )


def get_new_assistant_messages(
    page,
    before_assistant_count,
):

    if (
        page is None
        or page.is_closed()
    ):

        return []

    messages = page.locator(
        "div[data-message-author-role='assistant']"
    )

    try:

        current_count = (
            messages.count()
        )

    except Exception:

        return []

    if (
        current_count
        <= before_assistant_count
    ):

        return []

    new_texts = []

    for index in range(
        before_assistant_count,
        current_count,
    ):

        try:

            message = (
                messages.nth(
                    index
                )
            )

            message_text = (
                message.inner_text(
                    timeout=10000
                )
                .strip()
            )

            if message_text:

                new_texts.append(
                    message_text
                )

        except Exception:

            continue

    return new_texts


def raise_if_image_generation_limit(
    page,
    before_assistant_count,
    stage,
):

    new_messages = (
        get_new_assistant_messages(
            page,
            before_assistant_count,
        )
    )

    if not new_messages:
        return

    limit_phrases = [
        (
            "you've hit the plus plan limit "
            "for image generations requests"
        ),
        (
            "you have hit the plus plan limit "
            "for image generations requests"
        ),
        (
            "you've hit the plus plan limit "
            "for image generation requests"
        ),
        (
            "you have hit the plus plan limit "
            "for image generation requests"
        ),
        (
            "i was unable to invoke the "
            "image-generation tool right now"
        ),
    ]

    for message_text in new_messages:

        normalized = " ".join(
            message_text
            .lower()
            .split()
        )

        if not any(
            phrase in normalized
            for phrase in limit_phrases
        ):

            continue

        (
            parsed_seconds,
            reset_description,
        ) = (
            parse_relative_reset_seconds(
                message_text
            )
        )

        if parsed_seconds is None:

            parsed_seconds = (
                IMAGE_LIMIT_FALLBACK_WAIT_SECONDS
            )

            print(
                "Could not parse reset time. "
                "Using fallback wait."
            )

        wait_seconds = (
            parsed_seconds
            + IMAGE_LIMIT_RESET_BUFFER_SECONDS
        )

        print(
            "=" * 60
        )

        print(
            "PLUS IMAGE GENERATION LIMIT DETECTED"
        )

        print(
            "Stage:",
            stage,
        )

        print(
            "Reset text:",
            reset_description
            or "not parsed",
        )

        print(
            "Wait:",
            format_wait_duration(
                wait_seconds
            ),
        )

        print(
            "=" * 60
        )

        raise ImageGenerationLimitError(
            (
                "ChatGPT Plus "
                "image-generation limit detected "
                f"at stage: {stage}"
            ),
            wait_seconds=
                wait_seconds,
            reset_description=
                reset_description,
        )


# ============================================================
# TOO MANY REQUESTS
# ============================================================

def get_too_many_requests_dialog(
    page,
):

    if (
        page is None
        or page.is_closed()
    ):

        return None

    dialog = (
        page.locator(
            "div[role='dialog']"
        )
        .filter(
            has_text=
                "Too many requests"
        )
        .first
    )

    try:

        if (
            dialog.count() > 0
            and dialog.is_visible()
        ):

            return dialog

    except Exception:

        return None

    return None


def raise_if_too_many_requests(
    page,
    stage,
):

    dialog = (
        get_too_many_requests_dialog(
            page
        )
    )

    if dialog is None:
        return

    print(
        "=" * 60
    )

    print(
        "TOO MANY REQUESTS DETECTED"
    )

    print(
        "Stage:",
        stage,
    )

    print(
        "=" * 60
    )

    try:

        got_it_button = (
            dialog.get_by_role(
                "button",
                name="Got it",
            )
            .first
        )

        if (
            got_it_button.count() > 0
            and got_it_button.is_visible()
        ):

            got_it_button.click(
                force=True
            )

            print(
                "Clicked Got it."
            )

            time.sleep(
                1
            )

    except Exception as error:

        print(
            "Could not dismiss "
            "rate-limit dialog:",
            error,
        )

    raise TooManyRequestsError(
        "ChatGPT Too many requests "
        f"detected at stage: {stage}"
    )


def get_rate_limit_cooldown(
    consecutive_rate_limits,
):

    index = min(
        max(
            consecutive_rate_limits - 1,
            0,
        ),
        len(
            RATE_LIMIT_COOLDOWNS
        ) - 1,
    )

    base_cooldown = (
        RATE_LIMIT_COOLDOWNS[
            index
        ]
    )

    jitter = random.randint(
        RATE_LIMIT_JITTER_MIN_SECONDS,
        RATE_LIMIT_JITTER_MAX_SECONDS,
    )

    return (
        base_cooldown
        + jitter
    )


# ============================================================
# CHATGPT BROWSER
# ============================================================

def open_chatgpt(
    playwright,
):

    browser = (
        playwright.chromium
        .launch_persistent_context(
            user_data_dir=
                CHATGPT_PROFILE_DIR,

            headless=False,

            channel="chrome",

            accept_downloads=True,

            args=[
                "--window-size=1600,1000",
                "--window-position=0,0",
            ],
        )
    )

    if browser.pages:

        page = (
            browser.pages[0]
        )

    else:

        page = (
            browser.new_page()
        )

    page.goto(
        CHATGPT_URL,
        wait_until=
            "domcontentloaded",
        timeout=120000,
    )

    print(
        "Waiting ChatGPT load..."
    )

    time.sleep(
        PAGE_LOAD_WAIT
    )

    # Bảo đảm composer đã thực sự xuất hiện.
    page.locator(
        "#prompt-textarea"
    ).wait_for(
        state="visible",
        timeout=30000,
    )

    print(
        "ChatGPT ready."
    )

    return (
        browser,
        page,
    )


# ============================================================
# PROMPT
# ============================================================

def fill_prompt(
    page,
    prompt,
):

    raise_if_too_many_requests(
        page,
        "before filling prompt",
    )

    prompt_box = (
        page.locator(
            "#prompt-textarea"
        )
    )

    prompt_box.wait_for(
        state="visible",
        timeout=30000,
    )

    prompt_box.click(
        force=True
    )

    # Clear trước để không dính text cũ.
    try:

        prompt_box.fill(
            ""
        )

    except Exception:

        prompt_box.click(
            force=True
        )

        page.keyboard.press(
            "Control+A"
        )

        page.keyboard.press(
            "Backspace"
        )

    prompt_box.fill(
        prompt
    )

    print(
        "Filled prompt"
    )

    time.sleep(
        PROMPT_READY_WAIT
    )

    raise_if_too_many_requests(
        page,
        "after filling prompt",
    )


# ============================================================
# SEND
# ============================================================

def wait_for_send_ready(
    page,
):
    """
    POV generation không upload input image.

    Chỉ cần chờ nút Send visible + enabled.
    """

    send_button = page.locator(
        'button[data-testid="send-button"]'
    )

    send_button.wait_for(
        state="visible",
        timeout=30000,
    )

    start_time = time.time()

    while True:

        raise_if_too_many_requests(
            page,
            "while waiting for Send",
        )

        try:

            enabled = (
                send_button.is_enabled()
            )

            aria_disabled = (
                send_button.get_attribute(
                    "aria-disabled"
                )
            )

            disabled_attribute = (
                send_button.get_attribute(
                    "disabled"
                )
            )

            ready = (
                enabled
                and aria_disabled != "true"
                and disabled_attribute is None
            )

        except Exception:

            ready = False

        if ready:

            print(
                "Send button ready."
            )

            return

        if (
            time.time()
            - start_time
            > 30
        ):

            raise TimeoutError(
                "Send button not ready "
                "after 30 seconds."
            )

        time.sleep(
            1
        )


# ============================================================
# WAIT GENERATED IMAGE
# ============================================================

def wait_for_generated_image(
    page,
    before_count,
    before_assistant_count,
):

    print(
        "Waiting generated image..."
    )

    start_render_time = (
        time.time()
    )

    while True:

        raise_if_too_many_requests(
            page,
            "while waiting for generated image",
        )

        raise_if_image_generation_limit(
            page,
            before_assistant_count,
            "while waiting for generated image",
        )

        current_count = (
            page.locator(
                'img[alt^="Generated image"]'
            )
            .count()
        )

        print(
            "Generated image count:",
            current_count,
        )

        if (
            current_count
            > before_count
        ):

            return

        elapsed = (
            time.time()
            - start_render_time
        )

        if (
            elapsed
            > MAX_RENDER_TIME
        ):

            raise TimeoutError(
                "Render timeout > "
                f"{MAX_RENDER_TIME} seconds"
            )

        time.sleep(
            10
        )


# ============================================================
# NORMALIZE DOWNLOADED IMAGE
# ============================================================

def image_has_transparency(
    image,
):

    if (
        "A"
        in image.getbands()
    ):

        return True

    return (
        "transparency"
        in image.info
    )


def normalize_downloaded_output_to_png(
    downloaded_path,
):

    downloaded_path = str(
        downloaded_path
    )

    if not os.path.isfile(
        downloaded_path
    ):

        raise FileNotFoundError(
            "Không tìm thấy ảnh vừa tải: "
            f"{downloaded_path}"
        )

    temporary_path = (
        downloaded_path
        + ".real_png.temporary"
    )

    detected_format = None

    try:

        with Image.open(
            downloaded_path
        ) as image:

            detected_format = (
                image.format
                or "UNKNOWN"
            )

            if getattr(
                image,
                "is_animated",
                False,
            ):

                image.seek(
                    0
                )

            image = (
                ImageOps.exif_transpose(
                    image
                )
            )

            if (
                image_has_transparency(
                    image
                )
            ):

                normalized_image = (
                    image.convert(
                        "RGBA"
                    )
                )

            else:

                normalized_image = (
                    image.convert(
                        "RGB"
                    )
                )

            normalized_image.save(
                temporary_path,
                format="PNG",
                optimize=True,
            )

            normalized_image.close()

        os.replace(
            temporary_path,
            downloaded_path,
        )

        with Image.open(
            downloaded_path
        ) as verified:

            if (
                verified.format
                != "PNG"
            ):

                raise ValueError(
                    "Output sau chuẩn hóa "
                    "không phải PNG."
                )

            width, height = (
                verified.size
            )

        print(
            "Normalized downloaded image:"
        )

        print(
            "  Detected source format:",
            detected_format,
        )

        print(
            "  Final format: PNG"
        )

        print(
            "  Final size:",
            f"{width}x{height}",
        )

    except Exception:

        if os.path.exists(
            temporary_path
        ):

            try:

                os.remove(
                    temporary_path
                )

            except OSError:

                pass

        raise


# ============================================================
# SAVE GENERATED IMAGE
# ============================================================

def save_latest_generated_image(
    page,
    output_path,
):

    raise_if_too_many_requests(
        page,
        "before saving generated image",
    )

    generated_image = (
        page.locator(
            'img[alt^="Generated image"]'
        )
        .last
    )

    generated_image.scroll_into_view_if_needed()

    time.sleep(
        2
    )

    generated_image.click(
        force=True
    )

    print(
        "Clicked generated image"
    )

    time.sleep(
        AFTER_FULLSCREEN_OPEN_WAIT
    )

    output_path = Path(
        output_path
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with page.expect_download(
        timeout=180000,
    ) as download_info:

        page.locator(
            'button[aria-label="Save"]'
        ).click(
            force=True
        )

    download = (
        download_info.value
    )

    download.save_as(
        str(
            output_path
        )
    )

    if not output_path.is_file():

        raise FileNotFoundError(
            "Download completed but "
            "output was not found:\n"
            f"{output_path}"
        )

    normalize_downloaded_output_to_png(
        output_path
    )

    print(
        "Saved image:",
        output_path,
    )

    close_button = (
        page.locator(
            'button[aria-label="Close fullscreen view"]'
        )
    )

    if (
        close_button.count()
        > 0
    ):

        close_button.click(
            force=True
        )

        print(
            "Closed fullscreen view"
        )

    time.sleep(
        AFTER_FULLSCREEN_CLOSE_WAIT
    )


# ============================================================
# DEBUG
# ============================================================

def safe_screenshot(
    page,
    moment_id,
):

    if page is None:
        return

    try:

        if page.is_closed():
            return

        screenshot_path = (
            DEBUG_DIR
            / (
                "pov_image_"
                f"{sanitize_filename(moment_id)}.png"
            )
        )

        page.screenshot(
            path=str(
                screenshot_path
            ),
            full_page=True,
        )

        print(
            "Debug screenshot:",
            screenshot_path,
        )

    except Exception as error:

        print(
            "Could not save debug screenshot:",
            error,
        )


# ============================================================
# CLOSE BROWSER
# ============================================================

def close_browser(
    browser,
):

    if browser is None:
        return True

    try:

        print(
            "Closing current Chrome browser..."
        )

        browser.close()

        print(
            "Current Chrome browser closed."
        )

        return True

    except Exception as error:

        print(
            "Could not close browser:",
            error,
        )

        return False


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # RESET INTERRUPTED JOBS
    # --------------------------------------------------------

    rows = load_queue()

    reset_interrupted(
        rows
    )

    rows = load_queue()

    # --------------------------------------------------------
    # CHECK BEFORE OPENING CHROME
    # --------------------------------------------------------

    first_job = (
        get_next_pending_job(
            rows
        )
    )

    if not first_job:

        print(
            "=" * 60
        )

        print(
            "No runnable POV image jobs left."
        )

        return

    # ========================================================
    # PLAYWRIGHT
    # ========================================================

    with sync_playwright() as playwright:

        browser = None
        page = None

        consecutive_rate_limits = 0

        while True:

            rows = load_queue()

            job = (
                get_next_pending_job(
                    rows
                )
            )

            if not job:

                print(
                    "=" * 60
                )

                print(
                    "No runnable POV image jobs left."
                )

                break

            # ------------------------------------------------
            # JOB DATA
            # ------------------------------------------------

            moment_id = (
                job[
                    "moment_id"
                ]
            )

            topic_id = (
                job[
                    "topic_id"
                ]
            )

            person = (
                job.get(
                    "person",
                    "",
                )
            )

            moment_order = (
                job.get(
                    "moment_order",
                    "",
                )
            )

            moment = (
                job.get(
                    "moment",
                    "",
                )
            )

            prompt_file = (
                job[
                    "prompt_file"
                ]
            )

            output_path = (
                job[
                    "output_path"
                ]
            )

            # ------------------------------------------------
            # OPEN BROWSER WHEN NEEDED
            # ------------------------------------------------

            if (
                browser is None
                or page is None
            ):

                print(
                    "Opening new ChatGPT session..."
                )

                (
                    browser,
                    page,
                ) = open_chatgpt(
                    playwright
                )

            # ------------------------------------------------
            # ATTEMPTS
            # ------------------------------------------------

            try:

                attempts = int(
                    job.get(
                        "image_attempts",
                        ""
                    )
                    or 0
                )

            except ValueError:

                attempts = 0

            # ------------------------------------------------
            # READ PROMPT
            # ------------------------------------------------

            prompt = (
                read_text(
                    prompt_file
                )
            )

            print(
                "=" * 60
            )

            print(
                "Running POV image job:",
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
                "Moment:",
                moment,
            )

            print(
                "Prompt:",
                prompt_file,
            )

            print(
                "Output:",
                output_path,
            )

            # ------------------------------------------------
            # MARK RUNNING
            # ------------------------------------------------

            update_job(
                moment_id,
                status=
                    "processing_start_frame",
                error="",
            )

            try:

                # ============================================
                # COUNT BEFORE SEND
                # ============================================

                before_count = (
                    page.locator(
                        'img[alt^="Generated image"]'
                    )
                    .count()
                )

                assistant_count_before_send = (
                    page.locator(
                        "div[data-message-author-role="
                        "'assistant']"
                    )
                    .count()
                )

                print(
                    "Generated images before Send:",
                    before_count,
                )

                print(
                    "Assistant messages before Send:",
                    assistant_count_before_send,
                )

                # ============================================
                # FILL
                # ============================================

                fill_prompt(
                    page,
                    prompt,
                )

                # ============================================
                # SEND READY
                # ============================================

                wait_for_send_ready(
                    page
                )

                raise_if_too_many_requests(
                    page,
                    "immediately before Send",
                )

                # ============================================
                # SEND
                # ============================================

                page.locator(
                    'button[data-testid="send-button"]'
                ).click(
                    force=True
                )

                print(
                    "Sent prompt"
                )

                time.sleep(
                    AFTER_SEND_WAIT
                )

                # ============================================
                # CHECK LIMITS
                # ============================================

                raise_if_too_many_requests(
                    page,
                    "immediately after Send",
                )

                raise_if_image_generation_limit(
                    page,
                    assistant_count_before_send,
                    "immediately after Send",
                )

                # ============================================
                # WAIT IMAGE
                # ============================================

                wait_for_generated_image(
                    page,
                    before_count,
                    assistant_count_before_send,
                )

                # Worker cũ của bạn chờ thêm 12s
                # để ảnh/nút Save ổn định.
                time.sleep(
                    IMAGE_READY_BEFORE_SAVE_WAIT
                )

                # ============================================
                # SAVE IMAGE
                # ============================================

                save_latest_generated_image(
                    page,
                    output_path,
                )

                # ============================================
                # DONE
                # ============================================

                update_job(
                    moment_id,
                    status=
                        "start_frame_generated",
                    image_attempts=
                        str(
                            attempts + 1
                        ),
                    start_frame_file=
                        str(
                            output_path
                        ),
                    error="",
                )

                print(
                    "POV start frame done:",
                    moment_id,
                )

                consecutive_rate_limits = 0

                # ============================================
                # RESTART AFTER EACH IMAGE
                # ============================================

                if (
                    RESTART_AFTER_EACH_IMAGE
                ):

                    print(
                        "Image completed. "
                        "Restarting browser before next image:",
                        moment_id,
                    )

                    close_browser(
                        browser
                    )

                    browser = None
                    page = None

                    if (
                        BROWSER_RESTART_DELAY
                        > 0
                    ):

                        time.sleep(
                            BROWSER_RESTART_DELAY
                        )

            # =================================================
            # PLUS LIMIT
            # =================================================

            except ImageGenerationLimitError as error:

                wait_seconds = max(
                    1,
                    int(
                        error.wait_seconds
                    ),
                )

                print(
                    "=" * 60
                )

                print(
                    "POV IMAGE WORKER PLUS LIMIT"
                )

                print(
                    "Moment:",
                    moment_id,
                )

                print(
                    "Reset:",
                    (
                        error.reset_description
                        or "not parsed"
                    ),
                )

                print(
                    "Worker wait:",
                    format_wait_duration(
                        wait_seconds
                    ),
                )

                print(
                    "=" * 60
                )

                # Đây không phải lỗi nội dung của moment.
                # Không tăng attempts.
                update_job(
                    moment_id,
                    status=
                        "prompts_generated",
                    image_attempts=
                        str(
                            attempts
                        ),
                    error=(
                        str(error)
                        + " | reset="
                        + (
                            error.reset_description
                            or "unknown"
                        )
                        + " | wait="
                        + str(
                            wait_seconds
                        )
                        + "s"
                    ),
                )

                safe_screenshot(
                    page,
                    moment_id,
                )

                if browser is not None:

                    close_browser(
                        browser
                    )

                    browser = None
                    page = None

                print(
                    "No new image request "
                    "until reset window."
                )

                time.sleep(
                    wait_seconds
                )

            # =================================================
            # TOO MANY REQUESTS
            # =================================================

            except TooManyRequestsError as error:

                consecutive_rate_limits += 1

                cooldown_seconds = (
                    get_rate_limit_cooldown(
                        consecutive_rate_limits
                    )
                )

                print(
                    "=" * 60
                )

                print(
                    "POV IMAGE WORKER RATE LIMITED"
                )

                print(
                    "Moment:",
                    moment_id,
                )

                print(
                    "Consecutive:",
                    consecutive_rate_limits,
                )

                print(
                    "Cooldown:",
                    cooldown_seconds,
                    "seconds",
                )

                print(
                    "=" * 60
                )

                # Rate limit không tăng attempts.
                update_job(
                    moment_id,
                    status=
                        "prompts_generated",
                    image_attempts=
                        str(
                            attempts
                        ),
                    error=(
                        str(error)
                        + " | cooldown="
                        + str(
                            cooldown_seconds
                        )
                        + "s"
                    ),
                )

                safe_screenshot(
                    page,
                    moment_id,
                )

                if browser is not None:

                    close_browser(
                        browser
                    )

                    browser = None
                    page = None

                print(
                    "No requests during cooldown."
                )

                time.sleep(
                    cooldown_seconds
                )

            # =================================================
            # NORMAL ERROR
            # =================================================

            except Exception as error:

                error_text = str(
                    error
                )

                print(
                    "POV image job failed:",
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
                        "start_frame_failed"
                    )

                else:

                    next_status = (
                        "prompts_generated"
                    )

                update_job(
                    moment_id,
                    status=
                        next_status,
                    image_attempts=
                        str(
                            attempts
                        ),
                    error=
                        error_text,
                )

                safe_screenshot(
                    page,
                    moment_id,
                )

                if browser is not None:

                    print(
                        "Closing browser after failure"
                    )

                    close_browser(
                        browser
                    )

                    browser = None
                    page = None

                time.sleep(
                    5
                )

        # ====================================================
        # FINISH
        # ====================================================

        print(
            "=" * 60
        )

        print(
            "POV image batch finished."
        )

        if browser is not None:

            close_browser(
                browser
            )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    main()