from __future__ import annotations

from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

import csv
import os
import re
import time

import pyautogui
import pyperclip


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

FLOW_URL = (
    "https://labs.google/fx/vi/tools/flow"
)


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
    / "pov_video_worker"
)


PROFILE_STATE_FILE = (
    PROJECT_ROOT
    / "flow_profile_state.txt"
)


BLOCKED_PROFILE_FILE = (
    PROJECT_ROOT
    / "flow_blocked_profiles.txt"
)


DEBUG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


GENERATED_ASSETS_ROOT.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# FLOW PROFILES
# ============================================================

FLOW_PROFILES = [
    r"C:\flow_auto_profile_01",
    r"C:\flow_auto_profile_02",
    r"C:\flow_auto_profile_03",
    r"C:\flow_auto_profile_04",
    r"C:\flow_auto_profile_05",
    r"C:\flow_auto_profile_06",
    r"C:\flow_auto_profile_07",
    r"C:\flow_auto_profile_08",
    r"C:\flow_auto_profile_09",
]


VIDEOS_PER_PROFILE = 1


# ============================================================
# SETTINGS
# ============================================================

MAX_ATTEMPTS = 3


FLOW_LOAD_WAIT = 5

AFTER_NEW_PROJECT_WAIT = 3

AFTER_TAB_WAIT = 1

AFTER_MODEL_WAIT = 1

AFTER_PLUS_WAIT = 1

AFTER_UPLOAD_MENU_WAIT = 1

AFTER_FILE_DIALOG_WAIT = 3

AFTER_IMAGE_CARD_WAIT = 2

AFTER_ADD_TO_PROMPT_WAIT = 2

AFTER_PROMPT_PASTE_WAIT = 2

AFTER_CREATE_WAIT = 5


VIDEO_CARD_WAIT_ATTEMPTS = 120

VIDEO_CARD_WAIT_INTERVAL = 2


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

    additional = [
        "video_attempts",
        "flow_profile",
        "video_file",
        "error",
    ]

    for field in additional:

        if field not in fieldnames:

            fieldnames.append(
                field
            )

    return fieldnames


def save_queue(rows):

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

def reset_interrupted(rows):

    changed = False

    for row in rows:

        if (
            row.get(
                "status",
                ""
            )
            .strip()
            .lower()
            == "processing_video"
        ):

            row["status"] = (
                "start_frame_generated"
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

    raw_path = os.path.expandvars(
        os.path.expanduser(
            raw_path
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


def read_prompt(
    prompt_file,
):

    path = resolve_project_path(
        prompt_file
    )

    if not path:

        raise FileNotFoundError(
            "video_prompt_file is empty."
        )

    if not os.path.isfile(
        path
    ):

        raise FileNotFoundError(
            f"Video prompt not found: {path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        prompt = (
            file.read()
            .strip()
        )

    if not prompt:

        raise ValueError(
            f"Video prompt is empty: {path}"
        )

    return prompt


# ============================================================
# OUTPUT PATH
# ============================================================

def get_video_output_path(
    row,
):

    topic_id = (
        row.get(
            "topic_id",
            ""
        ).strip()
    )

    moment_id = (
        row.get(
            "moment_id",
            ""
        ).strip()
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
        / "clip.mp4"
    )


# ============================================================
# PROFILE MANAGEMENT
# ============================================================

def get_blocked_profiles():

    if not BLOCKED_PROFILE_FILE.exists():

        return set()

    today = (
        datetime.now()
        .date()
        .isoformat()
    )

    legacy_is_today = (
        datetime.fromtimestamp(
            BLOCKED_PROFILE_FILE
            .stat()
            .st_mtime
        )
        .date()
        == datetime.now().date()
    )

    blocked = set()

    with open(
        BLOCKED_PROFILE_FILE,
        "r",
        encoding="utf-8",
    ) as file:

        for raw_line in file:

            line = raw_line.strip()

            if not line:
                continue

            if "|" in line:

                (
                    profile_dir,
                    blocked_date,
                ) = line.rsplit(
                    "|",
                    1,
                )

                if (
                    blocked_date
                    == today
                ):

                    blocked.add(
                        profile_dir
                    )

            elif legacy_is_today:

                blocked.add(
                    line
                )

    return blocked


def add_blocked_profile(
    profile_dir,
):

    if (
        profile_dir
        in get_blocked_profiles()
    ):
        return

    today = (
        datetime.now()
        .date()
        .isoformat()
    )

    with open(
        BLOCKED_PROFILE_FILE,
        "a",
        encoding="utf-8",
    ) as file:

        file.write(
            f"{profile_dir}|{today}\n"
        )


def get_job_index():

    if not PROFILE_STATE_FILE.exists():

        return 0

    value = (
        PROFILE_STATE_FILE
        .read_text(
            encoding="utf-8"
        )
        .strip()
    )

    if value.isdigit():

        return int(
            value
        )

    return 0


def save_job_index(
    index,
):

    PROFILE_STATE_FILE.write_text(
        str(
            index
        ),
        encoding="utf-8",
    )


def get_next_profile():

    blocked_profiles = (
        get_blocked_profiles()
    )

    job_index = (
        get_job_index()
    )

    for _ in range(
        len(
            FLOW_PROFILES
        )
    ):

        profile_index = (
            job_index
            // VIDEOS_PER_PROFILE
        ) % len(
            FLOW_PROFILES
        )

        profile_dir = (
            FLOW_PROFILES[
                profile_index
            ]
        )

        if (
            profile_dir
            not in blocked_profiles
        ):

            save_job_index(
                job_index + 1
            )

            return (
                profile_dir,
                profile_index + 1,
            )

        job_index += (
            VIDEOS_PER_PROFILE
        )

    raise Exception(
        "All Flow profiles are blocked."
    )


# ============================================================
# POPUP
# ============================================================

def dismiss_possible_ad_overlay(
    page,
):

    try:

        print(
            "Trying close popup..."
        )

        page.mouse.click(
            1880,
            500,
        )

        time.sleep(
            2
        )

        print(
            "Popup area cleared"
        )

    except Exception as error:

        print(
            "Popup clear skipped:",
            error,
        )


# ============================================================
# FLOW CREDITS
# ============================================================

def get_flow_credits(
    page,
):

    print(
        "Checking Google Flow credits..."
    )

    avatar_button = (
        page.locator(
            'button:has('
            'img[alt="User profile image"]'
            ')'
        )
        .first
    )

    try:

        avatar_button.wait_for(
            state="visible",
            timeout=15000,
        )

    except Exception:

        avatar_button = (
            page.locator(
                "button.sc-112fdb2-7"
            )
            .first
        )

        avatar_button.wait_for(
            state="visible",
            timeout=10000,
        )

    avatar_button.click(
        force=True
    )

    print(
        "Clicked avatar button"
    )

    credit_locator = (
        page.locator(
            'a[href*="flow_ai_credits_page"]'
        )
        .first
    )

    credit_locator.wait_for(
        state="visible",
        timeout=15000,
    )

    text = (
        credit_locator
        .inner_text()
        .strip()
    )

    print(
        f"Credits text: {text}"
    )

    match = re.search(
        r"([\d.,]+)\s+Google Flow credits",
        text,
        re.IGNORECASE,
    )

    if not match:

        match = re.search(
            r"[\d.,]+",
            text,
        )

    if not match:

        raise Exception(
            "FLOW_CREDITS_NOT_FOUND: "
            f"{text}"
        )

    credits_text = (
        match.group(1)
        if match.lastindex
        else match.group(0)
    )

    credits = int(
        re.sub(
            r"\D",
            "",
            credits_text,
        )
    )

    if credits > 0:

        close_button = (
            page.locator(
                'button[aria-label="Close this modal"]'
            )
        )

        try:

            if (
                close_button.count() > 0
                and
                close_button.first.is_visible()
            ):

                close_button.first.click(
                    force=True
                )

                print(
                    "Closed avatar menu"
                )

            else:

                page.keyboard.press(
                    "Escape"
                )

        except Exception as error:

            print(
                "Close avatar menu skipped:",
                error,
            )

    return credits


# ============================================================
# SELECT TAB HELPER
# ============================================================

def click_tab_if_needed(
    locator,
    label,
):

    locator.wait_for(
        state="visible",
        timeout=30000,
    )

    selected = (
        locator.get_attribute(
            "aria-selected"
        )
        == "true"
    )

    active = (
        locator.get_attribute(
            "data-state"
        )
        == "active"
    )

    if (
        selected
        or active
    ):

        print(
            f"{label} already selected"
        )

        return

    locator.click(
        force=True
    )

    print(
        f"Selected {label}"
    )


# ============================================================
# SETUP NEW PROJECT
# ============================================================

def setup_new_project(
    page,
):
    """
    FLOW:

    New project
    → Video
    → 9:16
    → model dropdown
    → Omni Flash
    → 4s
    → x1
    """

    # ========================================================
    # NEW PROJECT
    # Không phụ thuộc English / Vietnamese
    # Chỉ click 1 lần
    # ========================================================

    # ========================================================
    # NEW PROJECT
    # Chỉ click 1 lần
    # Không phụ thuộc ngôn ngữ
    # ========================================================

    new_project_button = (
        page.locator(
            "button.sc-a38764c7-0"
        )
        .first
    )

    try:
        new_project_button.wait_for(
            state="visible",
            timeout=30000,
        )

        print(
            "Found New project / Dự án mới button"
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "new_project_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "New project / Dự án mới button not found."
        ) from error

    new_project_button.scroll_into_view_if_needed()

    time.sleep(1)

    new_project_button.click(
        force=True
    )

    print(
        "Clicked New project / Dự án mới"
    )

    time.sleep(
        AFTER_NEW_PROJECT_WAIT
    )

    # ========================================================
    # OPEN VIDEO SETTINGS
    #
    # HTML user inspect:
    # button.sc-93abd9dc-1
    # Ví dụ hiển thị:
    # Video · 4s   9:16   x1
    #
    # Không dùng radix ID vì ID thay đổi theo session.
    # ========================================================

    video_settings_button = (
        page.locator(
            "button.sc-93abd9dc-1"
        )
        .first
    )

    try:

        video_settings_button.wait_for(
            state="visible",
            timeout=30000,
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "video_settings_button_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "Video settings button not found."
        ) from error

    video_settings_button.scroll_into_view_if_needed()

    time.sleep(1)

    video_settings_button.click(
        force=True
    )

    print(
        "Clicked Video settings button"
    )

    time.sleep(
        AFTER_TAB_WAIT
    )

    # ========================================================
    # VIDEO
    # ========================================================

    video_tab = (
        page.locator(
            "button[role='tab']"
            "[aria-controls$='content-VIDEO']"
        )
        .first
    )

    try:

        click_tab_if_needed(
            video_tab,
            "Video",
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "video_tab_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "Video tab not found."
        ) from error

    time.sleep(
        AFTER_TAB_WAIT
    )

    # ========================================================
    # THÀNH PHẦN / VIDEO REFERENCES
    # ========================================================

    component_tab = (
        page.locator(
            "button[role='tab']"
            "[aria-controls$='content-VIDEO_REFERENCES']"
        )
        .first
    )

    try:

        click_tab_if_needed(
            component_tab,
            "Thành phần",
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "video_references_tab_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "Thành phần / VIDEO_REFERENCES tab not found."
        ) from error

    time.sleep(
        AFTER_TAB_WAIT
    )

    # ========================================================
    # 9:16
    #
    # HTML:
    # aria-controls ends content-PORTRAIT
    # icon crop_9_16
    # ========================================================

    portrait_tab = (
        page.locator(
            "button[role='tab']"
            "[aria-controls$='content-PORTRAIT']"
        )
        .filter(
            has_text="9:16"
        )
        .first
    )

    try:

        click_tab_if_needed(
            portrait_tab,
            "9:16",
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "portrait_9_16_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "9:16 button not found."
        ) from error

    time.sleep(
        AFTER_TAB_WAIT
    )

    # ========================================================
    # MODEL DROPDOWN
    #
    # Current HTML still includes:
    # sc-3f41cc92-1
    # ========================================================

    model_dropdown = (
        page.locator(
            "button.sc-3f41cc92-1"
        )
        .first
    )

    try:

        model_dropdown.wait_for(
            state="visible",
            timeout=30000,
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "model_dropdown_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "Model dropdown not found."
        ) from error

    model_dropdown.click(
        force=True
    )

    print(
        "Opened model dropdown"
    )

    time.sleep(
        AFTER_MODEL_WAIT
    )

    # ========================================================
    # OMNI FLASH
    #
    # HTML:
    # button.sc-3f41cc92-3
    # span text Omni Flash
    # ========================================================

    omni_flash_button = (
        page.locator(
            "button.sc-3f41cc92-3"
        )
        .filter(
            has_text="Omni Flash"
        )
        .first
    )

    try:

        omni_flash_button.wait_for(
            state="visible",
            timeout=30000,
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "omni_flash_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "Omni Flash model not found."
        ) from error

    omni_flash_button.click(
        force=True
    )

    print(
        "Selected Omni Flash"
    )

    time.sleep(
        AFTER_MODEL_WAIT
    )

    # ========================================================
    # 4s
    #
    # ID radix dynamic -> DO NOT USE.
    #
    # HTML text is exactly 4s.
    # ========================================================

    duration_tab = (
        page.locator(
            "button[role='tab']"
            ".flow_tab_slider_trigger"
        )
        .filter(
            has_text="4s"
        )
        .first
    )

    try:

        click_tab_if_needed(
            duration_tab,
            "4s",
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "duration_4s_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "4s button not found."
        ) from error

    time.sleep(
        AFTER_TAB_WAIT
    )

    # ========================================================
    # x1
    # ========================================================

    x1_tab = (
        page.locator(
            "button[role='tab']"
            ".flow_tab_slider_trigger"
        )
        .filter(
            has_text="x1"
        )
        .first
    )

    try:

        click_tab_if_needed(
            x1_tab,
            "x1",
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "x1_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "x1 button not found."
        ) from error

    time.sleep(
        AFTER_TAB_WAIT
    )


# ============================================================
# WAIT IMAGE CARDS
# ============================================================

def wait_image_cards_stable(
    page,
    expected_count,
    timeout_rounds=180,
):

    last_count = -1

    stable_rounds = 0

    for _ in range(
        timeout_rounds
    ):

        cards = page.locator(
            "div[role='option']"
        )

        count = (
            cards.count()
        )

        print(
            f"Image cards: "
            f"{count}/{expected_count}"
        )

        if (
            count
            >= expected_count
        ):

            if (
                count
                == last_count
            ):

                stable_rounds += 1

            else:

                stable_rounds = 0

            last_count = count

            if (
                stable_rounds
                >= 3
            ):

                print(
                    "Image cards stable."
                )

                return

        else:

            stable_rounds = 0
            last_count = count

        time.sleep(
            2
        )

    page.screenshot(
        path=str(
            DEBUG_DIR
            / "upload_timeout.png"
        ),
        full_page=True,
    )

    raise Exception(
        f"Upload timeout. "
        f"Expected {expected_count}, "
        f"got {last_count}"
    )


# ============================================================
# CLICK IMAGE CARD
# ============================================================

def click_image_card(
    page,
    filename,
):

    card = page.locator(
        f"div[role='option']"
        f":has(img[alt*='{filename}'])"
    ).first

    try:

        card.wait_for(
            state="visible",
            timeout=30000,
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "image_card_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "Image card not found: "
            f"{filename}"
        ) from error

    card.scroll_into_view_if_needed()

    time.sleep(
        0.5
    )

    box = (
        card.bounding_box()
    )

    if not box:

        raise RuntimeError(
            "Cannot get image-card bounding box."
        )

    page.mouse.click(
        (
            box["x"]
            + box["width"] / 2
        ),
        (
            box["y"]
            + box["height"] / 2
        ),
    )

    print(
        "Clicked image card:",
        filename,
    )

    time.sleep(
        AFTER_IMAGE_CARD_WAIT
    )


# ============================================================
# UPLOAD START IMAGE
# ============================================================

def upload_start_image(
    page,
    image_path,
):
    """
    FLOW MỚI:

    dấu +
    → Upload media
    → Windows dialog
    → upload start image
    → chờ image card
    """

    image_path = os.path.abspath(
        image_path
    )

    if not os.path.isfile(
        image_path
    ):

        raise FileNotFoundError(
            f"Missing start image: {image_path}"
        )

    image_dir = (
        os.path.dirname(
            image_path
        )
    )

    image_name = (
        os.path.basename(
            image_path
        )
    )

    before_count = (
        page.locator(
            "div[role='option']"
        )
        .count()
    )

    # ========================================================
    # PLUS BUTTON
    #
    # HTML:
    # button
    # aria-haspopup=dialog
    # icon add_2
    # hidden text Create
    # ========================================================

    plus_button = (
        page.locator(
            "button.sc-253cad92-0"
        )
        .first
    )

    try:

        plus_button.wait_for(
            state="visible",
            timeout=30000,
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "plus_button_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "Plus button not found."
        ) from error

    plus_button.click(
        force=True
    )

    print(
        "Clicked +"
    )

    time.sleep(
        AFTER_PLUS_WAIT
    )

    # ========================================================
    # UPLOAD MEDIA
    #
    # HTML:
    # button.sc-559b4cd2-4
    # icon upload
    # text Upload media
    # ========================================================

    upload_button = (
        page.locator(
            "button.sc-559b4cd2-4"
        )
        .first
    )

    try:

        upload_button.wait_for(
            state="visible",
            timeout=30000,
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "upload_media_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "Upload media button not found."
        ) from error

    upload_button.click(
        force=True
    )

    print(
        "Clicked Upload media"
    )

    time.sleep(
        AFTER_UPLOAD_MENU_WAIT
    )

    # ========================================================
    # WINDOWS FILE DIALOG
    # ========================================================

    pyperclip.copy(
        image_dir
    )

    pyautogui.hotkey(
        "ctrl",
        "l",
    )

    time.sleep(
        0.5
    )

    pyautogui.hotkey(
        "ctrl",
        "v",
    )

    time.sleep(
        0.5
    )

    pyautogui.press(
        "enter"
    )

    time.sleep(
        2
    )

    pyperclip.copy(
        image_name
    )

    pyautogui.hotkey(
        "alt",
        "n",
    )

    time.sleep(
        0.5
    )

    pyautogui.hotkey(
        "ctrl",
        "v",
    )

    time.sleep(
        0.5
    )

    pyautogui.press(
        "enter"
    )

    print(
        "Uploading:",
        image_name,
    )

    time.sleep(
        AFTER_FILE_DIALOG_WAIT
    )

    # ========================================================
    # WAIT UPLOAD
    # ========================================================

    wait_image_cards_stable(
        page,
        expected_count=
            before_count + 1,
    )

    print(
        "Image upload completed."
    )

    return image_name


# ============================================================
# ADD IMAGE TO PROMPT
# ============================================================

def add_image_to_prompt(
    page,
    image_name,
):
    """
    Chọn image card
    → Add to Prompt
    """

    click_image_card(
        page,
        image_name,
    )

    # HTML:
    # button.sc-64c4dea-4
    # text Add to Prompt
    add_to_prompt_button = (
        page.locator(
            "button.sc-64c4dea-4"
        )
        .first
    )

    try:

        add_to_prompt_button.wait_for(
            state="visible",
            timeout=1000,
        )

        add_to_prompt_button.click(
            force=True
        )

        print(
            "Clicked Add to Prompt"
        )

        time.sleep(
            AFTER_ADD_TO_PROMPT_WAIT
        )

    except Exception:

        print(
            "Add to Prompt button not found - skipping."
        )

# ============================================================
# PASTE PROMPT
# ============================================================

def paste_video_prompt(
    page,
    prompt_text,
):

    # HTML user inspect:
    #
    # div
    # role=textbox
    # aria-multiline=true
    # data-slate-editor=true
    # contenteditable=true
    prompt_box = (
        page.locator(
            "div[role='textbox']"
            "[aria-multiline='true']"
            "[data-slate-editor='true']"
            "[contenteditable='true']"
        )
        .first
    )

    try:

        prompt_box.wait_for(
            state="visible",
            timeout=30000,
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "prompt_box_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "Prompt box not found."
        ) from error

    prompt_box.click(
        force=True
    )

    time.sleep(
        1
    )

    pyperclip.copy(
        prompt_text
    )

    pyautogui.hotkey(
        "ctrl",
        "v",
    )

    print(
        "Pasted video prompt"
    )

    time.sleep(
        AFTER_PROMPT_PASTE_WAIT
    )


# ============================================================
# CLICK CREATE
# ============================================================

def click_create(
    page,
):

    # HTML:
    #
    # button aria-disabled=false
    # icon arrow_forward
    # hidden span Create
    create_button = (
        page.locator(
            "button[aria-disabled]"
            ":has(i.google-symbols:text-is('arrow_forward'))"
        )
        .first
    )

    try:

        create_button.wait_for(
            state="visible",
            timeout=30000,
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "create_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "Create button not found."
        ) from error

    start_time = time.time()

    while True:

        aria_disabled = (
            create_button.get_attribute(
                "aria-disabled"
            )
        )

        try:

            enabled = (
                create_button.is_enabled()
            )

        except Exception:

            enabled = False

        if (
                aria_disabled != "true"
                and enabled
        ):
            break

        if (
                time.time()
                - start_time
                > 60
        ):
            page.screenshot(
                path=str(
                    DEBUG_DIR
                    / "create_disabled.png"
                ),
                full_page=True,
            )

            raise TimeoutError(
                "Create button remained disabled > 60 seconds."
            )

        print(
            "Waiting Create button..."
        )

        time.sleep(
            2
        )

    create_button.click(
        force=True
    )

    print(
        "Clicked Create"
    )

    time.sleep(
        AFTER_CREATE_WAIT
    )


# ============================================================
# CREATE POV CLIP
# ============================================================

def create_clip(
    page,
    start_image,
    prompt_text,
):

    print()
    print(
        "--- Creating POV clip ---"
    )

    image_name = (
        upload_start_image(
            page,
            start_image,
        )
    )

    add_image_to_prompt(
        page,
        image_name,
    )

    paste_video_prompt(
        page,
        prompt_text,
    )

    click_create(
        page
    )


# ============================================================
# VIEW VIDEOS
# ============================================================

def click_view_videos(
    page,
):
    """
    HTML:

    button
    icon videocam
    hidden text View videos
    """

    video_button = (
        page.locator(
            "button"
            ":has(i.google-symbols:text-is('videocam'))"
        )
        .first
    )

    try:

        video_button.wait_for(
            state="visible",
            timeout=30000,
        )

    except Exception as error:

        page.screenshot(
            path=str(
                DEBUG_DIR
                / "view_videos_not_found.png"
            ),
            full_page=True,
        )

        raise RuntimeError(
            "View videos button not found."
        ) from error

    video_button.click(
        force=True
    )

    print(
        "Clicked View videos"
    )

    time.sleep(
        3
    )


# ============================================================
# DOWNLOAD VIDEO CARD
# ============================================================

def wait_and_download_video_card(
    page,
    card_index,
    save_path,
):

    video_cards = page.locator(
        "div[data-tile-id]"
    )

    count = (
        video_cards.count()
    )

    print(
        f"Found {count} video cards. "
        f"Targeting index {card_index}."
    )

    card = (
        video_cards.nth(
            card_index
        )
    )

    card.scroll_into_view_if_needed()

    time.sleep(
        0.5
    )

    box = (
        card.bounding_box()
    )

    if not box:

        raise Exception(
            f"Cannot get bounding box "
            f"of video card {card_index}"
        )

    cx = (
        box["x"]
        + box["width"] / 2
    )

    cy = (
        box["y"]
        + box["height"] / 2
    )

    print(
        f"Waiting video card "
        f"{card_index} ready..."
    )

    for attempt in range(
        VIDEO_CARD_WAIT_ATTEMPTS
    ):

        page.mouse.move(
            cx,
            cy,
        )

        time.sleep(
            VIDEO_CARD_WAIT_INTERVAL
        )

        ready = page.evaluate(
            f"""
            () => {{
                const cards =
                    document.querySelectorAll(
                        'div[data-tile-id]'
                    );

                const card =
                    cards[{card_index}];

                if (!card) return false;

                const video =
                    card.querySelector(
                        'video'
                    );

                if (!video) return false;

                return (
                    video.src
                    && video.src.includes(
                        'media.getMediaUrlRedirect'
                    )
                );
            }}
            """
        )

        if ready:

            print(
                f"Video card "
                f"{card_index} ready."
            )

            break

        print(
            f"  waiting... "
            f"{attempt + 1}/"
            f"{VIDEO_CARD_WAIT_ATTEMPTS}"
        )

    else:

        raise Exception(
            f"Timeout waiting for "
            f"video card {card_index}"
        )

    time.sleep(
        1
    )

    page.mouse.move(
        cx,
        cy,
    )

    time.sleep(
        1
    )

    page.mouse.click(
        cx,
        cy,
        button="right",
    )

    print(
        f"Right clicked video "
        f"card {card_index}"
    )

    time.sleep(
        2
    )

    # Giữ selector download từ worker cũ.
    page.locator(
        "div.sc-d5e0baee-5"
    ).filter(
        has_text="Tải xuống"
    ).click(
        force=True
    )

    print(
        "Clicked Tải xuống"
    )

    time.sleep(
        2
    )

    os.makedirs(
        os.path.dirname(
            save_path
        ),
        exist_ok=True,
    )

    with page.expect_download(
        timeout=180000,
    ) as dl_info:

        page.locator(
            "button.sc-d5e0baee-7"
        ).filter(
            has_text="720p"
        ).click(
            force=True
        )

    download = (
        dl_info.value
    )

    download.save_as(
        save_path
    )

    if not os.path.isfile(
        save_path
    ):

        raise FileNotFoundError(
            "Download completed but "
            "video file was not found: "
            f"{save_path}"
        )

    print(
        "Saved:",
        save_path,
    )


# ============================================================
# RENDER SINGLE MOMENT
# ============================================================

def render_single_moment(
    moment_id,
    start_image,
    prompt_text,
    save_path,
):

    print(
        "=" * 60
    )

    print(
        "Rendering POV moment:",
        moment_id,
    )

    with sync_playwright() as p:

        while True:

            try:

                (
                    profile_dir,
                    profile_number,
                ) = get_next_profile()

            except Exception as error:

                if (
                    str(error)
                    == "All Flow profiles are blocked."
                ):

                    raise Exception(
                        "NO_FLOW_CREDITS_AVAILABLE"
                    ) from error

                raise

            print(
                f"Profile: {profile_number} "
                f"| {profile_dir}"
            )

            browser = (
                p.chromium
                .launch_persistent_context(
                    user_data_dir=
                        profile_dir,

                    headless=False,

                    channel="chrome",

                    accept_downloads=True,

                    args=[
                        "--window-size=1900,1000",
                        "--window-position=0,0",
                    ],
                )
            )

            try:

                page = (
                    browser.new_page()
                )

                page.goto(
                    FLOW_URL,
                    wait_until=
                        "domcontentloaded",
                    timeout=120000,
                )

                print(
                    "Waiting Google Flow load..."
                )

                time.sleep(
                    FLOW_LOAD_WAIT
                )

                # =================================================
                # GIỮ NGUYÊN POPUP LOGIC
                # =================================================

                dismiss_possible_ad_overlay(
                    page
                )

                # =================================================
                # GIỮ NGUYÊN CREDIT LOGIC
                # =================================================

                credits = (
                    get_flow_credits(
                        page
                    )
                )

                print(
                    f"Google Flow credits: "
                    f"{credits}"
                )

                if credits == 0:

                    print(
                        "Profile has 0 credits, "
                        "switching profile:",
                        profile_dir,
                    )

                    add_blocked_profile(
                        profile_dir
                    )

                    page.screenshot(
                        path=str(
                            DEBUG_DIR
                            / (
                                "zero_credits_"
                                f"profile_{profile_number}.png"
                            )
                        ),
                        full_page=True,
                    )

                    continue

                # =================================================
                # SETUP
                # =================================================

                setup_new_project(
                    page
                )

                # =================================================
                # CREATE
                # =================================================

                create_clip(
                    page=page,
                    start_image=
                        start_image,
                    prompt_text=
                        prompt_text,
                )

                # =================================================
                # UNUSUAL ACTIVITY
                # =================================================

                page_text = (
                    page.locator(
                        "body"
                    )
                    .inner_text()
                    .lower()
                )

                if (
                    "unusual activity"
                    in page_text
                    or
                    "hoạt động bất thường"
                    in page_text
                ):

                    print(
                        "Detected unusual activity:",
                        profile_dir,
                    )

                    add_blocked_profile(
                        profile_dir
                    )

                    page.screenshot(
                        path=str(
                            DEBUG_DIR
                            / (
                                "unusual_activity_"
                                f"{moment_id}.png"
                            )
                        ),
                        full_page=True,
                    )

                    raise Exception(
                        "UNUSUAL_ACTIVITY"
                    )

                # =================================================
                # VIEW VIDEOS
                # =================================================

                click_view_videos(
                    page
                )

                total_cards = (
                    page.locator(
                        "div[data-tile-id]"
                    )
                    .count()
                )

                print(
                    f"Total video cards: "
                    f"{total_cards}"
                )

                if (
                    total_cards <= 0
                ):

                    raise Exception(
                        "No video cards found "
                        "after generation."
                    )

                # =================================================
                # DOWNLOAD LAST CARD
                # =================================================

                wait_and_download_video_card(
                    page,
                    card_index=
                        total_cards - 1,
                    save_path=
                        save_path,
                )

                print(
                    "Moment downloaded:",
                    save_path,
                )

                return profile_dir

            finally:

                browser.close()


# ============================================================
# PENDING JOBS
# ============================================================

def get_pending_jobs(
    rows,
):

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
            == "start_frame_generated"
        )
    ]

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

    rows = (
        load_queue()
    )

    reset_interrupted(
        rows
    )

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

            print(
                "=" * 60
            )

            print(
                "No pending POV video jobs left."
            )

            break

        job = (
            pending_jobs[0]
        )

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

        moment = (
            job.get(
                "moment",
                ""
            )
            .strip()
        )

        start_image = (
            resolve_project_path(
                job.get(
                    "start_frame_file",
                    ""
                )
            )
        )

        video_prompt_file = (
            resolve_project_path(
                job.get(
                    "video_prompt_file",
                    ""
                )
            )
        )

        save_path = str(
            get_video_output_path(
                job
            )
        )

        print(
            "=" * 60
        )

        print(
            "Next POV video job:",
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
            "Start image:",
            start_image,
        )

        print(
            "Video prompt:",
            video_prompt_file,
        )

        print(
            "Output:",
            save_path,
        )

        try:

            attempts = int(
                job.get(
                    "video_attempts",
                    ""
                )
                or 0
            )

        except ValueError:

            attempts = 0

        update_job(
            moment_id,
            status=
                "processing_video",
            error="",
        )

        try:

            if not moment_id:

                raise ValueError(
                    "Missing moment_id."
                )

            if not os.path.isfile(
                start_image
            ):

                raise FileNotFoundError(
                    "Missing start image: "
                    f"{start_image}"
                )

            if not os.path.isfile(
                video_prompt_file
            ):

                raise FileNotFoundError(
                    "Missing video prompt: "
                    f"{video_prompt_file}"
                )

            prompt_text = (
                read_prompt(
                    video_prompt_file
                )
            )

            profile_dir = (
                render_single_moment(
                    moment_id=
                        moment_id,
                    start_image=
                        start_image,
                    prompt_text=
                        prompt_text,
                    save_path=
                        save_path,
                )
            )

            update_job(
                moment_id,

                status=
                    "clip_generated",

                video_attempts=
                    str(
                        attempts + 1
                    ),

                flow_profile=
                    profile_dir,

                video_file=
                    save_path,

                error="",
            )

            print(
                "POV video job done:",
                moment_id,
            )

        except Exception as error:

            error_text = str(
                error
            )

            print(
                "POV video job failed:",
                moment_id,
            )

            print(
                "Error:",
                error_text,
            )

            if (
                error_text
                == "NO_FLOW_CREDITS_AVAILABLE"
            ):

                update_job(
                    moment_id,

                    status=
                        "start_frame_generated",

                    video_attempts=
                        str(
                            attempts
                        ),

                    error=(
                        "All Flow profiles "
                        "have 0 credits today."
                    ),
                )

                print(
                    "All profiles have 0 credits today."
                )

                print(
                    "Stopping POV video batch."
                )

                break

            attempts += 1

            if (
                error_text
                == "UNUSUAL_ACTIVITY"
            ):

                next_status = (
                    "start_frame_generated"
                )

            elif (
                attempts
                >= MAX_ATTEMPTS
            ):

                next_status = (
                    "clip_failed"
                )

            else:

                next_status = (
                    "start_frame_generated"
                )

            update_job(
                moment_id,

                status=
                    next_status,

                video_attempts=
                    str(
                        attempts
                    ),

                error=
                    error_text,
            )

            time.sleep(
                5
            )

    print(
        "=" * 60
    )

    print(
        "POV video batch finished."
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    main()