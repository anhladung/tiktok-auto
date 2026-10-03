import csv
import json
import random
import os
import time
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

QUEUE_DIR = os.path.join(BASE_DIR, "queue")
UPLOAD_QUEUE_FILE = os.path.join(QUEUE_DIR, "upload_queue.csv")
SCHEDULE_FILE = os.path.join(QUEUE_DIR, "tiktok_schedule.csv")

TIKTOK_PROFILE_DIR = r"C:\tiktok_profile_01"
TIKTOK_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?from=webapp&tab=video"

CAPTION_FILE = os.path.join(
    BASE_DIR,
    "assets",
    "captions",
    "captions.json"
)

UPLOAD_FIELDNAMES = [
    "job_id",
    "product_id",
    "video_path",
    "status",
    "error",
]

SCHEDULE_FIELDNAMES = [
    "schedule_id",
    "scheduled_date",
    "scheduled_time",
    "day_name",
    "status",
    "job_id",
    "product_id",
    "error",
]

def load_caption():
    with open(CAPTION_FILE, "r", encoding="utf-8") as f:
        templates = json.load(f)

    template = random.choice(templates)

    caption = template["caption"]

    hashtags = " ".join(template["hashtags"])

    return f"{caption}\n\n{hashtags}"

def load_csv(path):
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def save_csv(path, rows, fieldnames):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def get_pending_uploads(rows):

    jobs = []

    for row in rows:
        if row.get("status", "").strip().lower() == "pending":
            jobs.append(row)

    return jobs

def update_upload_status(rows, job_id, status, error=""):

    for row in rows:
        if row["job_id"] == job_id:
            row["status"] = status
            row["error"] = error
            break


def get_pending_schedule(rows):
    pending_rows = []

    for row in rows:
        if row.get("status", "").strip().lower() != "pending":
            continue

        scheduled_date = row.get("scheduled_date", "").strip()
        scheduled_time = row.get("scheduled_time", "").strip()

        if not scheduled_date or not scheduled_time:
            continue

        dt = datetime.strptime(
            f"{scheduled_date} {scheduled_time}",
            "%Y-%m-%d %H:%M"
        )

        if dt <= datetime.now():
            continue

        pending_rows.append(row)

    pending_rows.sort(
        key=lambda row: (
            row["scheduled_date"],
            row["scheduled_time"],
        )
    )

    if not pending_rows:
        return None

    return pending_rows[0]


def abs_path(relative_path):
    return os.path.join(BASE_DIR, relative_path.replace("/", os.sep))


def wait_page_ready(page):
    page.wait_for_load_state("domcontentloaded")
    time.sleep(5)


def upload_video(page, video_path):
    print("Click Select video...")

    with page.expect_file_chooser() as fc_info:
        page.locator('button[data-e2e="select_video_button"]').click(timeout=60000)

    file_chooser = fc_info.value
    file_chooser.set_files(video_path)

    print("Video selected.")
    time.sleep(10)


def fill_caption(page, caption):
    print("Fill caption...")

    caption_box = page.locator(
        'div.public-DraftEditor-content[contenteditable="true"]'
    ).first

    caption_box.click(timeout=60000)
    page.keyboard.press("Control+A")
    page.keyboard.type(caption, delay=20)

    time.sleep(2)


def click_schedule_radio(page):
    print("Click Schedule radio...")

    schedule_radio = page.locator('input[value="schedule"]').first
    schedule_radio.click(force=True, timeout=60000)

    time.sleep(2)


def select_time(page, scheduled_time):
    hour, minute = scheduled_time.split(":")

    print(f"Select time: {scheduled_time}")

    time_input = page.locator(
        'input.TUXTextInputCore-input[readonly]'
    ).nth(0)

    inputs = page.locator('input.TUXTextInputCore-input[readonly]')
    count = inputs.count()

    target = None
    for i in range(count):
        value = inputs.nth(i).get_attribute("value") or ""
        if ":" in value:
            target = inputs.nth(i)
            break

    if target is None:
        raise Exception("Cannot find time input")

    target.click(timeout=60000)
    time.sleep(1)

    hour_option = page.locator(
        f'span.tiktok-timepicker-option-text:text-is("{hour}")'
    ).first
    hour_option.click(timeout=60000)

    time.sleep(1)

    minute_option = page.locator(
        f'span.tiktok-timepicker-option-text:text-is("{minute}")'
    ).last
    minute_option.click(timeout=60000)

    time.sleep(1)


def month_name_to_number(month_name):
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

    return months[month_name.strip().lower()]


def get_calendar_month_year(page):
    month_text = page.locator(".month-title").inner_text(timeout=10000)
    year_text = page.locator(".year-title").inner_text(timeout=10000)

    month = month_name_to_number(month_text)
    year = int(year_text.strip())

    return month, year


def click_next_month(page):
    arrows = page.locator(".month-header-wrapper .arrow")
    arrows.nth(1).click(timeout=30000)
    time.sleep(1)


def click_prev_month(page):
    arrows = page.locator(".month-header-wrapper .arrow")
    arrows.nth(0).click(timeout=30000)
    time.sleep(1)

def select_date(page, scheduled_date):
    target_date = datetime.strptime(scheduled_date, "%Y-%m-%d").date()
    target_year = target_date.year
    target_month = target_date.month
    target_day = str(target_date.day)

    print(f"Select date: {scheduled_date}")

    # Tìm đúng ô ngày theo value dạng YYYY-MM-DD
    date_input = page.locator(
        'input.TUXTextInputCore-input[readonly][value*="-"]'
    ).first

    date_input.wait_for(state="visible", timeout=60000)
    date_input.click(timeout=60000)

    time.sleep(1)

    for _ in range(12):
        current_month, current_year = get_calendar_month_year(page)

        if current_month == target_month and current_year == target_year:
            break

        current_value = current_year * 12 + current_month
        target_value = target_year * 12 + target_month

        if current_value < target_value:
            click_next_month(page)
        else:
            click_prev_month(page)
    else:
        raise Exception("Cannot navigate to target month")

    day_locator = page.locator(
        f'span.day.valid:text-is("{target_day}")'
    ).first

    day_locator.click(timeout=60000)
    time.sleep(1)


def enable_ai_generated_content(page):

    print("Opening advanced settings...")

    # Click Show more
    page.locator(
        '[data-e2e="advanced_settings_container"]'
    ).get_by_text(
        "Show more",
        exact=True
    ).click(
        force=True
    )

    print("Clicked Show more")

    time.sleep(3)


    # DEBUG 1
    print("DEBUG: Take screenshot after Show more")

    page.screenshot(
        path="debug_after_show_more.png",
        full_page=True
    )

    print(
        page.locator("body").inner_text()[:3000]
    )


    print("Searching AI-generated content...")


    # tìm dòng AI
    ai_text = page.get_by_text(
        "AI-generated content",
        exact=True
    )


    try:
        ai_text.wait_for(
            state="visible",
            timeout=30000
        )

        print("AI text found")


    except Exception as e:

        print(
            "AI text NOT FOUND"
        )

        page.screenshot(
            path="debug_ai_not_found.png",
            full_page=True
        )

        raise e



    # DEBUG 2
    print(
        "AI element HTML:"
    )

    print(
        ai_text.evaluate(
            "(el)=>el.outerHTML"
        )
    )


    # tìm vùng cha
    row = ai_text.locator(
        "xpath=ancestor::div[1]"
    )


    print(
        "ROW HTML:"
    )

    print(
        row.evaluate(
            "(el)=>el.outerHTML"
        )
    )



    # tìm switch gần đó
    switch = row.locator(
        'input[role="switch"]'
    )


    print(
        "Switch count:",
        switch.count()
    )


    if switch.count() == 0:

        print(
            "Switch not found in parent, searching nearby..."
        )


        switch = ai_text.locator(
            "xpath=../../.."
        ).locator(
            'input[role="switch"]'
        )


        print(
            "Nearby switch count:",
            switch.count()
        )



    switch.wait_for(
        state="attached",
        timeout=30000
    )


    print(
        "Switch HTML:"
    )

    print(
        switch.evaluate(
            "(el)=>el.outerHTML"
        )
    )


    state = switch.get_attribute(
        "aria-checked"
    )


    print(
        "AI switch state:",
        state
    )


    if state != "true":

        print(
            "Clicking switch..."
        )


        switch.locator(
            "xpath=.."
        ).click(
            force=True
        )


        print(
            "Clicked AI-generated content switch"
        )


    else:

        print(
            "AI-generated content already ON"
        )


    time.sleep(3)


    # DEBUG 3 sau click
    print(
        "After click state:",
        switch.get_attribute("aria-checked")
    )

def click_final_schedule_button(page):
    time.sleep(25)
    print("Click final Schedule button...")

    button = page.locator('button[data-e2e="post_video_button"]').first
    button.click(timeout=60000)

    time.sleep(8)


def process_job(page, upload_row, schedule_row):
    product_id = upload_row["product_id"]
    job_id = upload_row["job_id"]
    video_path = abs_path(upload_row["video_path"])

    scheduled_date = schedule_row["scheduled_date"]
    scheduled_time = schedule_row["scheduled_time"]

    if not os.path.exists(video_path):
        raise FileNotFoundError(video_path)

    print("=" * 60)
    print(f"UPLOAD JOB : {job_id}")
    print(f"PRODUCT    : {product_id}")
    print(f"VIDEO      : {video_path}")
    print(f"SCHEDULE   : {scheduled_date} {scheduled_time}")
    print("=" * 60)

    page.goto(TIKTOK_UPLOAD_URL, wait_until="domcontentloaded", timeout=120000)
    wait_page_ready(page)

    upload_video(page, video_path)
    caption = load_caption()
    fill_caption(page, caption)
    click_schedule_radio(page)

    select_date(page, scheduled_date)
    select_time(page, scheduled_time)

    enable_ai_generated_content(page)
    click_final_schedule_button(page)

    print("=" * 60)
    print("UPLOAD SCHEDULED")
    print("=" * 60)


def main():

    upload_rows = load_csv(UPLOAD_QUEUE_FILE)
    schedule_rows = load_csv(SCHEDULE_FILE)


    pending_jobs = get_pending_uploads(upload_rows)


    if not pending_jobs:
        print("No pending upload jobs.")
        return



    with sync_playwright() as p:


        browser = p.chromium.launch_persistent_context(
            user_data_dir=TIKTOK_PROFILE_DIR,
            channel="chrome",
            headless=False,
            viewport={
                "width":1400,
                "height":900
            },
            accept_downloads=True,
        )


        page = (
            browser.pages[0]
            if browser.pages
            else browser.new_page()
        )



        for upload_row in pending_jobs:


            schedule_row = get_pending_schedule(
                schedule_rows
            )


            if schedule_row is None:

                print(
                    "No schedule slot available"
                )

                break



            job_id = upload_row["job_id"]


            print("="*60)
            print(
                "START JOB:",
                job_id
            )
            print("="*60)



            try:

                update_upload_status(
                    upload_rows,
                    job_id,
                    "processing"
                )


                save_csv(
                    UPLOAD_QUEUE_FILE,
                    upload_rows,
                    UPLOAD_FIELDNAMES
                )


                schedule_row["status"]="processing"
                schedule_row["job_id"]=job_id
                schedule_row["product_id"]=upload_row["product_id"]



                save_csv(
                    SCHEDULE_FILE,
                    schedule_rows,
                    SCHEDULE_FIELDNAMES
                )


                process_job(
                    page,
                    upload_row,
                    schedule_row
                )



                update_upload_status(
                    upload_rows,
                    job_id,
                    "scheduled"
                )


                schedule_row["status"]="used"



                print(
                    "DONE:",
                    job_id
                )



            except Exception as e:


                print(
                    "FAILED:",
                    job_id,
                    e
                )


                update_upload_status(
                    upload_rows,
                    job_id,
                    "failed",
                    str(e)
                )



                schedule_row["status"]="failed"
                schedule_row["error"]=str(e)



            finally:


                save_csv(
                    UPLOAD_QUEUE_FILE,
                    upload_rows,
                    UPLOAD_FIELDNAMES
                )


                save_csv(
                    SCHEDULE_FILE,
                    schedule_rows,
                    SCHEDULE_FIELDNAMES
                )


                time.sleep(5)



        browser.close()



if __name__=="__main__":
    main()