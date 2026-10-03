import csv
import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

QUEUE_DIR = os.path.join(BASE_DIR, "queue")
SCHEDULE_FILE = os.path.join(QUEUE_DIR, "tiktok_schedule.csv")

DAYS_TO_GENERATE = 30

FIELDNAMES = [
    "schedule_id",
    "scheduled_date",
    "scheduled_time",
    "day_name",
    "status",
    "job_id",
    "product_id",
    "error",
]

GOLDEN_TIMES = {
    "monday": [
        "01:10",
        "06:40",
        "09:50",
        "13:40",
        "17:20",
        "22:20",
    ],
    "tuesday": [
        "02:10",
        "07:20",
        "10:30",
        "13:50",
        "17:30",
        "22:40",
    ],
    "wednesday": [
        "01:40",
        "06:50",
        "10:10",
        "13:30",
        "17:10",
        "22:10",
    ],
    "thursday": [
        "02:20",
        "07:40",
        "10:50",
        "13:40",
        "17:40",
        "22:30",
    ],
    "friday": [
        "01:20",
        "06:30",
        "09:40",
        "13:20",
        "17:00",
        "22:50",
    ],
    "saturday": [
        "02:30",
        "08:10",
        "11:20",
        "14:10",
        "17:30",
        "22:20",
    ],
    "sunday": [
        "01:50",
        "07:30",
        "10:40",
        "14:20",
        "17:50",
        "22:40",
    ],
}
def ensure_dirs():
    os.makedirs(QUEUE_DIR, exist_ok=True)


def load_existing_schedule():
    if not os.path.exists(SCHEDULE_FILE):
        return []

    with open(SCHEDULE_FILE, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def save_schedule(rows):
    with open(SCHEDULE_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def get_day_name(date_obj):
    return date_obj.strftime("%A").lower()


def build_schedule_id(date_obj, time_str):
    clean_time = time_str.replace(":", "")
    return f"s_{date_obj.strftime('%Y_%m_%d')}_{clean_time}"


def normalize_existing_rows(rows):
    normalized_rows = []

    for row in rows:
        normalized_row = {}

        for field in FIELDNAMES:
            normalized_row[field] = row.get(field, "")

        if not normalized_row["status"]:
            normalized_row["status"] = "pending"

        normalized_rows.append(normalized_row)

    return normalized_rows


def build_tiktok_schedule():
    ensure_dirs()

    existing_rows = load_existing_schedule()
    existing_rows = normalize_existing_rows(existing_rows)

    existing_ids = {row["schedule_id"] for row in existing_rows if row.get("schedule_id")}

    today = datetime.now().date()
    new_rows = []

    for i in range(DAYS_TO_GENERATE):
        date_obj = today + timedelta(days=i)
        day_name = get_day_name(date_obj)

        if day_name not in GOLDEN_TIMES:
            continue

        for time_str in GOLDEN_TIMES[day_name]:
            schedule_id = build_schedule_id(date_obj, time_str)

            if schedule_id in existing_ids:
                continue

            row = {
                "schedule_id": schedule_id,
                "scheduled_date": date_obj.strftime("%Y-%m-%d"),
                "scheduled_time": time_str,
                "day_name": day_name,
                "status": "pending",
                "job_id": "",
                "product_id": "",
                "error": "",
            }

            new_rows.append(row)

    all_rows = existing_rows + new_rows

    all_rows.sort(
        key=lambda row: (
            row["scheduled_date"],
            row["scheduled_time"],
        )
    )

    save_schedule(all_rows)

    print("=" * 50)
    print(f"TikTok schedule created: {SCHEDULE_FILE}")
    print(f"Existing slots: {len(existing_rows)}")
    print(f"New slots added: {len(new_rows)}")
    print(f"Total slots: {len(all_rows)}")
    print("=" * 50)


if __name__ == "__main__":
    build_tiktok_schedule()