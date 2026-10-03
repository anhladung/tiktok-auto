import csv
import os

from datetime import datetime, timedelta
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

QUEUE_DIR = BASE_DIR / "queue"

FACEBOOK_SCHEDULE_FILE = (
    QUEUE_DIR / "facebook_schedule.csv"
)


# ============================================================
# SETTINGS
# ============================================================

DAYS_TO_GENERATE = 30


# ============================================================
# CSV FIELDS
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
# FACEBOOK POSTING TIMES
# ============================================================

FACEBOOK_GOLDEN_TIMES = {
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
# CSV HANDLING
# ============================================================

def load_csv(path):
    if not path.exists():
        return []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:
        return list(
            csv.DictReader(file)
        )


def save_csv(path, rows):
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_file = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temp_file.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=FACEBOOK_SCHEDULE_FIELDNAMES,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(rows)

    os.replace(
        temp_file,
        path
    )


# ============================================================
# NORMALIZE OLD SCHEDULE
# ============================================================

def normalize_existing_rows(rows):
    """
    Chuẩn hóa lịch cũ sang cấu trúc mới.

    Lịch cũ chưa có category sẽ tự nhận giá trị rỗng.
    Khi một Facebook job được gán vào slot, worker sau
    sẽ điền category là lipstick hoặc sandal.
    """

    normalized_rows = []

    for raw_row in rows:
        row = {
            field: str(
                raw_row.get(
                    field,
                    ""
                ) or ""
            ).strip()
            for field in FACEBOOK_SCHEDULE_FIELDNAMES
        }

        if not row["status"]:
            row["status"] = "pending"

        normalized_rows.append(
            row
        )

    return normalized_rows


# ============================================================
# DATE HELPERS
# ============================================================

def get_day_name(date_value):
    return (
        date_value
        .strftime("%A")
        .lower()
    )


def build_schedule_id(
    scheduled_date,
    scheduled_time
):
    clean_time = scheduled_time.replace(
        ":",
        ""
    )

    return (
        "facebook_s_"
        f"{scheduled_date.strftime('%Y_%m_%d')}_"
        f"{clean_time}"
    )


# ============================================================
# BUILD FACEBOOK SCHEDULE
# ============================================================

def build_facebook_schedule():
    existing_rows = normalize_existing_rows(
        load_csv(
            FACEBOOK_SCHEDULE_FILE
        )
    )

    existing_schedule_ids = {
        row["schedule_id"]
        for row in existing_rows
        if row["schedule_id"]
    }

    today = datetime.now().date()

    new_rows = []

    for day_offset in range(
        DAYS_TO_GENERATE
    ):
        scheduled_date = (
            today
            + timedelta(
                days=day_offset
            )
        )

        day_name = get_day_name(
            scheduled_date
        )

        scheduled_times = (
            FACEBOOK_GOLDEN_TIMES.get(
                day_name,
                []
            )
        )

        for scheduled_time in scheduled_times:
            schedule_id = build_schedule_id(
                scheduled_date,
                scheduled_time
            )

            if (
                schedule_id
                in existing_schedule_ids
            ):
                continue

            new_rows.append({
                "schedule_id": schedule_id,

                "scheduled_date": (
                    scheduled_date.strftime(
                        "%Y-%m-%d"
                    )
                ),

                "scheduled_time": scheduled_time,

                "day_name": day_name,

                "status": "pending",

                # Các cột này sẽ được điền khi một job
                # Facebook được gán vào khung giờ.
                "job_id": "",

                "category": "",

                "product_id": "",

                "error": "",
            })

            existing_schedule_ids.add(
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

    save_csv(
        FACEBOOK_SCHEDULE_FILE,
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
        if row.get("job_id", "").strip()
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

    print("=" * 60)

    print(
        "Facebook schedule created:",
        FACEBOOK_SCHEDULE_FILE
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

    print("=" * 60)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    build_facebook_schedule()