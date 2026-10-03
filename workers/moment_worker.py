from __future__ import annotations

import csv
import json
import os
import re
import time

from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


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
        "Could not automatically find PROJECT_ROOT."
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
    / "moment_generation"
    / "moment_generator.txt"
)

TOPIC_QUEUE_FILE = (
    PROJECT_ROOT
    / "queue"
    / "topic_queue.csv"
)

MOMENT_QUEUE_FILE = (
    PROJECT_ROOT
    / "queue"
    / "moment_queue.csv"
)

DEBUG_DIR = (
    PROJECT_ROOT
    / "debug"
    / "moment_worker"
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
# DELAYS
# ============================================================

PAGE_READY_DELAY = 5
PROMPT_READY_DELAY = 2
AFTER_SEND_DELAY = 2

OUTPUT_START_DELAY = 3
OUTPUT_END_DELAY = 2

BETWEEN_JOBS_DELAY = 6

# Give Chrome time to really release the profile.
BROWSER_RESTART_DELAY = 10

# Small delay immediately after persistent context launch.
AFTER_BROWSER_LAUNCH_DELAY = 2


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

MOMENT_END_MARKER = (
    "<END_MOMENT_JSON>"
)


# ============================================================
# MOMENT SETTINGS
# ============================================================

NUMBER_OF_FINAL_MOMENTS = 3
MINIMUM_CANDIDATES = 3


# ============================================================
# MOMENT QUEUE FIELDS
# ============================================================

MOMENT_FIELDS = [
    "moment_id",
    "topic_id",
    "person",
    "moment_order",
    "moment",
    "short_title",
    "moment_type",
    "environment",
    "visual_signature",
    "motion",
    "identity_strength",
    "visual_wow",
    "pov_strength",
    "significance",
    "hero_frame_strength",
    "uniqueness",
    "cringe_risk",
    "score",
    "is_identity_hook",
    "status",
    "created_at",
    "error",
]


# ============================================================
# LOAD PROMPT
# ============================================================

def load_prompt() -> str:

    if not PROMPT_FILE.exists():
        raise FileNotFoundError(
            "\nMoment prompt not found:\n"
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
# TOPIC QUEUE
# ============================================================

def load_topic_queue():

    if not TOPIC_QUEUE_FILE.exists():
        raise FileNotFoundError(
            "\nTopic queue not found:\n"
            f"{TOPIC_QUEUE_FILE}"
        )

    with open(
        TOPIC_QUEUE_FILE,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        return list(
            csv.DictReader(f)
        )


def save_topic_queue(rows):

    if not rows:
        return

    fieldnames = []

    for row in rows:
        for key in row.keys():

            if (
                key
                and key not in fieldnames
            ):
                fieldnames.append(key)

    if "error" not in fieldnames:
        fieldnames.append("error")

    temp_file = (
        str(TOPIC_QUEUE_FILE)
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
        writer.writerows(rows)

    os.replace(
        temp_file,
        TOPIC_QUEUE_FILE,
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
        )

        if status == "processing_moments":

            row["status"] = (
                "pending_moments"
            )

            row["error"] = ""

            changed = True

    if changed:
        save_topic_queue(rows)


# ============================================================
# MOMENT QUEUE
# ============================================================

def ensure_moment_queue():

    MOMENT_QUEUE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if MOMENT_QUEUE_FILE.exists():
        return

    with open(
        MOMENT_QUEUE_FILE,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=MOMENT_FIELDS,
        )

        writer.writeheader()


def load_moment_queue():

    ensure_moment_queue()

    with open(
        MOMENT_QUEUE_FILE,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        return list(
            csv.DictReader(f)
        )


def save_moment_queue(rows):

    ensure_moment_queue()

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
            fieldnames=MOMENT_FIELDS,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)

    os.replace(
        temp_file,
        MOMENT_QUEUE_FILE,
    )


# ============================================================
# CHECK EXISTING MOMENTS
# ============================================================

def topic_has_moments(topic_id):

    rows = load_moment_queue()

    for row in rows:

        if (
            row.get(
                "topic_id",
                ""
            ).strip()
            == topic_id
        ):
            return True

    return False


# ============================================================
# BUILD PROMPT
# ============================================================

def build_prompt(
    template,
    row,
):

    topic_id = (
        row.get(
            "topic_id",
            ""
        ).strip()
    )

    person = (
        row.get(
            "person",
            ""
        ).strip()
    )

    era = (
        row.get(
            "era",
            ""
        ).strip()
    )

    category = (
        row.get(
            "category",
            ""
        ).strip()
    )

    concept = (
        row.get(
            "concept",
            ""
        ).strip()
    )

    return (
        template
        + "\n\n"
        + "==================================================\n"
        + "INPUT\n"
        + "==================================================\n\n"
        + f"TOPIC_ID: {topic_id}\n\n"
        + f"PERSON: {person}\n\n"
        + f"ERA: {era}\n\n"
        + f"CATEGORY: {category}\n\n"
        + f"CONCEPT: {concept}\n\n"
        + "Generate exactly 10 strongest candidate moments "
        + "for THIS person.\n\n"
        + "After the complete JSON object, output this "
        + "exact marker on a new line:\n\n"
        + MOMENT_END_MARKER
    )


# ============================================================
# PAGE HEALTH
# ============================================================

def ensure_page_alive(page):

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
    topic_id,
    suffix,
):

    if page is None:
        return

    try:

        if page.is_closed():
            return

        path = (
            DEBUG_DIR
            / (
                f"{topic_id}_"
                f"{suffix}.png"
            )
        )

        # IMPORTANT:
        # Do NOT use full_page=True on a huge ChatGPT thread.
        page.screenshot(
            path=str(path),
            full_page=False,
            timeout=10_000,
        )

        print(
            "[DEBUG] Screenshot:",
            path,
        )

    except Exception as exc:

        print(
            "[DEBUG] Screenshot skipped:",
            exc,
        )


# ============================================================
# EDITOR TEXT
# ============================================================

def get_editor_text(textarea):

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
# OPEN CHATGPT PROJECT
# ============================================================

def open_project(page):

    ensure_page_alive(page)

    print(
        "[WAIT] Opening ChatGPT project..."
    )

    page.goto(
        CHATGPT_URL,
        wait_until="domcontentloaded",
        timeout=NAVIGATION_TIMEOUT,
    )

    ensure_page_alive(page)

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

    ensure_page_alive(page)

    print(
        "[OK] ChatGPT project ready."
    )


# ============================================================
# FRESH BROWSER SESSION
# ============================================================

def open_browser_session(playwright):

    print(
        "[BROWSER] Starting fresh ChatGPT context..."
    )

    context = (
        playwright.chromium
        .launch_persistent_context(

            user_data_dir=
                CHATGPT_PROFILE_DIR,

            channel="chrome",

            headless=HEADLESS,

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
        # CRITICAL CHANGE
        #
        # Chrome persistent context may restore an old tab from
        # the previous worker/session.
        #
        # NEVER reuse context.pages[0].
        #
        # Create a genuinely fresh blank page first.
        # ====================================================

        old_pages = list(
            context.pages
        )

        page = context.new_page()

        print(
            "[BROWSER] Fresh blank page created."
        )

        # Close all restored / stale pages.
        for old_page in old_pages:

            if old_page == page:
                continue

            try:
                old_page.close(
                    run_before_unload=False
                )

            except Exception:
                pass

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

        open_project(page)

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
# CLOSE SESSION
# ============================================================

def close_browser_session(context):

    if context is None:
        return

    try:

        print(
            "[BROWSER] Closing ChatGPT context..."
        )

        # Close pages explicitly first.
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

        context.close()

        print(
            "[BROWSER] Context closed."
        )

    except Exception as exc:

        print(
            "[BROWSER] Close skipped:",
            exc,
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

        ensure_page_alive(page)

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
# WAIT SUBMITTED
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

        ensure_page_alive(page)

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

    ensure_page_alive(page)

    textarea = (
        page.locator(
            "#prompt-textarea"
        )
    )

    textarea.wait_for(
        state="visible",
        timeout=PROMPT_TIMEOUT,
    )

    ensure_page_alive(page)

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

        ensure_page_alive(page)

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

        ensure_page_alive(page)

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

    ensure_page_alive(page)

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
        "[SEND] Sending moment prompt..."
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

    return count_before


# ============================================================
# WAIT RESPONSE
# ============================================================

def wait_for_response(
    page,
    count_before,
):

    ensure_page_alive(page)

    assistant_messages = (
        page.locator(
            '[data-message-author-role="assistant"]'
        )
    )

    print(
        "[WAIT] Waiting for moment output..."
    )

    appear_deadline = (
        time.time()
        + RESPONSE_TIMEOUT / 1000
    )

    # --------------------------------------------------------
    # WAIT MESSAGE APPEAR
    # --------------------------------------------------------

    while (
        time.time()
        < appear_deadline
    ):

        ensure_page_alive(page)

        try:

            if (
                assistant_messages.count()
                > count_before
            ):

                print(
                    "[OK] Output appeared."
                )

                break

        except Exception as exc:

            raise RuntimeError(
                "CHATGPT_PAGE_LOST_WAITING_RESPONSE"
            ) from exc

        time.sleep(1)

    else:

        raise TimeoutError(
            "Response did not appear."
        )

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

    # --------------------------------------------------------
    # STREAM
    # --------------------------------------------------------

    while (
        time.time()
        < finish_deadline
    ):

        ensure_page_alive(page)

        try:

            current_text = (
                assistant_messages
                .last
                .inner_text(
                    timeout=10_000
                )
                .strip()
            )

        except Exception as exc:

            raise RuntimeError(
                "CHATGPT_PAGE_LOST_DURING_STREAM"
            ) from exc

        if (
            MOMENT_END_MARKER
            in current_text
        ):

            if not marker_seen:

                print(
                    "[WAIT] End marker detected."
                )

            marker_seen = True

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

        if (
            marker_seen
            and stable_count
            >= STABLE_CHECKS_REQUIRED
        ):

            page.wait_for_timeout(
                OUTPUT_END_DELAY
                * 1000
            )

            ensure_page_alive(page)

            final_text = (
                assistant_messages
                .last
                .inner_text(
                    timeout=10_000
                )
                .strip()
            )

            final_text = (
                final_text
                .replace(
                    MOMENT_END_MARKER,
                    "",
                )
                .strip()
            )

            print(
                "[OK] Moment output finished."
            )

            return final_text

        time.sleep(
            STABLE_CHECK_INTERVAL
        )

    raise TimeoutError(
        "Moment response did not finish "
        "or end marker was not found."
    )


# ============================================================
# JSON PARSER
# ============================================================

def extract_json(
    text: str,
) -> dict[str, Any]:

    text = text.strip()

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

    # --------------------------------------------------------
    # DIRECT
    # --------------------------------------------------------

    try:

        result = json.loads(text)

        if not isinstance(
            result,
            dict,
        ):
            raise ValueError(
                "JSON root must be an object."
            )

        return result

    except json.JSONDecodeError:
        pass

    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    start = text.find("{")
    end = text.rfind("}")

    if (
        start == -1
        or end == -1
        or end <= start
    ):

        raise ValueError(
            "Could not find JSON object."
        )

    json_text = (
        text[
            start:
            end + 1
        ]
    )

    try:

        result = json.loads(
            json_text
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
        result,
        dict,
    ):
        raise ValueError(
            "JSON root must be an object."
        )

    return result


# ============================================================
# VALIDATE MOMENT
# ============================================================

def validate_moment(moment):

    required_text = [
        "moment",
        "short_title",
        "moment_type",
        "environment",
        "visual_signature",
        "motion",
    ]

    required_scores = [
        "identity_strength",
        "visual_wow",
        "pov_strength",
        "significance",
        "hero_frame_strength",
        "uniqueness",
        "cringe_risk",
    ]

    for field in required_text:

        if not (
            str(
                moment.get(
                    field,
                    ""
                )
            )
            .strip()
        ):
            return False

    try:

        for field in required_scores:

            value = float(
                moment[field]
            )

            if not (
                1 <= value <= 10
            ):
                return False

    except Exception:
        return False

    return True


# ============================================================
# SCORING
# ============================================================

def calculate_identity_score(moment):

    score = (
        float(
            moment["identity_strength"]
        ) * 0.32
        +
        float(
            moment["visual_wow"]
        ) * 0.18
        +
        float(
            moment["pov_strength"]
        ) * 0.17
        +
        float(
            moment["significance"]
        ) * 0.15
        +
        float(
            moment["hero_frame_strength"]
        ) * 0.13
        +
        float(
            moment["uniqueness"]
        ) * 0.05
        -
        float(
            moment["cringe_risk"]
        ) * 0.10
    )

    return round(
        score,
        3,
    )


def calculate_normal_score(moment):

    score = (
        float(
            moment["visual_wow"]
        ) * 0.25
        +
        float(
            moment["pov_strength"]
        ) * 0.20
        +
        float(
            moment["hero_frame_strength"]
        ) * 0.22
        +
        float(
            moment["significance"]
        ) * 0.13
        +
        float(
            moment["uniqueness"]
        ) * 0.15
        +
        float(
            moment["identity_strength"]
        ) * 0.05
        -
        float(
            moment["cringe_risk"]
        ) * 0.10
    )

    return round(
        score,
        3,
    )


# ============================================================
# DIVERSITY
# ============================================================

def normalize_words(text):

    words = re.findall(
        r"[a-z0-9]+",
        str(text).lower(),
    )

    return set(words)


def visual_similarity(
    moment_a,
    moment_b,
):

    text_a = (
        str(
            moment_a.get(
                "environment",
                ""
            )
        )
        + " "
        + str(
            moment_a.get(
                "moment_type",
                ""
            )
        )
    )

    text_b = (
        str(
            moment_b.get(
                "environment",
                ""
            )
        )
        + " "
        + str(
            moment_b.get(
                "moment_type",
                ""
            )
        )
    )

    a = normalize_words(text_a)
    b = normalize_words(text_b)

    if not a or not b:
        return 0

    union = len(
        a.union(b)
    )

    if union == 0:
        return 0

    return (
        len(
            a.intersection(b)
        )
        / union
    )


# ============================================================
# SELECT FINAL MOMENTS
# ============================================================

def select_final_moments(moments):

    valid = [
        dict(moment)
        for moment in moments
        if validate_moment(moment)
    ]

    print(
        f"[INFO] Valid candidates: "
        f"{len(valid)}"
    )

    if (
        len(valid)
        < MINIMUM_CANDIDATES
    ):
        raise RuntimeError(
            "Not enough valid candidate moments."
        )

    for moment in valid:

        moment[
            "_identity_score"
        ] = (
            calculate_identity_score(
                moment
            )
        )

        moment[
            "_normal_score"
        ] = (
            calculate_normal_score(
                moment
            )
        )

    # ========================================================
    # MOMENT 1
    # ========================================================

    moment_1 = max(
        valid,
        key=lambda item:
            item["_identity_score"],
    )

    selected = [
        moment_1
    ]

    remaining = [
        moment
        for moment in valid
        if moment is not moment_1
    ]

    # ========================================================
    # MOMENT 2+
    # ========================================================

    while (
        len(selected)
        < NUMBER_OF_FINAL_MOMENTS
        and remaining
    ):

        best = None
        best_score = None

        for candidate in remaining:

            base_score = (
                candidate[
                    "_normal_score"
                ]
            )

            max_similarity = max(
                visual_similarity(
                    candidate,
                    chosen,
                )
                for chosen in selected
            )

            diversity_penalty = (
                max_similarity
                * 2.5
            )

            final_score = (
                base_score
                - diversity_penalty
            )

            if (
                best is None
                or final_score > best_score
            ):
                best = candidate
                best_score = final_score

        if best is None:
            break

        best[
            "_selection_score"
        ] = round(
            best_score,
            3,
        )

        selected.append(best)
        remaining.remove(best)

    if (
        len(selected)
        < NUMBER_OF_FINAL_MOMENTS
    ):
        raise RuntimeError(
            "Could not select enough final moments."
        )

    return selected


# ============================================================
# SAVE SELECTED MOMENTS
# ============================================================

def append_selected_moments(
    topic_row,
    selected,
):

    rows = load_moment_queue()

    topic_id = (
        topic_row.get(
            "topic_id",
            ""
        ).strip()
    )

    person = (
        topic_row.get(
            "person",
            ""
        ).strip()
    )

    rows = [
        row
        for row in rows
        if (
            row.get(
                "topic_id",
                ""
            ).strip()
            != topic_id
        )
    ]

    for index, moment in enumerate(
        selected,
        start=1,
    ):

        moment_id = (
            f"{topic_id}_M{index:02d}"
        )

        if index == 1:

            short_title = ""
            is_identity_hook = "true"

            score = (
                moment[
                    "_identity_score"
                ]
            )

        else:

            short_title = (
                moment.get(
                    "short_title",
                    ""
                ).strip()
            )

            is_identity_hook = "false"

            score = (
                moment.get(
                    "_selection_score",
                    moment["_normal_score"],
                )
            )

        row = {
            "moment_id":
                moment_id,

            "topic_id":
                topic_id,

            "person":
                person,

            "moment_order":
                index,

            "moment":
                moment.get(
                    "moment",
                    "",
                ),

            "short_title":
                short_title,

            "moment_type":
                moment.get(
                    "moment_type",
                    "",
                ),

            "environment":
                moment.get(
                    "environment",
                    "",
                ),

            "visual_signature":
                moment.get(
                    "visual_signature",
                    "",
                ),

            "motion":
                moment.get(
                    "motion",
                    "",
                ),

            "identity_strength":
                moment.get(
                    "identity_strength",
                    "",
                ),

            "visual_wow":
                moment.get(
                    "visual_wow",
                    "",
                ),

            "pov_strength":
                moment.get(
                    "pov_strength",
                    "",
                ),

            "significance":
                moment.get(
                    "significance",
                    "",
                ),

            "hero_frame_strength":
                moment.get(
                    "hero_frame_strength",
                    "",
                ),

            "uniqueness":
                moment.get(
                    "uniqueness",
                    "",
                ),

            "cringe_risk":
                moment.get(
                    "cringe_risk",
                    "",
                ),

            "score":
                score,

            "is_identity_hook":
                is_identity_hook,

            "status":
                "pending_prompt",

            "created_at":
                datetime.now().isoformat(
                    timespec="seconds"
                ),

            "error":
                "",
        }

        rows.append(row)

    save_moment_queue(rows)


# ============================================================
# PROCESS TOPIC
# ============================================================

def process_topic(
    page,
    topic_row,
    template,
):

    ensure_page_alive(page)

    prompt = build_prompt(
        template,
        topic_row,
    )

    count_before = send_prompt(
        page,
        prompt,
    )

    response = wait_for_response(
        page,
        count_before,
    )

    parsed = extract_json(
        response
    )

    moments = parsed.get(
        "moments",
        [],
    )

    if not isinstance(
        moments,
        list,
    ):
        raise ValueError(
            "'moments' must be a list."
        )

    print(
        f"[INFO] Received "
        f"{len(moments)} "
        f"candidate moments."
    )

    return select_final_moments(
        moments
    )


# ============================================================
# PRINT SELECTED
# ============================================================

def print_selected(
    person,
    selected,
):

    print()
    print(
        "=" * 60
    )
    print(
        f"SELECTED MOMENTS — {person}"
    )
    print(
        "=" * 60
    )

    for index, moment in enumerate(
        selected,
        start=1,
    ):

        if index == 1:

            title = (
                f"POV: You are {person}"
            )

            score = (
                moment[
                    "_identity_score"
                ]
            )

        else:

            title = (
                moment[
                    "short_title"
                ]
            )

            score = (
                moment.get(
                    "_selection_score",
                    moment["_normal_score"],
                )
            )

        print()
        print(
            f"MOMENT {index}"
        )
        print(
            f"Title : {title}"
        )
        print(
            f"Moment: {moment['moment']}"
        )
        print(
            f"Visual: {moment['visual_signature']}"
        )
        print(
            f"Motion: {moment['motion']}"
        )
        print(
            f"Score : {score}"
        )


# ============================================================
# WORKER
# ============================================================

def run_worker():

    rows = load_topic_queue()

    reset_interrupted(rows)

    rows = load_topic_queue()

    pending_rows = [
        row
        for row in rows
        if (
            row.get(
                "status",
                ""
            ).strip()
            == "pending_moments"
        )
    ]

    print()
    print(
        "=" * 60
    )
    print(
        "YOUTUBE POV — MOMENT WORKER"
    )
    print(
        "=" * 60
    )

    print(
        f"[INFO] Pending topics: "
        f"{len(pending_rows)}"
    )

    if not pending_rows:

        print(
            "[OK] Nothing to process."
        )
        return

    template = load_prompt()

    ensure_moment_queue()

    os.makedirs(
        CHATGPT_PROFILE_DIR,
        exist_ok=True,
    )

    # ========================================================
    # PLAYWRIGHT
    # ========================================================

    with sync_playwright() as p:

        for topic_row in rows:

            if (
                topic_row.get(
                    "status",
                    ""
                ).strip()
                != "pending_moments"
            ):
                continue

            topic_id = (
                topic_row.get(
                    "topic_id",
                    ""
                ).strip()
            )

            person = (
                topic_row.get(
                    "person",
                    ""
                ).strip()
            )

            print()
            print(
                "=" * 60
            )
            print(
                f"[TOPIC] {topic_id}"
            )
            print(
                f"[PERSON] {person}"
            )

            # =================================================
            # VALIDATION
            # =================================================

            if not topic_id:

                topic_row[
                    "status"
                ] = "moment_error"

                topic_row[
                    "error"
                ] = "Missing topic_id."

                save_topic_queue(rows)
                continue

            if not person:

                topic_row[
                    "status"
                ] = "moment_error"

                topic_row[
                    "error"
                ] = "Missing person."

                save_topic_queue(rows)
                continue

            # =================================================
            # EXISTING
            # =================================================

            if topic_has_moments(
                topic_id
            ):

                print(
                    "[SKIP] Topic already has moments."
                )

                topic_row[
                    "status"
                ] = (
                    "moments_generated"
                )

                topic_row[
                    "error"
                ] = ""

                save_topic_queue(rows)
                continue

            # =================================================
            # PROCESSING
            # =================================================

            topic_row[
                "status"
            ] = (
                "processing_moments"
            )

            topic_row[
                "error"
            ] = ""

            save_topic_queue(rows)

            success = False
            last_error = ""

            # =================================================
            # RETRIES
            #
            # Every attempt gets:
            #
            # new persistent context
            # +
            # new blank tab
            # +
            # old restored tabs closed
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

                    (
                        context,
                        page,
                    ) = open_browser_session(
                        p
                    )

                    selected = process_topic(
                        page,
                        topic_row,
                        template,
                    )

                    print_selected(
                        person,
                        selected,
                    )

                    append_selected_moments(
                        topic_row,
                        selected,
                    )

                    topic_row[
                        "status"
                    ] = (
                        "moments_generated"
                    )

                    topic_row[
                        "error"
                    ] = ""

                    save_topic_queue(rows)

                    print()
                    print(
                        "[OK] Moments generated."
                    )

                    success = True
                    break

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
                        topic_id,
                        f"attempt_{attempt}_error",
                    )

                finally:

                    close_browser_session(
                        context
                    )

                    context = None
                    page = None

                if (
                    not success
                    and attempt < MAX_RETRIES
                ):

                    print(
                        "[BROWSER] Discarded failed session."
                    )

                    delay = max(
                        RETRY_DELAY,
                        BROWSER_RESTART_DELAY,
                    )

                    print(
                        f"[WAIT] Fresh retry in "
                        f"{delay}s..."
                    )

                    time.sleep(delay)

            # =================================================
            # FAILED
            # =================================================

            if not success:

                topic_row[
                    "status"
                ] = (
                    "moment_error"
                )

                topic_row[
                    "error"
                ] = (
                    last_error
                )

                save_topic_queue(rows)

                print(
                    f"[FAILED] {topic_id}"
                )

            # =================================================
            # NEXT TOPIC
            # =================================================

            print(
                f"[WAIT] Next topic in "
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
        "[DONE] Moment generation finished."
    )
    print(
        f"[QUEUE] {MOMENT_QUEUE_FILE}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    run_worker()