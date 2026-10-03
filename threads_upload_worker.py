import csv
import os
import time
from datetime import datetime

from playwright.sync_api import sync_playwright


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

QUEUE_DIR = os.path.join(
    BASE_DIR,
    "queue"
)

READING_QUEUE_FILE = os.path.join(
    QUEUE_DIR,
    "threads_reading_queue.csv"
)

SCHEDULE_FILE = os.path.join(
    QUEUE_DIR,
    "threads_schedule.csv"
)

THREADS_PROFILE_DIR = (
    r"C:\threads_auto_profile_01"
)

THREADS_URL = (
    "https://www.threads.com/"
)

SCREENSHOT_DIR = os.path.join(
    BASE_DIR,
    "screenshots"
)


# ============================================================
# SETTINGS
# ============================================================

HEADLESS = False

NAVIGATION_TIMEOUT = 120_000

ELEMENT_TIMEOUT = 60_000


# ------------------------------------------------------------
# WAIT / BUFFER
# ------------------------------------------------------------

PAGE_READY_DELAY = 5

AFTER_OPEN_COMPOSER_DELAY = 2

AFTER_TEXT_DELAY = 2

AFTER_MORE_DELAY = 1

AFTER_SCHEDULE_MENU_DELAY = 2

AFTER_DATE_DELAY = 1

AFTER_TIME_DELAY = 1

AFTER_DONE_DELAY = 2

AFTER_FINAL_SCHEDULE_DELAY = 8

BETWEEN_JOBS_DELAY = 5


# ============================================================
# READING QUEUE FIELDS
# ============================================================

READING_QUEUE_FIELDNAMES = [
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
# SCHEDULE FIELDS
#
# Giữ schema cũ để build_threads_schedule.py hiện tại
# chưa cần sửa ngay.
#
# job_id sẽ chứa reading_job_id.
# category sẽ ghi "reading".
# product_id để trống.
# ============================================================

SCHEDULE_FIELDNAMES = [
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
    if not os.path.exists(
        path
    ):
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
    temp_file = (
        path
        + ".tmp"
    )

    with open(
        temp_file,
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

        writer.writerows(
            rows
        )

    os.replace(
        temp_file,
        path
    )


# ============================================================
# READING QUEUE
# ============================================================

def get_generated_reading_jobs(
    rows
):
    jobs = []

    for row in rows:

        status = row.get(
            "status",
            ""
        ).strip().lower()

        if status != "generated":
            continue

        post_text = row.get(
            "post_text",
            ""
        ).strip()

        if not post_text:
            continue

        jobs.append(
            row
        )

    return jobs


def update_reading_status(
    rows,
    reading_job_id,
    status,
    error=""
):
    for row in rows:

        if row.get(
            "reading_job_id",
            ""
        ).strip() != reading_job_id:
            continue

        row["status"] = status

        row["error"] = error

        break


# ============================================================
# RESET INTERRUPTED
# ============================================================

def reset_interrupted_jobs(
    rows
):
    changed = False

    for row in rows:

        status = row.get(
            "status",
            ""
        ).strip().lower()

        if status == "scheduling":

            row["status"] = (
                "generated"
            )

            row["error"] = ""

            changed = True

    return changed


# ============================================================
# SCHEDULE
# ============================================================

def get_pending_schedule(
    rows
):
    pending_rows = []

    now = datetime.now()

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

        if not scheduled_date:
            continue

        if not scheduled_time:
            continue

        try:

            scheduled_datetime = (
                datetime.strptime(
                    f"{scheduled_date} "
                    f"{scheduled_time}",
                    "%Y-%m-%d %H:%M"
                )
            )

        except ValueError:

            print(
                "[WARN] Invalid schedule:",
                scheduled_date,
                scheduled_time
            )

            continue

        # Chỉ lấy slot trong tương lai.
        if scheduled_datetime <= now:
            continue

        pending_rows.append(
            row
        )

    pending_rows.sort(
        key=lambda row: (
            row.get(
                "scheduled_date",
                ""
            ),
            row.get(
                "scheduled_time",
                ""
            ),
        )
    )

    if not pending_rows:
        return None

    return pending_rows[0]


# ============================================================
# PAGE READY
# ============================================================

def wait_page_ready(
    page
):
    print(
        "[WAIT] Waiting Threads page..."
    )

    page.wait_for_load_state(
        "domcontentloaded"
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
        "[OK] Threads page ready."
    )


# ============================================================
# POST BUTTON
#
# GIỮ SELECTOR TỪ CODE CŨ
# ============================================================

def click_post_button(
    page
):
    print(
        "[ACTION] Click Post..."
    )

    post_button = page.locator(
        'div[role="button"][tabindex="0"]'
        '.x1i10hfl.x1ypdohk.xdl72j9'
        ':has(> div.xc26acl.x6s0dn4.x78zum5'
        '.xl56j7k.x6ikm8r.x10wlt62'
        ':text-is("Post"))'
    ).first

    post_button.wait_for(
        state="visible",
        timeout=ELEMENT_TIMEOUT
    )

    post_button.click(
        timeout=ELEMENT_TIMEOUT
    )

    page.wait_for_timeout(
        AFTER_OPEN_COMPOSER_DELAY
        * 1000
    )

    print(
        "[OK] Composer opened."
    )


# ============================================================
# FILL POST TEXT
#
# Giữ cách nhập cũ:
# Threads tự focus composer sau khi Click Post.
# ============================================================

def fill_post_text(
    page,
    post_text
):
    post_text = str(
        post_text or ""
    ).strip()

    if not post_text:

        raise ValueError(
            "post_text is empty."
        )

    print(
        "[ACTION] Fill post text..."
    )

    print(
        "[TEXT LENGTH]",
        len(post_text)
    )

    page.keyboard.insert_text(
        post_text
    )

    page.wait_for_timeout(
        AFTER_TEXT_DELAY
        * 1000
    )

    print(
        "[OK] Post text filled."
    )


# ============================================================
# MORE
#
# GIỮ SELECTOR TỪ CODE CŨ
# ============================================================

def click_more_button(
    page
):
    print(
        "[ACTION] Click More..."
    )

    more_button = page.locator(
        'div[role="button"]'
        '[aria-haspopup="dialog"]'
        '.x1i10hfl.x1qjc9v5.xjbqb8w'
        ':has(svg[aria-label="More"])'
    ).first

    more_button.wait_for(
        state="visible",
        timeout=ELEMENT_TIMEOUT
    )

    more_button.click(
        timeout=ELEMENT_TIMEOUT
    )

    page.wait_for_timeout(
        AFTER_MORE_DELAY
        * 1000
    )


# ============================================================
# SCHEDULE MENU
#
# GIỮ SELECTOR TỪ CODE CŨ
# ============================================================

def click_schedule_menu(
    page
):
    print(
        "[ACTION] Click Schedule... menu..."
    )

    schedule_menu = page.locator(
        'div[role="menuitem"][tabindex="0"]'
        '.x1i10hfl.x1qjc9v5.xjbqb8w'
        ':has(span:text-is("Schedule..."))'
    ).first

    schedule_menu.wait_for(
        state="visible",
        timeout=ELEMENT_TIMEOUT
    )

    schedule_menu.click(
        timeout=ELEMENT_TIMEOUT
    )

    page.wait_for_timeout(
        AFTER_SCHEDULE_MENU_DELAY
        * 1000
    )


# ============================================================
# CALENDAR
# ============================================================

def month_name_to_number(
    month_name
):
    months = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }

    return months[
        month_name
        .strip()
        .lower()
    ]


def get_calendar_month_year(
    page
):
    import re

    month_pattern = re.compile(
        r"^(January|February|March|"
        r"April|May|June|July|August|"
        r"September|October|November|"
        r"December)\s+(\d{4})$",
        re.IGNORECASE
    )

    month_heading = page.locator(
        'div[role="status"]'
        '[aria-live="polite"] '
        'h2.html-h2'
    ).first

    month_heading.wait_for(
        state="visible",
        timeout=ELEMENT_TIMEOUT
    )

    text = (
        month_heading
        .inner_text()
        .strip()
    )

    match = (
        month_pattern.match(
            text
        )
    )

    if not match:

        raise Exception(
            "Cannot read Threads "
            f"calendar month: {text}"
        )

    month = (
        month_name_to_number(
            match.group(1)
        )
    )

    year = int(
        match.group(2)
    )

    return (
        month,
        year
    )


# ============================================================
# NEXT MONTH
#
# GIỮ SELECTOR TỪ CODE CŨ
# ============================================================

def click_next_month(
    page
):
    print(
        "[ACTION] Next Month..."
    )

    next_button = page.locator(
        'button[aria-label="Next Month"]'
        '[type="button"]'
        '.html-button.xdj266r.x14z9mp'
        '.xat24cr.x1lziwak'
    ).first

    next_button.wait_for(
        state="visible",
        timeout=30_000
    )

    next_button.click(
        timeout=30_000
    )

    page.wait_for_timeout(
        1000
    )


# ============================================================
# PREVIOUS MONTH
#
# GIỮ SELECTOR TỪ CODE CŨ
# ============================================================

def click_previous_month(
    page
):
    print(
        "[ACTION] Previous Month..."
    )

    previous_button = page.locator(
        'button[aria-label="Previous Month"]'
        '[type="button"]'
        '.html-button.xdj266r.x14z9mp'
        '.xat24cr.x1lziwak'
    ).first

    previous_button.wait_for(
        state="visible",
        timeout=30_000
    )

    previous_button.click(
        timeout=30_000
    )

    page.wait_for_timeout(
        1000
    )


# ============================================================
# SELECT DATE
#
# GIỮ SELECTOR TỪ CODE CŨ
# ============================================================

def select_date(
    page,
    scheduled_date
):
    target_date = (
        datetime.strptime(
            scheduled_date,
            "%Y-%m-%d"
        )
    )

    target_year = (
        target_date.year
    )

    target_month = (
        target_date.month
    )

    print(
        "[ACTION] Select date:",
        scheduled_date
    )

    calendar = page.locator(
        'div[aria-label="Choose Date"]'
        '[role="grid"]'
        '.x78zum5.xdt5ytf.x1a2a7pz.x3pnbk8'
    ).first

    calendar.wait_for(
        state="visible",
        timeout=ELEMENT_TIMEOUT
    )

    # --------------------------------------------------------
    # MOVE TO CORRECT MONTH
    # --------------------------------------------------------

    for _ in range(24):

        (
            current_month,
            current_year
        ) = get_calendar_month_year(
            page
        )

        if (
            current_month
            == target_month
            and current_year
            == target_year
        ):
            break

        current_value = (
            current_year * 12
            + current_month
        )

        target_value = (
            target_year * 12
            + target_month
        )

        if (
            current_value
            < target_value
        ):

            click_next_month(
                page
            )

        else:

            click_previous_month(
                page
            )

    else:

        raise Exception(
            "Cannot navigate "
            "to target month."
        )

    # --------------------------------------------------------
    # SELECT DAY
    # --------------------------------------------------------

    full_date_text = (
        f"{target_date.strftime('%A')}, "
        f"{target_date.strftime('%B')} "
        f"{target_date.day}, "
        f"{target_date.year}"
    )

    date_text = calendar.locator(
        'div.x9f619.x1ja2u2z.xzpqnlu'
        '.x1hyvwdk.x14bfe9o.xjm9jq1'
    ).filter(
        has_text=full_date_text
    ).first

    date_text.wait_for(
        state="visible",
        timeout=ELEMENT_TIMEOUT
    )

    day_cell = (
        date_text.locator(
            'xpath=ancestor::div'
            '[@role="gridcell"][1]'
        )
    )

    if (
        day_cell.get_attribute(
            "aria-disabled"
        )
        == "true"
    ):

        raise Exception(
            "Target date is disabled: "
            f"{full_date_text}"
        )

    day_cell.click(
        timeout=ELEMENT_TIMEOUT
    )

    page.wait_for_timeout(
        AFTER_DATE_DELAY
        * 1000
    )


# ============================================================
# SELECT HOUR
#
# GIỮ SELECTOR TỪ CODE CŨ
# ============================================================

def select_hour(
    page,
    scheduled_time
):
    hour, minute = (
        scheduled_time.split(
            ":"
        )
    )

    # Vì selector inspect cũ chỉ thao tác field giờ.
    if minute != "00":

        raise Exception(
            "Threads uploader hiện dùng "
            "selector cũ chỉ nhập giờ. "
            "scheduled_time phải có phút = 00."
        )

    print(
        "[ACTION] Select hour:",
        hour
    )

    hour_input = page.locator(
        'div[data-pressable-container="true"] '
        'input.x1i10hfl.xggy1nq.xtpw4lu'
        '[placeholder="hh"]'
        '[type="text"]'
    ).first

    hour_input.wait_for(
        state="visible",
        timeout=ELEMENT_TIMEOUT
    )

    hour_input.click(
        timeout=ELEMENT_TIMEOUT
    )

    hour_input.press(
        "Control+A"
    )

    hour_input.fill(
        hour
    )

    page.wait_for_timeout(
        AFTER_TIME_DELAY
        * 1000
    )


# ============================================================
# DONE BUTTON
#
# GIỮ SELECTOR TỪ CODE CŨ
# ============================================================

def click_done_button(
    page
):
    print(
        "[ACTION] Click Done..."
    )

    done_button = page.locator(
        'div[role="button"][tabindex="0"]'
        '.x1i10hfl.x1ypdohk.xdl72j9'
        ':has(> div.x6ikm8r.x10wlt62.xlyipyv'
        ':text-is("Done"))'
    ).first

    done_button.wait_for(
        state="visible",
        timeout=ELEMENT_TIMEOUT
    )

    done_button.click(
        timeout=ELEMENT_TIMEOUT
    )

    page.wait_for_timeout(
        AFTER_DONE_DELAY
        * 1000
    )


# ============================================================
# FINAL SCHEDULE
#
# GIỮ SELECTOR TỪ CODE CŨ
# ============================================================

def click_final_schedule_button(
    page
):
    print(
        "[ACTION] Click final Schedule..."
    )

    schedule_content = page.locator(
        'div.xc26acl.x6s0dn4.x78zum5'
        '.xl56j7k.x6ikm8r.x10wlt62'
        '.xf7dkkf.xv54qhq.xlyipyv.xw2npq5'
        ':has(> div:text-is("Schedule"))'
    ).last

    schedule_content.wait_for(
        state="visible",
        timeout=ELEMENT_TIMEOUT
    )

    schedule_button = (
        schedule_content.locator(
            'xpath=ancestor::*'
            '[@role="button"][1]'
        )
    )

    if (
        schedule_button.count()
        > 0
    ):

        schedule_button.click(
            timeout=ELEMENT_TIMEOUT
        )

    else:

        schedule_content.click(
            timeout=ELEMENT_TIMEOUT
        )

    print(
        f"[WAIT] Confirm scheduling "
        f"{AFTER_FINAL_SCHEDULE_DELAY}s..."
    )

    page.wait_for_timeout(
        AFTER_FINAL_SCHEDULE_DELAY
        * 1000
    )


# ============================================================
# PROCESS ONE READING
# ============================================================

def process_job(
    page,
    reading_row,
    schedule_row
):
    reading_job_id = (
        reading_row.get(
            "reading_job_id",
            ""
        ).strip()
    )

    reading_type = (
        reading_row.get(
            "reading_type",
            ""
        ).strip()
    )

    personalization = (
        reading_row.get(
            "personalization_value",
            ""
        ).strip()
    )

    archetype_1 = (
        reading_row.get(
            "archetype_1",
            ""
        ).strip()
    )

    post_text = (
        reading_row.get(
            "post_text",
            ""
        ).strip()
    )

    if not reading_job_id:

        raise ValueError(
            "Missing reading_job_id."
        )

    if not post_text:

        raise ValueError(
            f"post_text empty: "
            f"{reading_job_id}"
        )

    scheduled_date = (
        schedule_row.get(
            "scheduled_date",
            ""
        ).strip()
    )

    scheduled_time = (
        schedule_row.get(
            "scheduled_time",
            ""
        ).strip()
    )

    print()
    print(
        "=" * 60
    )

    print(
        f"READING JOB    : "
        f"{reading_job_id}"
    )

    print(
        f"TYPE           : "
        f"{reading_type}"
    )

    print(
        f"PERSONALIZATION: "
        f"{personalization}"
    )

    print(
        f"ARCHETYPE      : "
        f"{archetype_1}"
    )

    print(
        f"SCHEDULE       : "
        f"{scheduled_date} "
        f"{scheduled_time}"
    )

    print(
        f"TEXT LENGTH    : "
        f"{len(post_text)}"
    )

    print(
        "=" * 60
    )

    # ========================================================
    # OPEN THREADS
    # ========================================================

    page.goto(
        THREADS_URL,
        wait_until="domcontentloaded",
        timeout=NAVIGATION_TIMEOUT
    )

    wait_page_ready(
        page
    )

    # ========================================================
    # CREATE POST
    # ========================================================

    click_post_button(
        page
    )

    fill_post_text(
        page,
        post_text
    )

    # ========================================================
    # OPEN SCHEDULE
    # ========================================================

    click_more_button(
        page
    )

    click_schedule_menu(
        page
    )

    # ========================================================
    # DATE / TIME
    # ========================================================

    select_date(
        page,
        scheduled_date
    )

    select_hour(
        page,
        scheduled_time
    )

    click_done_button(
        page
    )

    # ========================================================
    # FINAL SCHEDULE
    # ========================================================

    click_final_schedule_button(
        page
    )

    print()
    print(
        "=" * 60
    )

    print(
        "THREADS READING SCHEDULED"
    )

    print(
        "=" * 60
    )


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

    # ========================================================
    # LOAD QUEUES
    # ========================================================

    reading_rows = load_csv(
        READING_QUEUE_FILE
    )

    schedule_rows = load_csv(
        SCHEDULE_FILE
    )

    # ========================================================
    # RESET PREVIOUS INTERRUPTED JOBS
    # ========================================================

    if reset_interrupted_jobs(
        reading_rows
    ):

        save_csv(
            READING_QUEUE_FILE,
            reading_rows,
            READING_QUEUE_FIELDNAMES
        )

    # ========================================================
    # GET GENERATED READINGS
    # ========================================================

    pending_jobs = (
        get_generated_reading_jobs(
            reading_rows
        )
    )

    if not pending_jobs:

        print(
            "[OK] No generated "
            "Threads readings to schedule."
        )

        return

    print(
        f"[INFO] Generated readings: "
        f"{len(pending_jobs)}"
    )

    # ========================================================
    # BROWSER
    # ========================================================

    with sync_playwright() as p:

        browser = (
            p.chromium
            .launch_persistent_context(
                user_data_dir=
                    THREADS_PROFILE_DIR,

                channel=
                    "chrome",

                headless=
                    HEADLESS,

                viewport={
                    "width":
                        1400,

                    "height":
                        900
                },

                accept_downloads=True,
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

        # ====================================================
        # JOB LOOP
        # ====================================================

        for reading_row in pending_jobs:

            schedule_row = (
                get_pending_schedule(
                    schedule_rows
                )
            )

            if schedule_row is None:

                print(
                    "[STOP] No future "
                    "schedule slot available."
                )

                break

            reading_job_id = (
                reading_row.get(
                    "reading_job_id",
                    ""
                ).strip()
            )

            reading_type = (
                reading_row.get(
                    "reading_type",
                    ""
                ).strip()
            )

            print()
            print(
                "=" * 60
            )

            print(
                "[START]",
                reading_job_id
            )

            print(
                "[TYPE]",
                reading_type
            )

            print(
                "=" * 60
            )

            try:

                # ============================================
                # MARK READING AS SCHEDULING
                # ============================================

                update_reading_status(
                    reading_rows,
                    reading_job_id,
                    "scheduling"
                )

                save_csv(
                    READING_QUEUE_FILE,
                    reading_rows,
                    READING_QUEUE_FIELDNAMES
                )

                # ============================================
                # RESERVE SCHEDULE SLOT
                # ============================================

                schedule_row[
                    "status"
                ] = "processing"

                # Giữ cột job_id của schedule cũ,
                # nhưng giá trị giờ là reading_job_id.
                schedule_row[
                    "job_id"
                ] = reading_job_id

                schedule_row[
                    "category"
                ] = "reading"

                schedule_row[
                    "product_id"
                ] = ""

                schedule_row[
                    "error"
                ] = ""

                save_csv(
                    SCHEDULE_FILE,
                    schedule_rows,
                    SCHEDULE_FIELDNAMES
                )

                # ============================================
                # SCHEDULE ON THREADS
                # ============================================

                process_job(
                    page,
                    reading_row,
                    schedule_row
                )

                # ============================================
                # SUCCESS
                # ============================================

                update_reading_status(
                    reading_rows,
                    reading_job_id,
                    "scheduled"
                )

                schedule_row[
                    "status"
                ] = "used"

                schedule_row[
                    "error"
                ] = ""

                print(
                    "[DONE]",
                    reading_job_id
                )

                # ============================================
                # PICK 3 NOTICE
                # ============================================

                if (
                    reading_type
                    == "pick_3"
                ):

                    print(
                        "[INFO] pick_3 detected."
                    )

                    print(
                        "[INFO] Main post scheduled."
                    )

                    print(
                        "[INFO] reply_1 / reply_2 / "
                        "reply_3 remain in reading queue "
                        "for reply worker."
                    )

            except Exception as exc:

                error_message = (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

                print(
                    "[FAILED]",
                    reading_job_id
                )

                print(
                    "[ERROR]",
                    error_message
                )

                # ============================================
                # READING FAILED
                # ============================================

                update_reading_status(
                    reading_rows,
                    reading_job_id,
                    "upload_failed",
                    error_message
                )

                # ============================================
                # SCHEDULE FAILED
                # ============================================

                schedule_row[
                    "status"
                ] = "failed"

                schedule_row[
                    "error"
                ] = error_message

                # ============================================
                # SCREENSHOT
                # ============================================

                screenshot_path = (
                    os.path.join(
                        SCREENSHOT_DIR,
                        f"{reading_job_id}_error.png"
                    )
                )

                try:

                    page.screenshot(
                        path=screenshot_path,
                        full_page=True
                    )

                    print(
                        "[SCREENSHOT]",
                        screenshot_path
                    )

                except Exception:

                    pass

            finally:

                # ============================================
                # ALWAYS SAVE
                # ============================================

                save_csv(
                    READING_QUEUE_FILE,
                    reading_rows,
                    READING_QUEUE_FIELDNAMES
                )

                save_csv(
                    SCHEDULE_FILE,
                    schedule_rows,
                    SCHEDULE_FIELDNAMES
                )

                print(
                    f"[WAIT] Next job in "
                    f"{BETWEEN_JOBS_DELAY}s..."
                )

                time.sleep(
                    BETWEEN_JOBS_DELAY
                )

        browser.close()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    main()