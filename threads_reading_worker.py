import csv
import json
import os
import time

from playwright.sync_api import (
    sync_playwright,
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

QUEUE_FILE = os.path.join(
    BASE_DIR,
    "queue",
    "threads_reading_queue.csv",
)

ARCHETYPES_FILE = os.path.join(
    BASE_DIR,
    "data",
    "threads",
    "archetypes.json",
)

PROMPT_FILE = os.path.join(
    BASE_DIR,
    "prompts",
    "threads",
    "reading_generation.txt",
)

CHATGPT_PROFILE_DIR = (
    r"C:\chatgpt_auto_profile"
)


# ============================================================
# CHATGPT
# ============================================================

CHATGPT_URL = (
    "https://chatgpt.com/"
    "g/g-p-6a59ccfe43208191a8a880795664b046/project"
)


# ============================================================
# SETTINGS
# ============================================================

HEADLESS = False

NAVIGATION_TIMEOUT = 60_000

PROMPT_TIMEOUT = 30_000

PROMPT_LOAD_TIMEOUT = 15_000

SEND_CONFIRM_TIMEOUT = 15_000

RESPONSE_TIMEOUT = 120_000


# ------------------------------------------------------------
# EXTRA WAIT / BUFFER
# ------------------------------------------------------------

# Sau khi trang load + textarea xuất hiện
PAGE_READY_DELAY = 3

# Sau khi prompt đã được điền đầy đủ
PROMPT_READY_DELAY = 2

# Sau khi Enter gửi prompt
AFTER_SEND_DELAY = 2

# Sau khi assistant bắt đầu xuất hiện output
OUTPUT_START_DELAY = 3

# Sau khi output đã được xác định là hoàn tất
OUTPUT_END_DELAY = 2

# Nghỉ giữa các job
BETWEEN_JOBS_DELAY = 3


# ------------------------------------------------------------
# RESPONSE STABILITY
# ------------------------------------------------------------

STABLE_CHECK_INTERVAL = 2

STABLE_CHECKS_REQUIRED = 3

# Marker cuối cùng mà prompt yêu cầu ChatGPT trả về.
RESPONSE_END_MARKER = "</REPLY_3>"


# ------------------------------------------------------------
# RETRY
# ------------------------------------------------------------

MAX_RETRIES = 2

RETRY_DELAY = 5


# ============================================================
# CSV FIELDS
# ============================================================

FIELDNAMES = [
    "reading_job_id",
    "created_at",

    "reading_type",

    "personalization_type",
    "personalization_value",

    "archetype_1",
    "archetype_2",
    "archetype_3",

    "status",

    "post_text",

    "reply_1",
    "reply_2",
    "reply_3",

    "error",
]


# ============================================================
# LOAD FILES
# ============================================================

def load_prompt():
    if not os.path.exists(
        PROMPT_FILE
    ):
        raise FileNotFoundError(
            PROMPT_FILE
        )

    with open(
        PROMPT_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        return f.read().strip()


def load_archetypes():
    if not os.path.exists(
        ARCHETYPES_FILE
    ):
        raise FileNotFoundError(
            ARCHETYPES_FILE
        )

    with open(
        ARCHETYPES_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def load_queue():
    if not os.path.exists(
        QUEUE_FILE
    ):
        raise FileNotFoundError(
            QUEUE_FILE
        )

    with open(
        QUEUE_FILE,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return list(
            csv.DictReader(f)
        )


def save_queue(rows):
    temp_file = (
        QUEUE_FILE
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
            fieldnames=FIELDNAMES,
            extrasaction="ignore",
        )

        writer.writeheader()

        writer.writerows(
            rows
        )

    os.replace(
        temp_file,
        QUEUE_FILE,
    )


# ============================================================
# RESET INTERRUPTED
# ============================================================

def reset_interrupted(rows):
    changed = False

    for row in rows:

        if row.get(
            "status",
            ""
        ).strip() == "processing":

            row["status"] = (
                "pending"
            )

            row["error"] = ""

            changed = True

    if changed:

        save_queue(
            rows
        )


# ============================================================
# ARCHETYPE TEXT
# ============================================================

def get_archetype_text(
    archetypes,
    name,
):

    if not name:
        return ""

    data = archetypes.get(
        name,
        {}
    )

    themes = data.get(
        "themes",
        []
    )

    return (
        f"{name}: "
        + ", ".join(themes)
    )


# ============================================================
# BUILD PROMPT
# ============================================================

def build_prompt(
    template,
    row,
    archetypes,
):

    # --------------------------------------------------------
    # READING TYPE
    # --------------------------------------------------------

    reading_type = row.get(
        "reading_type",
        ""
    ).strip()

    # --------------------------------------------------------
    # PERSONALIZATION
    # --------------------------------------------------------

    personalization_type = row.get(
        "personalization_type",
        ""
    ).strip()

    personalization_value = row.get(
        "personalization_value",
        ""
    ).strip()

    # --------------------------------------------------------
    # ARCHETYPES
    # --------------------------------------------------------

    a1 = row.get(
        "archetype_1",
        ""
    ).strip()

    a2 = row.get(
        "archetype_2",
        ""
    ).strip()

    a3 = row.get(
        "archetype_3",
        ""
    ).strip()

    # --------------------------------------------------------
    # PROMPT
    # --------------------------------------------------------

    return (
        template
        + "\n\n"

        + "========================================\n"
        + "INPUT\n"
        + "========================================\n\n"

        + f"READING_TYPE: "
        + f"{reading_type}\n\n"

        + f"PERSONALIZATION_TYPE: "
        + f"{personalization_type}\n\n"

        + f"PERSONALIZATION_VALUE: "
        + f"{personalization_value}\n\n"

        + "ARCHETYPE_1:\n"
        + get_archetype_text(
            archetypes,
            a1,
        )

        + "\n\n"

        + "ARCHETYPE_2:\n"
        + get_archetype_text(
            archetypes,
            a2,
        )

        + "\n\n"

        + "ARCHETYPE_3:\n"
        + get_archetype_text(
            archetypes,
            a3,
        )

        + "\n"
    )


# ============================================================
# RESPONSE PARSER
# ============================================================

def extract_section(
    text,
    start_marker,
    end_marker,
):

    start = text.find(
        start_marker
    )

    if start == -1:
        return ""

    start += len(
        start_marker
    )

    end = text.find(
        end_marker,
        start,
    )

    if end == -1:
        return ""

    return text[
        start:end
    ].strip()


def parse_response(text):
    text = text.strip()

    post_text = extract_section(
        text,
        "<POST_TEXT>",
        "</POST_TEXT>",
    )

    reply_1 = extract_section(
        text,
        "<REPLY_1>",
        "</REPLY_1>",
    )

    reply_2 = extract_section(
        text,
        "<REPLY_2>",
        "</REPLY_2>",
    )

    reply_3 = extract_section(
        text,
        "<REPLY_3>",
        "</REPLY_3>",
    )

    if not post_text:

        print()
        print(
            "[DEBUG] Raw response:"
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
            "Missing POST_TEXT."
        )

    return {
        "post_text":
            post_text,

        "reply_1":
            reply_1,

        "reply_2":
            reply_2,

        "reply_3":
            reply_3,
    }


# ============================================================
# EDITOR HELPERS
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
# CHATGPT - OPEN PROJECT
# ============================================================

def open_project(
    page,
):

    print(
        "[WAIT] Opening ChatGPT project..."
    )

    page.goto(
        CHATGPT_URL,
        wait_until=
            "domcontentloaded",
        timeout=
            NAVIGATION_TIMEOUT,
    )

    # --------------------------------------------------------
    # WAIT FOR PROMPT AREA
    # --------------------------------------------------------

    textarea = page.locator(
        "#prompt-textarea"
    )

    textarea.wait_for(
        state="visible",
        timeout=PROMPT_TIMEOUT,
    )

    print(
        "[WAIT] Prompt area visible."
    )

    # --------------------------------------------------------
    # EXTRA UI BUFFER
    # --------------------------------------------------------

    print(
        f"[WAIT] Page settling "
        f"{PAGE_READY_DELAY}s..."
    )

    page.wait_for_timeout(
        PAGE_READY_DELAY
        * 1000
    )

    print(
        "[OK] ChatGPT project ready."
    )


# ============================================================
# WAIT UNTIL PROMPT IS REALLY FILLED
# ============================================================

def wait_for_prompt_loaded(
    textarea,
    prompt,
):

    print(
        "[WAIT] Checking prompt content..."
    )

    deadline = (
        time.time()
        + (
            PROMPT_LOAD_TIMEOUT
            / 1000
        )
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
                "[OK] Prompt loaded "
                "into editor."
            )

            return

        time.sleep(
            0.5
        )

    raise TimeoutError(
        "Prompt did not finish "
        "loading into editor."
    )


# ============================================================
# WAIT FOR SUBMISSION CONFIRMATION
# ============================================================

def wait_for_prompt_submitted(
    textarea,
    assistant_messages,
    count_before,
):

    deadline = (
        time.time()
        + (
            SEND_CONFIRM_TIMEOUT
            / 1000
        )
    )

    while (
        time.time()
        < deadline
    ):

        editor_text = (
            get_editor_text(
                textarea
            )
        )

        assistant_count = (
            assistant_messages.count()
        )

        # Editor đã clear = prompt gửi thành công.
        if not editor_text:
            return

        # Hoặc assistant đã bắt đầu trả lời.
        if (
            assistant_count
            > count_before
        ):
            return

        time.sleep(
            0.5
        )

    raise TimeoutError(
        "Could not confirm "
        "prompt submission."
    )


# ============================================================
# CHATGPT - SEND PROMPT
# ============================================================

def send_prompt(
    page,
    prompt,
):

    textarea = page.locator(
        "#prompt-textarea"
    )

    textarea.wait_for(
        state="visible",
        timeout=PROMPT_TIMEOUT,
    )

    textarea.click()

    # --------------------------------------------------------
    # CLEAR OLD TEXT
    # --------------------------------------------------------

    try:

        textarea.fill("")

    except Exception:

        textarea.click()

        page.keyboard.press(
            "Control+A"
        )

        page.keyboard.press(
            "Backspace"
        )

    # --------------------------------------------------------
    # FILL PROMPT
    # --------------------------------------------------------

    print(
        "[WAIT] Filling prompt..."
    )

    try:

        textarea.fill(
            prompt
        )

    except Exception:

        textarea.click()

        page.keyboard.insert_text(
            prompt
        )

    # --------------------------------------------------------
    # VERIFY PROMPT LOADED
    # --------------------------------------------------------

    wait_for_prompt_loaded(
        textarea,
        prompt,
    )

    # --------------------------------------------------------
    # BUFFER BEFORE SEND
    # --------------------------------------------------------

    print(
        f"[WAIT] Prompt settling "
        f"{PROMPT_READY_DELAY}s..."
    )

    page.wait_for_timeout(
        PROMPT_READY_DELAY
        * 1000
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
        "[SEND] Sending prompt..."
    )

    page.keyboard.press(
        "Enter"
    )

    # --------------------------------------------------------
    # CONFIRM SEND
    # --------------------------------------------------------

    wait_for_prompt_submitted(
        textarea,
        assistant_messages,
        count_before,
    )

    print(
        "[OK] Prompt submitted."
    )

    # --------------------------------------------------------
    # BUFFER AFTER SEND
    # --------------------------------------------------------

    print(
        f"[WAIT] Waiting "
        f"{AFTER_SEND_DELAY}s "
        f"after submission..."
    )

    page.wait_for_timeout(
        AFTER_SEND_DELAY
        * 1000
    )

    return count_before


# ============================================================
# WAIT FOR RESPONSE
# ============================================================

def wait_for_response(
    page,
    count_before,
):

    assistant_messages = (
        page.locator(
            '[data-message-author-role="assistant"]'
        )
    )

    # ========================================================
    # STEP 1 - WAIT FOR OUTPUT
    # ========================================================

    print(
        "[WAIT] Waiting for output..."
    )

    appear_deadline = (
        time.time()
        + (
            RESPONSE_TIMEOUT
            / 1000
        )
    )

    while (
        time.time()
        < appear_deadline
    ):

        current_count = (
            assistant_messages.count()
        )

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
    # STEP 2 - LET STREAM START
    # ========================================================

    print(
        f"[WAIT] Letting output start "
        f"for {OUTPUT_START_DELAY}s..."
    )

    page.wait_for_timeout(
        OUTPUT_START_DELAY
        * 1000
    )

    finish_deadline = (
        time.time()
        + (
            RESPONSE_TIMEOUT
            / 1000
        )
    )

    previous_text = ""

    stable_count = 0

    marker_seen = False

    # ========================================================
    # STEP 3 - WAIT UNTIL COMPLETE
    # ========================================================

    while (
        time.time()
        < finish_deadline
    ):

        current_text = (
            assistant_messages
            .last
            .inner_text()
            .strip()
        )

        # ----------------------------------------------------
        # END MARKER
        # ----------------------------------------------------

        if (
            RESPONSE_END_MARKER
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

            print(
                "[OK] Output finished."
            )

            page.wait_for_timeout(
                OUTPUT_END_DELAY
                * 1000
            )

            final_text = (
                assistant_messages
                .last
                .inner_text()
                .strip()
            )

            return final_text

        time.sleep(
            STABLE_CHECK_INTERVAL
        )

    raise TimeoutError(
        "Response did not finish "
        "or final marker was not found."
    )


# ============================================================
# PROCESS JOB
# ============================================================

def process_job(
    page,
    row,
    template,
    archetypes,
):

    prompt = build_prompt(
        template,
        row,
        archetypes,
    )

    # --------------------------------------------------------
    # OPEN PROJECT
    # --------------------------------------------------------

    open_project(
        page
    )

    # --------------------------------------------------------
    # SEND PROMPT
    # --------------------------------------------------------

    count_before = send_prompt(
        page,
        prompt,
    )

    # --------------------------------------------------------
    # WAIT RESPONSE
    # --------------------------------------------------------

    response = wait_for_response(
        page,
        count_before,
    )

    # --------------------------------------------------------
    # PARSE
    # --------------------------------------------------------

    return parse_response(
        response
    )


# ============================================================
# WORKER
# ============================================================

def run_worker():

    rows = load_queue()

    reset_interrupted(
        rows
    )

    rows = load_queue()

    pending_count = sum(
        1
        for row in rows
        if row.get(
            "status",
            ""
        ).strip()
        == "pending"
    )

    print()
    print(
        "=" * 60
    )

    print(
        f"[INFO] Pending: "
        f"{pending_count}"
    )

    if pending_count == 0:

        print(
            "[OK] Nothing to process."
        )

        return

    template = (
        load_prompt()
    )

    archetypes = (
        load_archetypes()
    )

    os.makedirs(
        CHATGPT_PROFILE_DIR,
        exist_ok=True,
    )

    # ========================================================
    # PLAYWRIGHT
    # ========================================================

    with sync_playwright() as p:

        context = (
            p.chromium
            .launch_persistent_context(
                user_data_dir=
                    CHATGPT_PROFILE_DIR,

                channel=
                    "chrome",

                headless=
                    HEADLESS,

                viewport={
                    "width":
                        1440,

                    "height":
                        1000,
                },
            )
        )

        if context.pages:

            page = (
                context.pages[0]
            )

        else:

            page = (
                context.new_page()
            )

        # ====================================================
        # JOB LOOP
        # ====================================================

        for row in rows:

            if row.get(
                "status",
                ""
            ).strip() != "pending":

                continue

            job_id = row.get(
                "reading_job_id",
                ""
            ).strip()

            reading_type = row.get(
                "reading_type",
                ""
            ).strip()

            personalization_type = row.get(
                "personalization_type",
                ""
            ).strip()

            personalization_value = row.get(
                "personalization_value",
                ""
            ).strip()

            archetype_1 = row.get(
                "archetype_1",
                ""
            ).strip()

            print()
            print(
                "=" * 60
            )

            print(
                f"[JOB] "
                f"{job_id}"
            )

            print(
                f"[TYPE] "
                f"{reading_type}"
            )

            print(
                f"[PERSONALIZATION TYPE] "
                f"{personalization_type}"
            )

            print(
                f"[PERSONALIZATION] "
                f"{personalization_value}"
            )

            print(
                f"[ARCHETYPE] "
                f"{archetype_1}"
            )

            # ------------------------------------------------
            # VALIDATE
            # ------------------------------------------------

            if not personalization_value:

                row["status"] = (
                    "error"
                )

                row["error"] = (
                    "Missing personalization_value."
                )

                save_queue(
                    rows
                )

                print(
                    "[FAILED] Missing "
                    "personalization_value."
                )

                continue

            # ------------------------------------------------
            # MARK PROCESSING
            # ------------------------------------------------

            row["status"] = (
                "processing"
            )

            row["error"] = ""

            save_queue(
                rows
            )

            success = False

            last_error = ""

            # =================================================
            # RETRY LOOP
            # =================================================

            for attempt in range(
                1,
                MAX_RETRIES + 1,
            ):

                try:

                    print(
                        f"[INFO] Attempt "
                        f"{attempt}/"
                        f"{MAX_RETRIES}"
                    )

                    result = (
                        process_job(
                            page,
                            row,
                            template,
                            archetypes,
                        )
                    )

                    # -----------------------------------------
                    # SAVE OUTPUT
                    # -----------------------------------------

                    row["post_text"] = (
                        result[
                            "post_text"
                        ]
                    )

                    row["reply_1"] = (
                        result[
                            "reply_1"
                        ]
                    )

                    row["reply_2"] = (
                        result[
                            "reply_2"
                        ]
                    )

                    row["reply_3"] = (
                        result[
                            "reply_3"
                        ]
                    )

                    row["status"] = (
                        "generated"
                    )

                    row["error"] = ""

                    save_queue(
                        rows
                    )

                    print(
                        "[OK] Reading generated."
                    )

                    print()
                    print(
                        "[POST]"
                    )

                    print(
                        row[
                            "post_text"
                        ]
                    )

                    success = True

                    break

                except Exception as exc:

                    last_error = (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

                    print(
                        f"[ERROR] "
                        f"{last_error}"
                    )

                    # -----------------------------------------
                    # RETRY
                    # -----------------------------------------

                    if (
                        attempt
                        < MAX_RETRIES
                    ):

                        print(
                            f"[WAIT] Retry in "
                            f"{RETRY_DELAY}s..."
                        )

                        time.sleep(
                            RETRY_DELAY
                        )

            # =================================================
            # JOB FAILED
            # =================================================

            if not success:

                row["status"] = (
                    "error"
                )

                row["error"] = (
                    last_error
                )

                save_queue(
                    rows
                )

                print(
                    f"[FAILED] "
                    f"{job_id}"
                )

            # =================================================
            # BETWEEN JOBS
            # =================================================

            print(
                f"[WAIT] Next job in "
                f"{BETWEEN_JOBS_DELAY}s..."
            )

            time.sleep(
                BETWEEN_JOBS_DELAY
            )

        context.close()

    print()
    print(
        "=" * 60
    )

    print(
        "[DONE] Reading generation finished."
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    run_worker()