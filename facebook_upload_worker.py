import csv
import json
import os
import random
import time
from datetime import datetime

from playwright.sync_api import sync_playwright


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

QUEUE_DIR = os.path.join(
    BASE_DIR,
    "queue"
)

FACEBOOK_QUEUE_FILE = os.path.join(
    QUEUE_DIR,
    "facebook_queue.csv"
)

FACEBOOK_SCHEDULE_FILE = os.path.join(
    QUEUE_DIR,
    "facebook_schedule.csv"
)

FACEBOOK_PROFILE_DIR = (
    r"C:\facebook_auto_profile_01"
)

FACEBOOK_PAGE_URL = (
    "https://www.facebook.com/"
    "beautymemochannel/"
)

CAPTION_DIR = os.path.join(
    BASE_DIR,
    "assets",
    "captions"
)

CAPTION_FILES = {
    "lipstick": os.path.join(
        CAPTION_DIR,
        "lipstick.json"
    ),

    "sandal": os.path.join(
        CAPTION_DIR,
        "sandal.json"
    ),
}

SCREENSHOT_DIR = os.path.join(
    BASE_DIR,
    "screenshots"
)


# ============================================================
# FACEBOOK QUEUE COLUMNS
# ============================================================

FACEBOOK_QUEUE_FIELDNAMES = [
    "job_id",
    "category",
    "product_id",
    "media_path",
    "caption",
    "status",
    "attempts",
    "error",
    "updated_at",
]


# ============================================================
# FACEBOOK SCHEDULE COLUMNS
# ============================================================

FACEBOOK_SCHEDULE_FIELDNAMES = [
    "schedule_id",
    "scheduled_date",
    "scheduled_time",
    "day_name",
    "status",
    "job_id",
    "category",
    "product_id",
    "error",
]


# ============================================================
# CSV
# ============================================================

def load_csv(path):
    if not os.path.exists(path):
        return []

    with open(
        path,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        return list(
            csv.DictReader(f)
        )


def save_csv(
    path,
    rows,
    fieldnames
):
    with open(
        path,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(rows)


# ============================================================
# CAPTION
# ============================================================

def load_caption(category):
    category = str(
        category or ""
    ).strip().lower()

    caption_file = CAPTION_FILES.get(
        category
    )

    if not caption_file:
        raise ValueError(
            f"Không có file caption cho category: "
            f"{category}"
        )

    if not os.path.exists(
        caption_file
    ):
        raise FileNotFoundError(
            caption_file
        )

    with open(
        caption_file,
        "r",
        encoding="utf-8"
    ) as f:
        templates = json.load(f)

    if not isinstance(
        templates,
        list
    ):
        raise ValueError(
            f"{os.path.basename(caption_file)} "
            f"phải là JSON array."
        )

    valid_templates = []

    for item in templates:
        if not isinstance(
            item,
            dict
        ):
            continue

        caption = str(
            item.get(
                "caption",
                ""
            )
        ).strip()

        hashtags = item.get(
            "hashtags",
            []
        )

        if not isinstance(
            hashtags,
            list
        ):
            hashtags = []

        hashtags = [
            str(tag).strip()
            for tag in hashtags
            if str(tag).strip()
        ]

        if caption:
            valid_templates.append({
                "caption": caption,
                "hashtags": hashtags,
            })

    if not valid_templates:
        raise ValueError(
            f"Không có caption hợp lệ trong: "
            f"{caption_file}"
        )

    template = random.choice(
        valid_templates
    )

    caption = template[
        "caption"
    ]

    hashtags = " ".join(
        template["hashtags"]
    )

    print(
        "Caption category:",
        category
    )

    print(
        "Caption file:",
        caption_file
    )

    if hashtags:
        return (
            f"{caption}\n\n"
            f"{hashtags}"
        )

    return caption


# ============================================================
# QUEUE HELPERS
# ============================================================

def get_pending_jobs(rows):
    pending_jobs = []

    for row in rows:
        status = row.get(
            "status",
            ""
        ).strip().lower()

        if status == "pending":
            pending_jobs.append(
                row
            )

    return pending_jobs


def update_queue_status(
    rows,
    job_id,
    status,
    error=""
):
    for row in rows:
        if row.get(
            "job_id"
        ) != job_id:
            continue

        row["status"] = status
        row["error"] = error

        row["updated_at"] = (
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        break


def increase_attempts(
    rows,
    job_id
):
    for row in rows:
        if row.get(
            "job_id"
        ) != job_id:
            continue

        try:
            attempts = int(
                row.get(
                    "attempts",
                    "0"
                ) or 0
            )

        except ValueError:
            attempts = 0

        row["attempts"] = str(
            attempts + 1
        )

        break


# ============================================================
# SCHEDULE
# ============================================================

def get_pending_schedule(rows):
    pending_rows = []

    for row in rows:
        status = row.get(
            "status",
            ""
        ).strip().lower()

        if status != "pending":
            continue

        scheduled_date = row.get(
            "scheduled_date",
            ""
        ).strip()

        scheduled_time = row.get(
            "scheduled_time",
            ""
        ).strip()

        if (
            not scheduled_date
            or not scheduled_time
        ):
            continue

        schedule_datetime = (
            datetime.strptime(
                f"{scheduled_date} "
                f"{scheduled_time}",
                "%Y-%m-%d %H:%M"
            )
        )

        if (
            schedule_datetime
            <= datetime.now()
        ):
            continue

        pending_rows.append(
            row
        )

    pending_rows.sort(
        key=lambda row: (
            row["scheduled_date"],
            row["scheduled_time"],
        )
    )

    if not pending_rows:
        return None

    return pending_rows[0]


# ============================================================
# VIDEO PATH
# ============================================================

def resolve_video_path(
    facebook_row
):
    media_path = facebook_row.get(
        "media_path",
        ""
    ).strip()

    if not media_path:
        raise ValueError(
            "media_path đang trống."
        )

    if os.path.isabs(
        media_path
    ):
        video_path = media_path

    else:
        video_path = os.path.join(
            BASE_DIR,
            media_path.replace(
                "/",
                os.sep
            )
        )

    video_path = os.path.abspath(
        video_path
    )

    if not os.path.isfile(
        video_path
    ):
        raise FileNotFoundError(
            video_path
        )

    if os.path.getsize(
        video_path
    ) <= 0:
        raise ValueError(
            f"Video file đang rỗng: "
            f"{video_path}"
        )

    return video_path


# ============================================================
# PAGE READY
# ============================================================

def wait_page_ready(page):
    page.wait_for_load_state(
        "domcontentloaded"
    )

    time.sleep(6)


# ============================================================
# CREATE POST
# GIỮ NGUYÊN SELECTOR
# ============================================================

def click_create_post(page):
    print(
        "Click Bạn đang nghĩ gì?..."
    )

    create_post_button = (
        page.locator(
            'div[role="button"]'
            '[tabindex="0"]'
            '.x1i10hfl.x1ejq31n'
            ':has(span:text-is('
            '"Bạn đang nghĩ gì?"))'
        )
        .first
    )

    create_post_button.wait_for(
        state="visible",
        timeout=60000
    )

    create_post_button.click(
        timeout=60000
    )

    time.sleep(3)


# ============================================================
# CAPTION
# GIỮ NGUYÊN SELECTOR
# ============================================================

def fill_caption(page, caption):
    print(
        "Fill caption and hashtags..."
    )

    caption_box = (
        page.locator(
            'div[role="dialog"] '
            'div[contenteditable="true"]'
            '[role="textbox"]'
        )
        .first
    )

    caption_box.wait_for(
        state="visible",
        timeout=60000
    )

    caption_box.click(
        timeout=60000
    )

    page.keyboard.insert_text(
        caption
    )

    time.sleep(2)


# ============================================================
# UPLOAD VIDEO
# GIỮ NGUYÊN SELECTOR
# ============================================================

def upload_video(
    page,
    video_path
):
    print(
        "Click Ảnh/video..."
    )

    media_button = (
        page.locator(
            'div[aria-label="Ảnh/video"]'
            '[role="button"]'
            '.x1i10hfl.x1qjc9v5'
            '.xjqpnuy.xc5r6h4'
        )
        .first
    )

    media_button.wait_for(
        state="visible",
        timeout=60000
    )

    with page.expect_file_chooser(
        timeout=60000
    ) as file_chooser_info:
        media_button.click(
            timeout=60000
        )

    file_chooser_info.value.set_files(
        video_path
    )

    print(
        "Video selected:",
        video_path
    )

    time.sleep(15)


# ============================================================
# FIRST NEXT
# GIỮ NGUYÊN SELECTOR
# ============================================================

def click_first_next(page):
    print(
        "Click first Tiếp..."
    )

    next_button = (
        page.locator(
            'div[aria-label="Tiếp"]'
            '[role="button"]'
            '.x1i10hfl.xjbqb8w'
        )
        .first
    )

    next_button.wait_for(
        state="visible",
        timeout=60000
    )

    next_button.click(
        timeout=60000
    )

    time.sleep(3)


# ============================================================
# MAKEUP
# GIỮ NGUYÊN SELECTOR VÀ THAO TÁC
# ============================================================

def fill_makeup(page):
    print(
        "Fill makeup..."
    )

    makeup_input = (
        page.locator(
            'div[role="dialog"] '
            'input.x1i10hfl.xggy1nq'
            '.xtpw4lu.x1tutvks'
            '[type="text"]'
            ':not([role])'
        )
        .first
    )

    makeup_input.wait_for(
        state="visible",
        timeout=60000
    )

    makeup_input.click(
        timeout=60000
    )

    makeup_input.fill(
        "makeup"
    )

    time.sleep(1)


# ============================================================
# ADD TAG
# GIỮ NGUYÊN SELECTOR
# ============================================================

def open_add_tag_menu(page):
    print(
        "Click Thêm thẻ..."
    )

    add_tag_input = (
        page.locator(
            'input[aria-label="Thêm thẻ"]'
            '[role="textbox"]'
            '[type="search"]'
        )
        .first
    )

    add_tag_input.wait_for(
        state="visible",
        timeout=60000
    )

    add_tag_input.click(
        timeout=60000
    )

    time.sleep(2)


# ============================================================
# FASHION & STYLE
# GIỮ NGUYÊN SELECTOR VÀ THAO TÁC
# ============================================================

def select_fashion_and_style(page):
    print(
        "Select Fashion & Style..."
    )

    option_text = (
        page.get_by_text(
            "Fashion & Style",
            exact=True
        )
        .first
    )

    option_text.wait_for(
        state="visible",
        timeout=60000
    )

    option_container = (
        option_text.locator(
            "xpath=ancestor::div"
            "[contains(@class,'x1qjc9v5')]"
            "[1]"
        )
    )

    if (
        option_container.count()
        > 0
    ):
        option_container.click(
            timeout=60000
        )

    else:
        option_text.click(
            timeout=60000
        )

    time.sleep(2)


# ============================================================
# BEAUTY
# GIỮ NGUYÊN SELECTOR VÀ THAO TÁC
# ============================================================

def select_beauty(page):
    print(
        "Select Beauty..."
    )

    option_text = (
        page.get_by_text(
            "Beauty",
            exact=True
        )
        .first
    )

    option_text.wait_for(
        state="visible",
        timeout=60000
    )

    option_container = (
        option_text.locator(
            "xpath=ancestor::div"
            "[contains(@class,'x1qjc9v5')]"
            "[1]"
        )
    )

    if (
        option_container.count()
        > 0
    ):
        option_container.click(
            timeout=60000
        )

    else:
        option_text.click(
            timeout=60000
        )

    time.sleep(2)


# ============================================================
# SECOND NEXT
# GIỮ NGUYÊN SELECTOR
# ============================================================

def click_second_next(page):
    print(
        "Click second Tiếp..."
    )

    next_text = (
        page.get_by_text(
            "Tiếp",
            exact=True
        )
        .last
    )

    next_text.wait_for(
        state="visible",
        timeout=60000
    )

    clickable = next_text.locator(
        "xpath=ancestor::div"
        "[@role='button'][1]"
    )

    if clickable.count() > 0:
        clickable.click(
            timeout=60000
        )

    else:
        next_text.click(
            timeout=60000
        )

    time.sleep(3)


# ============================================================
# OPEN SCHEDULE
# GIỮ NGUYÊN SELECTOR
# ============================================================

def open_schedule_options(page):
    print(
        "Click Lựa chọn lịch đăng..."
    )

    schedule_text = (
        page.get_by_text(
            "Lựa chọn lịch đăng",
            exact=True
        )
        .first
    )

    schedule_text.wait_for(
        state="visible",
        timeout=60000
    )

    schedule_row = (
        schedule_text.locator(
            "xpath=ancestor::div"
            "[contains(@class,'html-div')]"
            "[1]"
        )
    )

    if schedule_row.count() > 0:
        schedule_row.click(
            timeout=60000
        )

    else:
        schedule_text.click(
            timeout=60000
        )

    time.sleep(2)


# ============================================================
# DATE
# ============================================================

def format_facebook_date(
    scheduled_date
):
    date_value = datetime.strptime(
        scheduled_date,
        "%Y-%m-%d"
    )

    return (
        f"{date_value.day} tháng "
        f"{date_value.month}, "
        f"{date_value.year}"
    )


def fill_schedule_date(
    page,
    scheduled_date
):
    date_text = format_facebook_date(
        scheduled_date
    )

    print(
        "Fill schedule date:",
        date_text
    )

    date_input = (
        page.locator(
            'input[role="combobox"]'
            '[type="text"]'
            ':not([aria-haspopup="listbox"])'
        )
        .last
    )

    date_input.wait_for(
        state="visible",
        timeout=60000
    )

    date_input.click(
        timeout=60000
    )

    date_input.press(
        "Control+A"
    )

    date_input.fill(
        date_text
    )

    date_input.press(
        "Tab"
    )

    time.sleep(2)


# ============================================================
# TIME
# ============================================================

def fill_schedule_time(
    page,
    scheduled_time
):
    print(
        "Fill schedule time:",
        scheduled_time
    )

    time_input = (
        page.locator(
            'input[role="combobox"]'
            '[aria-haspopup="listbox"]'
            '[type="text"]'
        )
        .last
    )

    time_input.wait_for(
        state="visible",
        timeout=60000
    )

    time_input.click(
        timeout=60000
    )

    time_input.press(
        "Control+A"
    )

    time_input.fill(
        scheduled_time
    )

    time_input.press(
        "Tab"
    )

    time.sleep(2)


# ============================================================
# SCHEDULE LATER
# GIỮ NGUYÊN SELECTOR
# ============================================================

def click_schedule_later(page):
    print(
        "Click Lên lịch đăng sau..."
    )

    schedule_later_button = (
        page.locator(
            'div[aria-label='
            '"Lên lịch đăng sau"]'
            '[role="button"]'
        )
        .first
    )

    schedule_later_button.wait_for(
        state="visible",
        timeout=60000
    )

    schedule_later_button.click(
        timeout=60000
    )

    time.sleep(3)


# ============================================================
# FINAL SCHEDULE
# GIỮ NGUYÊN SELECTOR
# ============================================================

def click_final_schedule(page):
    print(
        "Click final Lên lịch..."
    )

    final_schedule_button = (
        page.locator(
            'div[aria-label="Lên lịch"]'
            '[role="button"]'
        )
        .last
    )

    final_schedule_button.wait_for(
        state="visible",
        timeout=60000
    )

    final_schedule_button.click(
        timeout=60000
    )

    time.sleep(10)


# ============================================================
# OPTIONAL AD MENU
# GIỮ NGUYÊN THAO TÁC
# ============================================================

def dismiss_optional_ad_menu(page):
    print(
        "Check optional advertising menu..."
    )

    try:
        time.sleep(2)

        visible_popups = page.locator(
            '[role="dialog"]:visible, '
            '[role="menu"]:visible'
        )

        if visible_popups.count() == 0:
            print(
                "No advertising menu detected."
            )

            return

        viewport = page.viewport_size or {
            "width": 1400,
            "height": 900,
        }

        width = viewport["width"]
        height = viewport["height"]

        print(
            "Advertising menu detected. "
            "Click outside left margin..."
        )

        page.mouse.click(
            10,
            height // 2
        )

        time.sleep(1)

        if visible_popups.count() > 0:
            print(
                "Menu still visible. "
                "Click outside right margin..."
            )

            page.mouse.click(
                width - 10,
                height // 2
            )

            time.sleep(1)

    except Exception as error:
        print(
            "Skip advertising menu:",
            str(error)
        )


# ============================================================
# PROCESS ONE JOB
# ============================================================

def process_job(
    page,
    facebook_row,
    schedule_row
):
    job_id = facebook_row[
        "job_id"
    ]

    category = (
        facebook_row.get(
            "category",
            ""
        )
        .strip()
    )

    product_id = facebook_row[
        "product_id"
    ]

    if not category:
        raise ValueError(
            f"Missing category for job: "
            f"{job_id}"
        )

    video_path = resolve_video_path(
        facebook_row
    )

    caption = load_caption(
        category
    )

    scheduled_date = schedule_row[
        "scheduled_date"
    ]

    scheduled_time = schedule_row[
        "scheduled_time"
    ]

    print("=" * 60)

    print(
        "FACEBOOK JOB:",
        job_id
    )

    print(
        "CATEGORY    :",
        category
    )

    print(
        "PRODUCT     :",
        product_id
    )

    print(
        "VIDEO       :",
        video_path
    )

    print(
        "SCHEDULE    :",
        scheduled_date,
        scheduled_time
    )

    print("=" * 60)

    # ========================================================
    # GIỮ NGUYÊN TOÀN BỘ THỨ TỰ THAO TÁC
    # ========================================================

    page.goto(
        FACEBOOK_PAGE_URL,
        wait_until="domcontentloaded",
        timeout=120000
    )

    wait_page_ready(page)

    click_create_post(page)

    fill_caption(
        page,
        caption
    )

    upload_video(
        page,
        video_path
    )

    click_first_next(page)

    fill_makeup(page)

    open_add_tag_menu(page)

    select_fashion_and_style(page)

    select_beauty(page)

    click_second_next(page)

    open_schedule_options(page)

    fill_schedule_date(
        page,
        scheduled_date
    )

    fill_schedule_time(
        page,
        scheduled_time
    )

    click_schedule_later(page)

    click_final_schedule(page)

    dismiss_optional_ad_menu(page)

    print("=" * 60)
    print(
        "FACEBOOK POST SCHEDULED"
    )
    print("=" * 60)


# ============================================================
# MAIN
# ============================================================

def main():
    os.makedirs(
        QUEUE_DIR,
        exist_ok=True
    )

    os.makedirs(
        SCREENSHOT_DIR,
        exist_ok=True
    )

    facebook_rows = load_csv(
        FACEBOOK_QUEUE_FILE
    )

    schedule_rows = load_csv(
        FACEBOOK_SCHEDULE_FILE
    )

    pending_jobs = get_pending_jobs(
        facebook_rows
    )

    if not pending_jobs:
        print(
            "No pending Facebook jobs."
        )

        return

    with sync_playwright() as p:
        browser = (
            p.chromium
            .launch_persistent_context(
                user_data_dir=(
                    FACEBOOK_PROFILE_DIR
                ),
                channel="chrome",
                headless=False,
                viewport={
                    "width": 1400,
                    "height": 900,
                },
                accept_downloads=True,
            )
        )

        # Reuse the first page from the persistent Chrome profile.
        # Some Chrome/Playwright combinations start the persistent context
        # with an initial blank tab. Explicitly navigate that tab before the
        # worker loop so the real profile is initialized exactly like the
        # standalone profile test.
        page = (
            browser.pages[0]
            if browser.pages
            else browser.new_page()
        )

        print("Chrome profile:", FACEBOOK_PROFILE_DIR)
        print("Initial page URL:", page.url)
        print("Opening Facebook profile page...")

        page.goto(
            FACEBOOK_PAGE_URL,
            wait_until="domcontentloaded",
            timeout=120000
        )
        wait_page_ready(page)

        print("Facebook opened:", page.url)
        print("Page title:", page.title())

        for facebook_row in pending_jobs:
            schedule_row = (
                get_pending_schedule(
                    schedule_rows
                )
            )

            if schedule_row is None:
                print(
                    "No Facebook schedule "
                    "slot available."
                )

                break

            job_id = facebook_row[
                "job_id"
            ]

            category = (
                facebook_row.get(
                    "category",
                    ""
                )
                .strip()
            )

            product_id = facebook_row[
                "product_id"
            ]

            print("=" * 60)

            print(
                "START JOB:",
                job_id
            )

            print(
                "CATEGORY:",
                category
            )

            print(
                "PRODUCT:",
                product_id
            )

            print("=" * 60)

            try:
                if not category:
                    raise ValueError(
                        f"Missing category for job: "
                        f"{job_id}"
                    )

                update_queue_status(
                    facebook_rows,
                    job_id,
                    "processing"
                )

                save_csv(
                    FACEBOOK_QUEUE_FILE,
                    facebook_rows,
                    FACEBOOK_QUEUE_FIELDNAMES
                )

                schedule_row[
                    "status"
                ] = "processing"

                schedule_row[
                    "job_id"
                ] = job_id

                # Ghi category vào schedule.
                schedule_row[
                    "category"
                ] = category

                schedule_row[
                    "product_id"
                ] = product_id

                schedule_row[
                    "error"
                ] = ""

                save_csv(
                    FACEBOOK_SCHEDULE_FILE,
                    schedule_rows,
                    FACEBOOK_SCHEDULE_FIELDNAMES
                )

                process_job(
                    page,
                    facebook_row,
                    schedule_row
                )

                update_queue_status(
                    facebook_rows,
                    job_id,
                    "scheduled"
                )

                schedule_row[
                    "status"
                ] = "used"

                schedule_row[
                    "error"
                ] = ""

                print(
                    "DONE:",
                    job_id
                )

            except Exception as error:
                error_message = str(
                    error
                )

                print(
                    "FAILED:",
                    job_id,
                    error_message
                )

                increase_attempts(
                    facebook_rows,
                    job_id
                )

                update_queue_status(
                    facebook_rows,
                    job_id,
                    "failed",
                    error_message
                )

                schedule_row[
                    "status"
                ] = "failed"

                schedule_row[
                    "error"
                ] = error_message

                screenshot_path = os.path.join(
                    SCREENSHOT_DIR,
                    f"{job_id}_facebook_error.png"
                )

                try:
                    page.screenshot(
                        path=screenshot_path,
                        full_page=True
                    )

                    print(
                        "Screenshot:",
                        screenshot_path
                    )

                except Exception:
                    pass

            finally:
                save_csv(
                    FACEBOOK_QUEUE_FILE,
                    facebook_rows,
                    FACEBOOK_QUEUE_FIELDNAMES
                )

                save_csv(
                    FACEBOOK_SCHEDULE_FILE,
                    schedule_rows,
                    FACEBOOK_SCHEDULE_FIELDNAMES
                )

                time.sleep(5)

        browser.close()


if __name__ == "__main__":
    main()