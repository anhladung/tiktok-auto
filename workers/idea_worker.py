from __future__ import annotations

import csv
import json
import os
import re
import time

from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import (
    sync_playwright,
)


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)


PROMPT_FILE = (
    PROJECT_ROOT
    / "prompts"
    / "youtube"
    / "pov"
    / "idea_generation"
    / "idea_generator.txt"
)


QUEUE_FILE = (
    PROJECT_ROOT
    / "queue"
    / "topic_queue.csv"
)


HISTORY_FILE = (
    PROJECT_ROOT
    / "data"
    / "idea_history.json"
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

PROMPT_TIMEOUT = 30_000

PROMPT_LOAD_TIMEOUT = 15_000

SEND_CONFIRM_TIMEOUT = 15_000

RESPONSE_TIMEOUT = 180_000


# ------------------------------------------------------------
# WAIT / BUFFER
# ------------------------------------------------------------

PAGE_READY_DELAY = 3

PROMPT_READY_DELAY = 2

AFTER_SEND_DELAY = 2

OUTPUT_START_DELAY = 3

OUTPUT_END_DELAY = 2


# ------------------------------------------------------------
# RESPONSE STABILITY
# ------------------------------------------------------------

STABLE_CHECK_INTERVAL = 2

STABLE_CHECKS_REQUIRED = 3


# ------------------------------------------------------------
# FINAL RESPONSE MARKER
# ------------------------------------------------------------

IDEA_END_MARKER = (
    "<END_IDEA_JSON>"
)


# ------------------------------------------------------------
# NUMBER OF TOPICS SELECTED EACH RUN
# ------------------------------------------------------------

NUMBER_OF_FINAL_TOPICS = 1


# ============================================================
# QUEUE FIELDS
# ============================================================

QUEUE_HEADERS = [
    "topic_id",
    "person",
    "era",
    "category",
    "concept",
    "score",
    "status",
    "created_at",
]


# ============================================================
# LOAD PROMPT
# ============================================================

def load_prompt() -> str:

    if not PROMPT_FILE.exists():

        raise FileNotFoundError(
            "\nPrompt file not found:\n"
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
# HISTORY
# ============================================================

def load_history() -> list[dict]:

    if not HISTORY_FILE.exists():
        return []

    try:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        if isinstance(
            data,
            list,
        ):
            return data

        return []

    except Exception:

        return []


def save_history(
    history: list[dict],
) -> None:

    HISTORY_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_file = (
        str(HISTORY_FILE)
        + ".tmp"
    )

    with open(
        temp_file,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            history,
            f,
            indent=2,
            ensure_ascii=False,
        )

    os.replace(
        temp_file,
        HISTORY_FILE,
    )


def get_used_people(
    history: list[dict],
) -> set[str]:

    used = set()

    for item in history:

        person = (
            item
            .get(
                "person",
                "",
            )
            .strip()
            .lower()
        )

        if person:
            used.add(
                person
            )

    return used


# ============================================================
# BUILD PROMPT
# ============================================================

def build_prompt(
    history: list[dict],
) -> str:

    base_prompt = (
        load_prompt()
    )

    recent = (
        history[-50:]
    )

    used_people = [
        item.get(
            "person",
            "",
        ).strip()
        for item in recent
        if item.get(
            "person",
            ""
        ).strip()
    ]

    if not used_people:

        return (
            base_prompt
            + "\n\n"
            + "After the complete JSON object, "
            + "output this exact marker on a new line:\n\n"
            + IDEA_END_MARKER
        )

    avoid_block = (
        "\n\n"
        "==================================================\n"
        "RECENTLY USED PEOPLE\n"
        "==================================================\n\n"
        "Do NOT select or closely repeat these people:\n\n"
    )

    avoid_block += "\n".join(
        f"- {person}"
        for person
        in used_people
    )

    avoid_block += (
        "\n\n"
        "After the complete JSON object, "
        "output this exact marker on a new line:\n\n"
        + IDEA_END_MARKER
    )

    return (
        base_prompt
        + avoid_block
    )


# ============================================================
# EDITOR HELPERS
# ============================================================

def get_editor_text(
    textarea,
):

    try:

        text = (
            textarea.evaluate(
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
        )

        return (
            text or ""
        ).strip()

    except Exception:

        return ""


# ============================================================
# OPEN CHATGPT PROJECT
# ============================================================

def open_project(
    page,
):

    print(
        "[WAIT] Opening ChatGPT project..."
    )

    page.goto(
        CHATGPT_URL,
        wait_until="domcontentloaded",
        timeout=NAVIGATION_TIMEOUT,
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
# WAIT FOR PROMPT LOAD
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
                "[OK] Prompt loaded into editor."
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
        + SEND_CONFIRM_TIMEOUT / 1000
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

        # Editor cleared.
        if not editor_text:
            return

        # Assistant already started output.
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
# SEND PROMPT
# ============================================================

def send_prompt(
    page,
    prompt,
):

    textarea = (
        page.locator(
            "#prompt-textarea"
        )
    )

    textarea.wait_for(
        state="visible",
        timeout=PROMPT_TIMEOUT,
    )

    textarea.click()

    # --------------------------------------------------------
    # CLEAR
    # --------------------------------------------------------

    try:

        textarea.fill(
            ""
        )

    except Exception:

        textarea.click()

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

        textarea.click()

        page.keyboard.insert_text(
            prompt
        )

    # --------------------------------------------------------
    # VERIFY
    # --------------------------------------------------------

    wait_for_prompt_loaded(
        textarea,
        prompt,
    )

    # --------------------------------------------------------
    # BUFFER
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
    # CONFIRM
    # --------------------------------------------------------

    wait_for_prompt_submitted(
        textarea,
        assistant_messages,
        count_before,
    )

    print(
        "[OK] Prompt submitted."
    )

    print(
        f"[WAIT] Waiting "
        f"{AFTER_SEND_DELAY}s "
        f"after submission..."
    )

    page.wait_for_timeout(
        AFTER_SEND_DELAY
        * 1000
    )

    return (
        count_before
    )


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
    # STEP 1
    # WAIT FOR NEW MESSAGE
    # ========================================================

    print(
        "[WAIT] Waiting for idea output..."
    )

    appear_deadline = (
        time.time()
        + RESPONSE_TIMEOUT / 1000
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
    # STEP 2
    # LET STREAM START
    # ========================================================

    print(
        f"[WAIT] Letting output start "
        f"for {OUTPUT_START_DELAY}s..."
    )

    page.wait_for_timeout(
        OUTPUT_START_DELAY
        * 1000
    )

    # ========================================================
    # STEP 3
    # WAIT FOR MARKER + STABILITY
    # ========================================================

    finish_deadline = (
        time.time()
        + RESPONSE_TIMEOUT / 1000
    )

    previous_text = ""

    stable_count = 0

    marker_seen = False

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
        # MARKER
        # ----------------------------------------------------

        if (
            IDEA_END_MARKER
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
        # FINISH
        # ----------------------------------------------------

        if (
            marker_seen
            and stable_count
            >= STABLE_CHECKS_REQUIRED
        ):

            print(
                "[OK] Idea output finished."
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

            final_text = (
                final_text
                .replace(
                    IDEA_END_MARKER,
                    "",
                )
                .strip()
            )

            return (
                final_text
            )

        time.sleep(
            STABLE_CHECK_INTERVAL
        )

    raise TimeoutError(
        "Idea response did not finish "
        "or end marker was not found."
    )


# ============================================================
# ASK CHATGPT
# ============================================================

def ask_chatgpt(
    prompt: str,
) -> str:

    os.makedirs(
        CHATGPT_PROFILE_DIR,
        exist_ok=True,
    )

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

        try:

            if context.pages:

                page = (
                    context.pages[0]
                )

            else:

                page = (
                    context.new_page()
                )

            open_project(
                page
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

            return (
                response
            )

        finally:

            context.close()


# ============================================================
# JSON PARSER
# ============================================================

def extract_json(
    text: str,
) -> dict[str, Any]:

    text = (
        text.strip()
    )

    # Remove code fences if ChatGPT ignores instruction.
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
    # DIRECT JSON
    # --------------------------------------------------------

    try:

        result = (
            json.loads(
                text
            )
        )

        if not isinstance(
            result,
            dict,
        ):

            raise ValueError(
                "JSON root is not an object."
            )

        return (
            result
        )

    except json.JSONDecodeError:
        pass

    # --------------------------------------------------------
    # FALLBACK
    # FIND OUTERMOST OBJECT
    # --------------------------------------------------------

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
            "Could not find JSON object."
        )

    json_text = (
        text[
            start:
            end + 1
        ]
    )

    try:

        result = (
            json.loads(
                json_text
            )
        )

    except json.JSONDecodeError as exc:

        print()
        print(
            "[DEBUG] JSON TEXT"
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
            "JSON root is not an object."
        )

    return (
        result
    )


# ============================================================
# VALIDATE CANDIDATE
# ============================================================

def validate_candidate(
    candidate: dict,
) -> bool:

    required_fields = [
        "person",
        "recognizability",
        "moment_strength",
        "pov_visual",
        "visual_diversity",
        "wow_factor",
        "cringe_risk",
        "repetition_risk",
    ]

    for field in required_fields:

        if field not in candidate:
            return False

    person = (
        str(
            candidate.get(
                "person",
                ""
            )
        )
        .strip()
    )

    if not person:
        return False

    numeric_fields = [
        "recognizability",
        "moment_strength",
        "pov_visual",
        "visual_diversity",
        "wow_factor",
        "cringe_risk",
        "repetition_risk",
    ]

    try:

        for field in numeric_fields:

            value = float(
                candidate[field]
            )

            if not (
                1
                <= value
                <= 10
            ):

                return False

    except Exception:

        return False

    return True


# ============================================================
# SCORE
# ============================================================

def calculate_score(
    candidate: dict,
) -> float:

    recognizability = float(
        candidate[
            "recognizability"
        ]
    )

    moment_strength = float(
        candidate[
            "moment_strength"
        ]
    )

    pov_visual = float(
        candidate[
            "pov_visual"
        ]
    )

    visual_diversity = float(
        candidate[
            "visual_diversity"
        ]
    )

    wow_factor = float(
        candidate[
            "wow_factor"
        ]
    )

    cringe_risk = float(
        candidate[
            "cringe_risk"
        ]
    )

    repetition_risk = float(
        candidate[
            "repetition_risk"
        ]
    )

    # --------------------------------------------------------
    # POSITIVE SCORE
    # --------------------------------------------------------

    positive = (
        wow_factor
        * 0.25

        + pov_visual
        * 0.25

        + moment_strength
        * 0.20

        + recognizability
        * 0.15

        + visual_diversity
        * 0.15
    )

    # --------------------------------------------------------
    # PENALTIES
    # --------------------------------------------------------

    penalty = (
        cringe_risk
        * 0.12

        + repetition_risk
        * 0.08
    )

    score = (
        positive
        - penalty
    )

    return round(
        score,
        3,
    )


# ============================================================
# FILTER + RANK
# ============================================================

def filter_candidates(
    candidates: list[dict],
    used_people: set[str],
) -> list[dict]:

    results = []

    for candidate in candidates:

        if not validate_candidate(
            candidate
        ):
            continue

        person = (
            candidate[
                "person"
            ]
            .strip()
        )

        # ----------------------------------------------------
        # DUPLICATE
        # ----------------------------------------------------

        if (
            person.lower()
            in used_people
        ):
            continue

        # ----------------------------------------------------
        # HARD QUALITY FILTERS
        # ----------------------------------------------------

        if (
            float(
                candidate[
                    "wow_factor"
                ]
            )
            < 7
        ):
            continue

        if (
            float(
                candidate[
                    "pov_visual"
                ]
            )
            < 7
        ):
            continue

        if (
            float(
                candidate[
                    "moment_strength"
                ]
            )
            < 7
        ):
            continue

        if (
            float(
                candidate[
                    "cringe_risk"
                ]
            )
            > 6
        ):
            continue

        candidate[
            "score"
        ] = (
            calculate_score(
                candidate
            )
        )

        results.append(
            candidate
        )

    results.sort(
        key=lambda x:
            x[
                "score"
            ],
        reverse=True,
    )

    return (
        results
    )


# ============================================================
# QUEUE
# ============================================================

def ensure_queue():

    QUEUE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if QUEUE_FILE.exists():
        return

    with open(
        QUEUE_FILE,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = (
            csv.DictWriter(
                f,
                fieldnames=
                    QUEUE_HEADERS,
            )
        )

        writer.writeheader()


def get_next_topic_number() -> int:

    ensure_queue()

    highest = 0

    with open(
        QUEUE_FILE,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = (
            csv.DictReader(
                f
            )
        )

        for row in reader:

            topic_id = (
                row.get(
                    "topic_id",
                    ""
                )
                .strip()
            )

            match = (
                re.fullmatch(
                    r"YT(\d+)",
                    topic_id,
                )
            )

            if not match:
                continue

            number = int(
                match.group(
                    1
                )
            )

            highest = max(
                highest,
                number,
            )

    return (
        highest + 1
    )


def add_to_queue(
    candidate: dict,
    topic_number: int,
) -> str:

    ensure_queue()

    topic_id = (
        f"YT{topic_number:05d}"
    )

    row = {

        "topic_id":
            topic_id,

        "person":
            candidate.get(
                "person",
                "",
            ),

        "era":
            candidate.get(
                "era",
                "",
            ),

        "category":
            candidate.get(
                "category",
                "",
            ),

        "concept":
            candidate.get(
                "concept",
                "",
            ),

        "score":
            candidate.get(
                "score",
                "",
            ),

        "status":
            "pending_moments",

        "created_at":
            datetime.now()
            .isoformat(
                timespec="seconds"
            ),
    }

    with open(
        QUEUE_FILE,
        "a",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = (
            csv.DictWriter(
                f,
                fieldnames=
                    QUEUE_HEADERS,
            )
        )

        writer.writerow(
            row
        )

    return (
        topic_id
    )


# ============================================================
# MAIN
# ============================================================

def run():

    print()
    print(
        "=" * 60
    )

    print(
        "YOUTUBE POV — IDEA ENGINE"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # LOAD HISTORY
    # --------------------------------------------------------

    history = (
        load_history()
    )

    used_people = (
        get_used_people(
            history
        )
    )

    # --------------------------------------------------------
    # BUILD PROMPT
    # --------------------------------------------------------

    prompt = (
        build_prompt(
            history
        )
    )

    # --------------------------------------------------------
    # GENERATE
    # --------------------------------------------------------

    print()
    print(
        "[1/4] Generating candidate ideas..."
    )

    raw_response = (
        ask_chatgpt(
            prompt
        )
    )

    # --------------------------------------------------------
    # PARSE
    # --------------------------------------------------------

    print()
    print(
        "[2/4] Parsing response..."
    )

    result = (
        extract_json(
            raw_response
        )
    )

    candidates = (
        result.get(
            "candidates",
            []
        )
    )

    if not isinstance(
        candidates,
        list,
    ):

        raise ValueError(
            "'candidates' must be a list."
        )

    print(
        f"      Received "
        f"{len(candidates)} "
        f"candidates."
    )

    # --------------------------------------------------------
    # RANK
    # --------------------------------------------------------

    print()
    print(
        "[3/4] Ranking ideas..."
    )

    ranked = (
        filter_candidates(
            candidates,
            used_people,
        )
    )

    if not ranked:

        raise RuntimeError(
            "No candidate passed "
            "the quality filters."
        )

    print()
    print(
        "TOP IDEAS"
    )

    print(
        "-" * 60
    )

    for (
        index,
        candidate,
    ) in enumerate(
        ranked[:10],
        start=1,
    ):

        person = (
            candidate[
                "person"
            ]
        )

        score = (
            candidate[
                "score"
            ]
        )

        category = (
            candidate.get(
                "category",
                ""
            )
        )

        print(
            f"{index:02d}. "
            f"{person:<30} "
            f"{score:>6.3f} "
            f"[{category}]"
        )

    # --------------------------------------------------------
    # SELECT WINNER
    # --------------------------------------------------------

    print()
    print(
        "[4/4] Adding winner to queue..."
    )

    topic_number = (
        get_next_topic_number()
    )

    winners = (
        ranked[
            :NUMBER_OF_FINAL_TOPICS
        ]
    )

    for winner in winners:

        topic_id = (
            add_to_queue(
                winner,
                topic_number,
            )
        )

        topic_number += 1

        history.append(
            {
                "topic_id":
                    topic_id,

                "person":
                    winner[
                        "person"
                    ],

                "era":
                    winner.get(
                        "era",
                        "",
                    ),

                "category":
                    winner.get(
                        "category",
                        "",
                    ),

                "score":
                    winner[
                        "score"
                    ],

                "created_at":
                    datetime.now()
                    .isoformat(
                        timespec="seconds"
                    ),
            }
        )

        print()
        print(
            "=" * 60
        )

        print(
            f"WINNER : "
            f"{winner['person']}"
        )

        print(
            f"ERA    : "
            f"{winner.get('era', '')}"
        )

        print(
            f"TYPE   : "
            f"{winner.get('category', '')}"
        )

        print(
            f"SCORE  : "
            f"{winner['score']}"
        )

        print(
            f"ID     : "
            f"{topic_id}"
        )

        print(
            "=" * 60
        )

    # --------------------------------------------------------
    # SAVE HISTORY
    # --------------------------------------------------------

    save_history(
        history
    )

    print()
    print(
        "[DONE] Idea generation finished."
    )

    print(
        f"[QUEUE] {QUEUE_FILE}"
    )

    print()


# ============================================================
# MAIN ENTRY
# ============================================================

if __name__ == "__main__":
    run()