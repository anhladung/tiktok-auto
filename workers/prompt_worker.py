from __future__ import annotations

import csv
import json
import os
import re
import time

from pathlib import Path
from typing import Any

from playwright.sync_api import (
    sync_playwright,
)


# ============================================================
# PROJECT ROOT
# ============================================================

def find_project_root() -> Path:

    current = Path(__file__).resolve()

    for parent in current.parents:

        if (
            (parent / "prompts").exists()
            and
            (parent / "queue").exists()
        ):
            return parent

    raise RuntimeError(
        "Could not find PROJECT_ROOT."
    )


PROJECT_ROOT = find_project_root()


# ============================================================
# PATHS
# ============================================================

PROMPT_FILE = (
    PROJECT_ROOT
    / "prompts"
    / "youtube"
    / "pov"
    / "prompt_generation"
    / "prompt_generator.txt"
)


MOMENT_QUEUE_FILE = (
    PROJECT_ROOT
    / "queue"
    / "moment_queue.csv"
)


GENERATED_PROMPT_DIR = (
    PROJECT_ROOT
    / "generated_prompts"
)


DEBUG_DIR = (
    PROJECT_ROOT
    / "debug"
    / "prompt_worker"
)


DEBUG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# CHATGPT
# ============================================================

CHATGPT_PROFILE_DIR = (
    r"C:\chatgpt_auto_profile"
)


CHATGPT_URL = (
    "https://chatgpt.com/"
    "g/g-p-6a59ccfe43208191a8a880795664b046/project"
)


# ============================================================
# SETTINGS
# ============================================================

HEADLESS = False


NAVIGATION_TIMEOUT = 60_000

PROMPT_TIMEOUT = 40_000

PROMPT_LOAD_TIMEOUT = 25_000

SEND_CONFIRM_TIMEOUT = 20_000

RESPONSE_TIMEOUT = 240_000


# ============================================================
# WAIT
# ============================================================

PAGE_READY_DELAY = 5

AFTER_BROWSER_LAUNCH_DELAY = 2

PROMPT_READY_DELAY = 2

AFTER_SEND_DELAY = 2

OUTPUT_START_DELAY = 3

OUTPUT_END_DELAY = 2


# ------------------------------------------------------------
# IMPORTANT:
#
# Browser is COMPLETELY closed after every moment.
# Give Chrome enough time to release persistent profile.
# ------------------------------------------------------------

BETWEEN_JOBS_DELAY = 8

BROWSER_RESTART_DELAY = 8


# ============================================================
# RESPONSE STABILITY
# ============================================================

STABLE_CHECK_INTERVAL = 2

STABLE_CHECKS_REQUIRED = 3


# ============================================================
# RETRY
# ============================================================

MAX_RETRIES = 3

RETRY_DELAY = 8


# ============================================================
# END MARKER
# ============================================================

PROMPT_END_MARKER = (
    "<END_VISUAL_PROMPT_JSON>"
)


# ============================================================
# LOAD TEMPLATE
# ============================================================

def load_prompt_template() -> str:

    if not PROMPT_FILE.exists():

        raise FileNotFoundError(
            "\nPrompt template not found:\n"
            f"{PROMPT_FILE}"
        )

    return (
        PROMPT_FILE
        .read_text(
            encoding="utf-8"
        )
        .strip()
    )


# ============================================================
# MOMENT QUEUE
# ============================================================

def load_moment_queue():

    if not MOMENT_QUEUE_FILE.exists():

        raise FileNotFoundError(
            "\nMoment queue not found:\n"
            f"{MOMENT_QUEUE_FILE}"
        )

    with open(
        MOMENT_QUEUE_FILE,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        return list(
            csv.DictReader(f)
        )


def get_queue_fieldnames(
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
        "image_prompt_file",
        "video_prompt_file",
        "error",
    ]

    for field in additional:

        if field not in fieldnames:

            fieldnames.append(
                field
            )

    return fieldnames


def save_moment_queue(
    rows,
):

    if not rows:
        return

    fieldnames = (
        get_queue_fieldnames(
            rows
        )
    )

    temp_file = (
        str(MOMENT_QUEUE_FILE)
        + ".tmp"
    )

    with open(
        temp_file,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()

        writer.writerows(
            rows
        )

    os.replace(
        temp_file,
        MOMENT_QUEUE_FILE,
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
        )

        if (
            status
            == "processing_prompt"
        ):

            row["status"] = (
                "pending_prompt"
            )

            row["error"] = ""

            changed = True

    if changed:

        save_moment_queue(
            rows
        )


# ============================================================
# BUILD PROMPT
# ============================================================

def build_prompt(
    template,
    row,
):

    moment_id = (
        row.get(
            "moment_id",
            ""
        )
        .strip()
    )

    person = (
        row.get(
            "person",
            ""
        )
        .strip()
    )

    moment_order = (
        row.get(
            "moment_order",
            ""
        )
        .strip()
    )

    moment = (
        row.get(
            "moment",
            ""
        )
        .strip()
    )

    short_title = (
        row.get(
            "short_title",
            ""
        )
        .strip()
    )

    moment_type = (
        row.get(
            "moment_type",
            ""
        )
        .strip()
    )

    environment = (
        row.get(
            "environment",
            ""
        )
        .strip()
    )

    visual_signature = (
        row.get(
            "visual_signature",
            ""
        )
        .strip()
    )

    motion = (
        row.get(
            "motion",
            ""
        )
        .strip()
    )

    is_identity_hook = (
        row.get(
            "is_identity_hook",
            ""
        )
        .strip()
    )

    return (
        template

        + "\n\n"

        + "==================================================\n"
        + "INPUT\n"
        + "==================================================\n\n"

        + f"MOMENT_ID: {moment_id}\n\n"

        + f"PERSON: {person}\n\n"

        + f"MOMENT_ORDER: {moment_order}\n\n"

        + f"IS_IDENTITY_HOOK: "
        + f"{is_identity_hook}\n\n"

        + f"SHORT_TITLE: "
        + f"{short_title}\n\n"

        + f"MOMENT:\n"
        + f"{moment}\n\n"

        + f"MOMENT_TYPE:\n"
        + f"{moment_type}\n\n"

        + f"ENVIRONMENT:\n"
        + f"{environment}\n\n"

        + f"VISUAL_SIGNATURE:\n"
        + f"{visual_signature}\n\n"

        + f"INTENDED_MOTION:\n"
        + f"{motion}\n\n"

        + "Generate the IMAGE_PROMPT and VIDEO_PROMPT "
        + "for this specific moment.\n\n"

        + "After the complete JSON object, output "
        + "this exact marker on a new line:\n\n"

        + PROMPT_END_MARKER
    )


# ============================================================
# PAGE HEALTH
# ============================================================

def ensure_page_alive(
    page,
):

    if page is None:

        raise RuntimeError(
            "CHATGPT_PAGE_MISSING"
        )

    try:

        if page.is_closed():

            raise RuntimeError(
                "CHATGPT_PAGE_CLOSED"
            )

    except RuntimeError:

        raise

    except Exception as exc:

        raise RuntimeError(
            "CHATGPT_PAGE_UNAVAILABLE"
        ) from exc


# ============================================================
# SAFE SCREENSHOT
# ============================================================

def safe_screenshot(
    page,
    moment_id,
    suffix,
):

    if page is None:
        return

    try:

        if page.is_closed():
            return

        screenshot_file = (
            DEBUG_DIR
            / (
                f"{moment_id}_"
                f"{suffix}.png"
            )
        )

        # Do not full-page screenshot long ChatGPT threads.
        page.screenshot(
            path=str(
                screenshot_file
            ),
            full_page=False,
            timeout=10_000,
        )

        print(
            "[DEBUG] Screenshot:",
            screenshot_file,
        )

    except Exception as exc:

        print(
            "[DEBUG] Screenshot skipped:",
            exc,
        )


# ============================================================
# EDITOR TEXT
# ============================================================

def get_editor_text(
    textarea,
):

    try:

        text = textarea.evaluate(
            """
            el => {

                if (
                    typeof el.value === "string"
                    && el.value
                ) {
                    return el.value.trim();
                }

                if (el.innerText) {
                    return el.innerText.trim();
                }

                if (el.textContent) {
                    return el.textContent.trim();
                }

                return "";
            }
            """
        )

        return (
            text or ""
        ).strip()

    except Exception:

        return ""


# ============================================================
# OPEN PROJECT
# ============================================================

def open_project(
    page,
):

    ensure_page_alive(
        page
    )

    print(
        "[WAIT] Opening ChatGPT project..."
    )

    page.goto(
        CHATGPT_URL,
        wait_until="domcontentloaded",
        timeout=NAVIGATION_TIMEOUT,
    )

    ensure_page_alive(
        page
    )

    page.set_default_timeout(
        PROMPT_TIMEOUT
    )

    textarea = (
        page.locator(
            "#prompt-textarea"
        )
    )

    textarea.wait_for(
        state="visible",
        timeout=PROMPT_TIMEOUT,
    )

    print(
        "[WAIT] Prompt area visible."
    )

    page.wait_for_timeout(
        PAGE_READY_DELAY
        * 1000
    )

    ensure_page_alive(
        page
    )

    print(
        "[OK] ChatGPT project ready."
    )


# ============================================================
# OPEN FRESH BROWSER
# ============================================================

def open_browser_session(
    playwright,
):

    print()
    print(
        "[BROWSER] Launching NEW Chrome process..."
    )

    context = (
        playwright.chromium
        .launch_persistent_context(

            user_data_dir=
                CHATGPT_PROFILE_DIR,

            channel=
                "chrome",

            headless=
                HEADLESS,

            viewport={
                "width": 1440,
                "height": 1000,
            },

            accept_downloads=True,

            args=[
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=CalculateNativeWinOcclusion",
                "--disable-session-crashed-bubble",
                "--no-first-run",
            ],
        )
    )

    try:

        time.sleep(
            AFTER_BROWSER_LAUNCH_DELAY
        )

        # ====================================================
        # IMPORTANT:
        #
        # launch_persistent_context may restore pages from the
        # previous session.
        #
        # We DO NOT reuse those pages.
        # ====================================================

        restored_pages = list(
            context.pages
        )

        # Always create a NEW blank page.
        page = (
            context.new_page()
        )

        print(
            "[BROWSER] Fresh blank tab created."
        )

        # Close restored/stale tabs.
        for old_page in restored_pages:

            if old_page == page:
                continue

            try:

                old_page.close(
                    run_before_unload=False
                )

            except Exception:

                pass

        # ----------------------------------------------------
        # DEBUG EVENTS
        # ----------------------------------------------------

        page.on(
            "crash",
            lambda crashed_page:
                print(
                    "[BROWSER] PAGE CRASH DETECTED."
                )
        )

        page.on(
            "close",
            lambda closed_page:
                print(
                    "[BROWSER] Page closed."
                )
        )

        # ----------------------------------------------------
        # OPEN PROJECT
        # ----------------------------------------------------

        open_project(
            page
        )

        print(
            "[BROWSER] Fresh ChatGPT session ready."
        )

        return (
            context,
            page,
        )

    except Exception:

        try:

            context.close()

        except Exception:

            pass

        raise


# ============================================================
# CLOSE BROWSER COMPLETELY
# ============================================================

def close_browser_session(
    context,
):

    if context is None:
        return

    print(
        "[BROWSER] Closing browser completely..."
    )

    # --------------------------------------------------------
    # CLOSE ALL PAGES
    # --------------------------------------------------------

    try:

        for page in list(
            context.pages
        ):

            try:

                if not page.is_closed():

                    page.close(
                        run_before_unload=False
                    )

            except Exception:

                pass

    except Exception:

        pass

    # --------------------------------------------------------
    # CLOSE CONTEXT
    # --------------------------------------------------------

    try:

        context.close()

    except Exception as exc:

        print(
            "[BROWSER] Context close warning:",
            exc,
        )

    print(
        "[BROWSER] Browser/context closed."
    )


# ============================================================
# WAIT PROMPT LOADED
# ============================================================

def wait_for_prompt_loaded(
    page,
    textarea,
    prompt,
):

    print(
        "[WAIT] Checking prompt content..."
    )

    deadline = (
        time.time()
        + PROMPT_LOAD_TIMEOUT / 1000
    )

    prompt_length = len(
        prompt.strip()
    )

    minimum_length = max(
        30,
        int(
            prompt_length
            * 0.70
        ),
    )

    while (
        time.time()
        < deadline
    ):

        ensure_page_alive(
            page
        )

        current_text = (
            get_editor_text(
                textarea
            )
        )

        if (
            len(current_text)
            >= minimum_length
        ):

            print(
                "[OK] Prompt loaded."
            )

            return

        time.sleep(
            0.5
        )

    raise TimeoutError(
        "Prompt did not finish loading."
    )


# ============================================================
# WAIT PROMPT SUBMITTED
# ============================================================

def wait_for_prompt_submitted(
    page,
    textarea,
    assistant_messages,
    count_before,
):

    deadline = (
        time.time()
        + SEND_CONFIRM_TIMEOUT / 1000
    )

    while (
        time.time()
        < deadline
    ):

        ensure_page_alive(
            page
        )

        editor_text = (
            get_editor_text(
                textarea
            )
        )

        try:

            assistant_count = (
                assistant_messages.count()
            )

        except Exception as exc:

            raise RuntimeError(
                "CHATGPT_PAGE_LOST_DURING_SEND"
            ) from exc

        if not editor_text:

            return

        if (
            assistant_count
            > count_before
        ):

            return

        time.sleep(
            0.5
        )

    raise TimeoutError(
        "Could not confirm prompt submission."
    )


# ============================================================
# SEND PROMPT
# ============================================================

def send_prompt(
    page,
    prompt,
):

    ensure_page_alive(
        page
    )

    textarea = (
        page.locator(
            "#prompt-textarea"
        )
    )

    textarea.wait_for(
        state="visible",
        timeout=PROMPT_TIMEOUT,
    )

    ensure_page_alive(
        page
    )

    textarea.scroll_into_view_if_needed()

    textarea.click(
        force=True
    )

    # --------------------------------------------------------
    # CLEAR
    # --------------------------------------------------------

    try:

        textarea.fill("")

    except Exception:

        ensure_page_alive(
            page
        )

        textarea.click(
            force=True
        )

        page.keyboard.press(
            "Control+A"
        )

        page.keyboard.press(
            "Backspace"
        )

    # --------------------------------------------------------
    # FILL
    # --------------------------------------------------------

    print(
        "[WAIT] Filling prompt..."
    )

    try:

        textarea.fill(
            prompt
        )

    except Exception:

        ensure_page_alive(
            page
        )

        textarea.click(
            force=True
        )

        page.keyboard.insert_text(
            prompt
        )

    # --------------------------------------------------------
    # VERIFY
    # --------------------------------------------------------

    wait_for_prompt_loaded(
        page,
        textarea,
        prompt,
    )

    print(
        f"[WAIT] Prompt settling "
        f"{PROMPT_READY_DELAY}s..."
    )

    page.wait_for_timeout(
        PROMPT_READY_DELAY
        * 1000
    )

    ensure_page_alive(
        page
    )

    assistant_messages = (
        page.locator(
            '[data-message-author-role="assistant"]'
        )
    )

    count_before = (
        assistant_messages.count()
    )

    # --------------------------------------------------------
    # SEND
    # --------------------------------------------------------

    print(
        "[SEND] Sending visual prompt request..."
    )

    page.keyboard.press(
        "Enter"
    )

    wait_for_prompt_submitted(
        page,
        textarea,
        assistant_messages,
        count_before,
    )

    print(
        "[OK] Prompt submitted."
    )

    page.wait_for_timeout(
        AFTER_SEND_DELAY
        * 1000
    )

    return (
        count_before
    )


# ============================================================
# WAIT RESPONSE
# ============================================================

def wait_for_response(
    page,
    count_before,
):

    ensure_page_alive(
        page
    )

    assistant_messages = (
        page.locator(
            '[data-message-author-role="assistant"]'
        )
    )

    print(
        "[WAIT] Waiting for visual prompts..."
    )

    appear_deadline = (
        time.time()
        + RESPONSE_TIMEOUT / 1000
    )

    # ========================================================
    # WAIT FOR NEW MESSAGE
    # ========================================================

    while (
        time.time()
        < appear_deadline
    ):

        ensure_page_alive(
            page
        )

        try:

            current_count = (
                assistant_messages.count()
            )

        except Exception as exc:

            raise RuntimeError(
                "CHATGPT_PAGE_LOST_WAITING_RESPONSE"
            ) from exc

        if (
            current_count
            > count_before
        ):

            print(
                "[OK] Output appeared."
            )

            break

        time.sleep(
            1
        )

    else:

        raise TimeoutError(
            "Response did not appear."
        )

    # ========================================================
    # LET STREAM BEGIN
    # ========================================================

    page.wait_for_timeout(
        OUTPUT_START_DELAY
        * 1000
    )

    finish_deadline = (
        time.time()
        + RESPONSE_TIMEOUT / 1000
    )

    previous_text = ""

    stable_count = 0

    marker_seen = False

    # ========================================================
    # WAIT UNTIL COMPLETE
    # ========================================================

    while (
        time.time()
        < finish_deadline
    ):

        ensure_page_alive(
            page
        )

        try:

            current_text = (
                assistant_messages
                .last
                .inner_text(
                    timeout=15_000
                )
                .strip()
            )

        except Exception as exc:

            raise RuntimeError(
                "CHATGPT_PAGE_LOST_DURING_STREAM"
            ) from exc

        # ----------------------------------------------------
        # END MARKER
        # ----------------------------------------------------

        if (
            PROMPT_END_MARKER
            in current_text
        ):

            if not marker_seen:

                print(
                    "[WAIT] End marker detected."
                )

            marker_seen = True

        # ----------------------------------------------------
        # STABILITY
        # ----------------------------------------------------

        if (
            marker_seen
            and current_text
            and current_text
            == previous_text
        ):

            stable_count += 1

            print(
                f"[WAIT] Output stable "
                f"{stable_count}/"
                f"{STABLE_CHECKS_REQUIRED}"
            )

        else:

            stable_count = 0

        previous_text = (
            current_text
        )

        # ----------------------------------------------------
        # FINISHED
        # ----------------------------------------------------

        if (
            marker_seen
            and stable_count
            >= STABLE_CHECKS_REQUIRED
        ):

            page.wait_for_timeout(
                OUTPUT_END_DELAY
                * 1000
            )

            ensure_page_alive(
                page
            )

            final_text = (
                assistant_messages
                .last
                .inner_text(
                    timeout=15_000
                )
                .strip()
            )

            final_text = (
                final_text
                .replace(
                    PROMPT_END_MARKER,
                    "",
                )
                .strip()
            )

            print(
                "[OK] Visual prompts finished."
            )

            return (
                final_text
            )

        time.sleep(
            STABLE_CHECK_INTERVAL
        )

    raise TimeoutError(
        "Visual prompt response "
        "did not finish."
    )


# ============================================================
# JSON PARSER
# ============================================================

def extract_json(
    text: str,
) -> dict[str, Any]:

    text = (
        text.strip()
    )

    # Remove markdown fences if present.
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
    )

    # ========================================================
    # DIRECT JSON
    # ========================================================

    try:

        data = (
            json.loads(
                text
            )
        )

        if not isinstance(
            data,
            dict,
        ):

            raise ValueError(
                "JSON root must be object."
            )

        return data

    except json.JSONDecodeError:

        pass

    # ========================================================
    # FALLBACK
    # ========================================================

    start = (
        text.find(
            "{"
        )
    )

    end = (
        text.rfind(
            "}"
        )
    )

    if (
        start == -1
        or end == -1
        or end <= start
    ):

        print()
        print(
            "[DEBUG] RAW RESPONSE"
        )

        print(
            "-" * 60
        )

        print(
            text
        )

        print(
            "-" * 60
        )

        raise ValueError(
            "Could not find JSON."
        )

    json_text = (
        text[
            start:
            end + 1
        ]
    )

    try:

        data = (
            json.loads(
                json_text
            )
        )

    except json.JSONDecodeError as exc:

        print()
        print(
            "[DEBUG] INVALID JSON"
        )

        print(
            "-" * 60
        )

        print(
            json_text
        )

        print(
            "-" * 60
        )

        raise ValueError(
            f"Invalid JSON: {exc}"
        )

    if not isinstance(
        data,
        dict,
    ):

        raise ValueError(
            "JSON root must be object."
        )

    return data


# ============================================================
# VALIDATE RESULT
# ============================================================

def validate_result(
    data,
):

    image_prompt = (
        str(
            data.get(
                "image_prompt",
                ""
            )
        )
        .strip()
    )

    video_prompt = (
        str(
            data.get(
                "video_prompt",
                ""
            )
        )
        .strip()
    )

    if not image_prompt:

        raise ValueError(
            "Missing image_prompt."
        )

    if not video_prompt:

        raise ValueError(
            "Missing video_prompt."
        )

    if (
        len(image_prompt)
        < 100
    ):

        raise ValueError(
            "image_prompt is too short."
        )

    if (
        len(video_prompt)
        < 80
    ):

        raise ValueError(
            "video_prompt is too short."
        )

    return {
        "image_prompt":
            image_prompt,

        "video_prompt":
            video_prompt,
    }


# ============================================================
# SAVE GENERATED PROMPTS
# ============================================================

def save_generated_prompts(
    row,
    result,
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
        GENERATED_PROMPT_DIR
        / topic_id
        / moment_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    image_file = (
        output_dir
        / "image_prompt.txt"
    )

    video_file = (
        output_dir
        / "video_prompt.txt"
    )

    image_file.write_text(
        result[
            "image_prompt"
        ],
        encoding="utf-8",
    )

    video_file.write_text(
        result[
            "video_prompt"
        ],
        encoding="utf-8",
    )

    return {
        "image_prompt_file":
            str(
                image_file
            ),

        "video_prompt_file":
            str(
                video_file
            ),
    }


# ============================================================
# PROCESS MOMENT
# ============================================================

def process_moment(
    page,
    row,
    template,
):

    ensure_page_alive(
        page
    )

    prompt = (
        build_prompt(
            template,
            row,
        )
    )

    count_before = (
        send_prompt(
            page,
            prompt,
        )
    )

    response = (
        wait_for_response(
            page,
            count_before,
        )
    )

    data = (
        extract_json(
            response
        )
    )

    return (
        validate_result(
            data
        )
    )


# ============================================================
# PRINT RESULT
# ============================================================

def print_result(
    row,
    result,
):

    print()
    print(
        "=" * 60
    )

    print(
        f"MOMENT: "
        f"{row.get('moment_id', '')}"
    )

    print(
        "=" * 60
    )

    print()

    print(
        "[IMAGE PROMPT]"
    )

    print()

    print(
        result[
            "image_prompt"
        ]
    )

    print()

    print(
        "[VIDEO PROMPT]"
    )

    print()

    print(
        result[
            "video_prompt"
        ]
    )


# ============================================================
# WORKER
# ============================================================

def run_worker():

    rows = (
        load_moment_queue()
    )

    reset_interrupted(
        rows
    )

    rows = (
        load_moment_queue()
    )

    pending = [
        row
        for row in rows
        if (
            row.get(
                "status",
                ""
            )
            .strip()
            == "pending_prompt"
        )
    ]

    print()
    print(
        "=" * 60
    )

    print(
        "YOUTUBE POV — PROMPT WORKER"
    )

    print(
        "=" * 60
    )

    print(
        f"[INFO] Pending moments: "
        f"{len(pending)}"
    )

    if not pending:

        print(
            "[OK] Nothing to process."
        )

        return

    template = (
        load_prompt_template()
    )

    GENERATED_PROMPT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    os.makedirs(
        CHATGPT_PROFILE_DIR,
        exist_ok=True,
    )

    # ========================================================
    # PLAYWRIGHT
    # ========================================================

    with sync_playwright() as p:

        # ====================================================
        # MOMENT LOOP
        #
        # IMPORTANT:
        #
        # NO browser exists outside this loop.
        #
        # Every moment gets a completely new Chrome context.
        # ====================================================

        for row in rows:

            if (
                row.get(
                    "status",
                    ""
                )
                .strip()
                != "pending_prompt"
            ):

                continue

            moment_id = (
                row.get(
                    "moment_id",
                    ""
                )
                .strip()
            )

            person = (
                row.get(
                    "person",
                    ""
                )
                .strip()
            )

            moment = (
                row.get(
                    "moment",
                    ""
                )
                .strip()
            )

            print()
            print(
                "=" * 60
            )

            print(
                f"[JOB] {moment_id}"
            )

            print(
                f"[PERSON] {person}"
            )

            print(
                f"[MOMENT] {moment}"
            )

            # =================================================
            # VALIDATE
            # =================================================

            if not moment_id:

                row["status"] = (
                    "prompt_error"
                )

                row["error"] = (
                    "Missing moment_id."
                )

                save_moment_queue(
                    rows
                )

                continue

            if not person:

                row["status"] = (
                    "prompt_error"
                )

                row["error"] = (
                    "Missing person."
                )

                save_moment_queue(
                    rows
                )

                continue

            if not moment:

                row["status"] = (
                    "prompt_error"
                )

                row["error"] = (
                    "Missing moment."
                )

                save_moment_queue(
                    rows
                )

                continue

            # =================================================
            # MARK PROCESSING
            # =================================================

            row["status"] = (
                "processing_prompt"
            )

            row["error"] = ""

            save_moment_queue(
                rows
            )

            success = False

            last_error = ""

            # =================================================
            # RETRY
            #
            # IMPORTANT:
            #
            # Every retry launches a NEW Chrome context.
            # =================================================

            for attempt in range(
                1,
                MAX_RETRIES + 1,
            ):

                context = None

                page = None

                try:

                    print()
                    print(
                        f"[INFO] Attempt "
                        f"{attempt}/"
                        f"{MAX_RETRIES}"
                    )

                    # =========================================
                    # START NEW BROWSER
                    # =========================================

                    (
                        context,
                        page,
                    ) = (
                        open_browser_session(
                            p
                        )
                    )

                    # =========================================
                    # PROCESS ONLY THIS MOMENT
                    # =========================================

                    result = (
                        process_moment(
                            page,
                            row,
                            template,
                        )
                    )

                    # =========================================
                    # PRINT
                    # =========================================

                    print_result(
                        row,
                        result,
                    )

                    # =========================================
                    # SAVE FILES
                    # =========================================

                    files = (
                        save_generated_prompts(
                            row,
                            result,
                        )
                    )

                    row[
                        "image_prompt_file"
                    ] = (
                        files[
                            "image_prompt_file"
                        ]
                    )

                    row[
                        "video_prompt_file"
                    ] = (
                        files[
                            "video_prompt_file"
                        ]
                    )

                    # =========================================
                    # SUCCESS STATUS
                    # =========================================

                    row["status"] = (
                        "prompts_generated"
                    )

                    row["error"] = ""

                    save_moment_queue(
                        rows
                    )

                    print()
                    print(
                        "[OK] Prompts generated."
                    )

                    success = True

                    break

                # =============================================
                # ERROR
                # =============================================

                except Exception as exc:

                    last_error = (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

                    print()
                    print(
                        "[ERROR]",
                        last_error,
                    )

                    safe_screenshot(
                        page,
                        moment_id,
                        f"attempt_{attempt}_error",
                    )

                # =============================================
                # ALWAYS CLOSE BROWSER
                # =============================================

                finally:

                    close_browser_session(
                        context
                    )

                    context = None

                    page = None

                # =============================================
                # RETRY WITH FRESH BROWSER
                # =============================================

                if (
                    not success
                    and attempt < MAX_RETRIES
                ):

                    delay = max(
                        RETRY_DELAY,
                        BROWSER_RESTART_DELAY,
                    )

                    print(
                        "[BROWSER] Failed browser "
                        "session discarded."
                    )

                    print(
                        f"[WAIT] Opening a completely "
                        f"new browser in {delay}s..."
                    )

                    time.sleep(
                        delay
                    )

            # =================================================
            # FAILED MOMENT
            # =================================================

            if not success:

                row["status"] = (
                    "prompt_error"
                )

                row["error"] = (
                    last_error
                )

                save_moment_queue(
                    rows
                )

                print(
                    f"[FAILED] "
                    f"{moment_id}"
                )

            # =================================================
            # IMPORTANT:
            #
            # Browser is already COMPLETELY CLOSED here.
            #
            # Wait before starting browser for next moment.
            # =================================================

            print()
            print(
                f"[WAIT] Browser is closed. "
                f"Next moment in "
                f"{BETWEEN_JOBS_DELAY}s..."
            )

            time.sleep(
                BETWEEN_JOBS_DELAY
            )

    print()
    print(
        "=" * 60
    )

    print(
        "[DONE] Prompt generation finished."
    )

    print(
        f"[OUTPUT] "
        f"{GENERATED_PROMPT_DIR}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    run_worker()