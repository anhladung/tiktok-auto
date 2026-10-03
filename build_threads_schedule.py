import csv
import os

from datetime import datetime, timedelta
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

QUEUE_DIR = BASE_DIR / "queue"

SCHEDULE_FILE = (
    QUEUE_DIR
    / "threads_schedule.csv"
)


# ============================================================
# SETTINGS
# ============================================================

DAYS_TO_GENERATE = 30

SUPPORTED_CATEGORIES = [
    "lipstick",
    "sandal",
    "keychain",
]


# ============================================================
# SCHEDULE FIELDS
# ============================================================

FIELDNAMES = [
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
# GOLDEN TIMES
# ============================================================

GOLDEN_TIMES = {
    "monday": [
        "10:00",
        "18:00",
        "22:00",
    ],

    "tuesday": [
        "14:00",
        "16:00",
        "21:00",
    ],

    "wednesday": [
        "11:00",
        "19:00",
        "20:00",
    ],

    "thursday": [
        "07:00",
        "12:00",
        "21:00",
    ],

    "friday": [
        "01:00",
        "15:00",
        "17:00",
    ],

    "saturday": [
        "07:00",
        "08:00",
        "23:00",
    ],

    "sunday": [
        "04:00",
        "19:00",
        "20:00",
    ],
}


# ============================================================
# DIRECTORY
# ============================================================

def ensure_dirs():
    QUEUE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# LOAD SCHEDULE
# ============================================================

def load_existing_schedule():
    if not SCHEDULE_FILE.exists():
        return []

    with SCHEDULE_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return list(
            csv.DictReader(file)
        )


# ============================================================
# NORMALIZE OLD ROWS
# ============================================================

def normalize_existing_rows(rows):
    """
    Chuẩn hóa lịch cũ sang cấu trúc mới.

    Lịch cũ chưa có category sẽ nhận giá trị rỗng.
    Khi Threads job được gán vào slot, hệ thống sẽ điền:

        category = lipstick

    hoặc:

        category = sandal

    hoặc:

        category = keychain
    """

    normalized = []

    for raw in rows:
        row = {
            field: str(
                raw.get(
                    field,
                    ""
                ) or ""
            ).strip()
            for field in FIELDNAMES
        }

        row["status"] = (
            row["status"]
            or "pending"
        )

        normalized.append(
            row
        )

    return normalized


# ============================================================
# SAVE SCHEDULE
# ============================================================

def save_schedule(rows):
    temp_file = SCHEDULE_FILE.with_suffix(
        ".csv.tmp"
    )

    with temp_file.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=FIELDNAMES,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)

    os.replace(
        temp_file,
        SCHEDULE_FILE
    )


# ============================================================
# DATE HELPERS
# ============================================================

def get_day_name(date_obj):
    return (
        date_obj
        .strftime("%A")
        .lower()
    )


def build_schedule_id(
    date_obj,
    time_str
):
    clean_time = time_str.replace(
        ":",
        ""
    )

    return (
        "threads_s_"
        f"{date_obj.strftime('%Y_%m_%d')}_"
        f"{clean_time}"
    )


# ============================================================
# BUILD THREADS SCHEDULE
# ============================================================

def build_threads_schedule():
    ensure_dirs()

    existing_rows = normalize_existing_rows(
        load_existing_schedule()
    )

    existing_ids = {
        row["schedule_id"]
        for row in existing_rows
        if row.get("schedule_id")
    }

    today = datetime.now().date()

    new_rows = []

    for offset in range(
        DAYS_TO_GENERATE
    ):
        date_obj = (
            today
            + timedelta(
                days=offset
            )
        )

        day_name = get_day_name(
            date_obj
        )

        scheduled_times = (
            GOLDEN_TIMES.get(
                day_name,
                []
            )
        )

        for time_str in scheduled_times:
            schedule_id = build_schedule_id(
                date_obj,
                time_str
            )

            if schedule_id in existing_ids:
                continue

            new_rows.append({
                "schedule_id": schedule_id,

                "scheduled_date": (
                    date_obj.strftime(
                        "%Y-%m-%d"
                    )
                ),

                "scheduled_time": time_str,

                "day_name": day_name,

                "status": "pending",

                # Được điền khi gán Threads job.
                "job_id": "",

                # lipstick, sandal hoặc keychain.
                "category": "",

                "product_id": "",

                "error": "",
            })

            existing_ids.add(
                schedule_id
            )

    all_rows = (
        existing_rows
        + new_rows
    )

    all_rows.sort(
        key=lambda row: (
            row["scheduled_date"],
            row["scheduled_time"],
        )
    )

    save_schedule(
        all_rows
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    pending_slots = sum(
        1
        for row in all_rows
        if (
            row.get("status", "")
            .strip()
            .lower()
            == "pending"
        )
    )

    assigned_slots = sum(
        1
        for row in all_rows
        if row.get(
            "job_id",
            ""
        ).strip()
    )

    lipstick_slots = sum(
        1
        for row in all_rows
        if row.get("category") == "lipstick"
    )

    sandal_slots = sum(
        1
        for row in all_rows
        if row.get("category") == "sandal"
    )

    keychain_slots = sum(
        1
        for row in all_rows
        if row.get("category") == "keychain"
    )

    print("=" * 60)

    print(
        "Threads schedule created:",
        SCHEDULE_FILE
    )

    print(
        "Supported categories:",
        ", ".join(SUPPORTED_CATEGORIES)
    )

    print(
        "Existing slots:",
        len(existing_rows)
    )

    print(
        "New slots added:",
        len(new_rows)
    )

    print(
        "Total slots:",
        len(all_rows)
    )

    print(
        "Pending slots:",
        pending_slots
    )

    print(
        "Assigned slots:",
        assigned_slots
    )

    print(
        "Lipstick slots:",
        lipstick_slots
    )

    print(
        "Sandal slots:",
        sandal_slots
    )

    print(
        "Keychain slots:",
        keychain_slots
    )

    print("=" * 60)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    build_threads_schedule()