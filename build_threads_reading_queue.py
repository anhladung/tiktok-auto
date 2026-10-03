import csv
import json
import os
import random

from datetime import datetime


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

QUEUE_DIR = os.path.join(
    BASE_DIR,
    "queue",
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data",
    "threads",
)

QUEUE_FILE = os.path.join(
    QUEUE_DIR,
    "threads_reading_queue.csv",
)

ARCHETYPES_FILE = os.path.join(
    DATA_DIR,
    "archetypes.json",
)


# ============================================================
# SETTINGS
# ============================================================

JOBS_TO_GENERATE = 20


# ============================================================
# READING TYPES
# ============================================================

READING_TYPES = {
    "message_for_you": 30,
    "love_reading": 25,
    "work_money": 15,
    "pick_3": 20,
    "weekly_message": 10,
}


# ============================================================
# PERSONALIZATION TYPES
# ============================================================

PERSONALIZATION_TYPES = {
    "birth_month_group": 45,
    "birth_day_range": 25,
    "birth_day_digit": 15,
    "birth_period": 15,
}


# ============================================================
# PERSONALIZATION VALUES
# ============================================================

BIRTH_MONTH_GROUPS = [
    "tháng 1, 5 và 9",
    "tháng 2, 6 và 10",
    "tháng 3, 7 và 11",
    "tháng 4, 8 và 12",

    "tháng 1, 4, 7 và 10",
    "tháng 2, 5, 8 và 11",
    "tháng 3, 6, 9 và 12",

    "tháng 1, 6 và 11",
    "tháng 2, 7 và 12",
    "tháng 3, 5 và 10",
    "tháng 4, 8 và 11",
    "tháng 5, 9 và 12",
]


BIRTH_DAY_RANGES = [
    "ngày sinh từ 1–10",
    "ngày sinh từ 11–20",
    "ngày sinh từ 21–31",
]


BIRTH_DAY_DIGITS = [
    "ngày sinh có số 1",
    "ngày sinh có số 2",
    "ngày sinh có số 3",
    "ngày sinh có số 5",
    "ngày sinh có số 7",
    "ngày sinh có số 8",
]


BIRTH_PERIODS = [
    "sinh vào đầu năm, từ tháng 1–4",
    "sinh vào giữa năm, từ tháng 5–8",
    "sinh vào cuối năm, từ tháng 9–12",
    "sinh trong nửa đầu năm",
    "sinh trong nửa cuối năm",
]


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
# LOAD DATA
# ============================================================

def load_archetypes():
    if not os.path.exists(
        ARCHETYPES_FILE
    ):
        raise FileNotFoundError(
            f"Archetypes file not found: "
            f"{ARCHETYPES_FILE}"
        )

    with open(
        ARCHETYPES_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def load_existing_rows():
    if not os.path.exists(
        QUEUE_FILE
    ):
        return []

    with open(
        QUEUE_FILE,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return list(
            csv.DictReader(f)
        )


# ============================================================
# ID
# ============================================================

def get_next_job_number(rows):
    max_number = 0

    for row in rows:

        job_id = row.get(
            "reading_job_id",
            "",
        ).strip()

        if not job_id.startswith(
            "THR"
        ):
            continue

        try:
            number = int(
                job_id.replace(
                    "THR",
                    "",
                )
            )

            max_number = max(
                max_number,
                number,
            )

        except ValueError:
            continue

    return max_number + 1


# ============================================================
# READING TYPE
# ============================================================

def choose_reading_type():
    reading_types = list(
        READING_TYPES.keys()
    )

    weights = list(
        READING_TYPES.values()
    )

    return random.choices(
        reading_types,
        weights=weights,
        k=1,
    )[0]


# ============================================================
# PERSONALIZATION
# ============================================================

def choose_personalization_type():
    personalization_types = list(
        PERSONALIZATION_TYPES.keys()
    )

    weights = list(
        PERSONALIZATION_TYPES.values()
    )

    return random.choices(
        personalization_types,
        weights=weights,
        k=1,
    )[0]


def choose_personalization_value(
    personalization_type,
):

    if (
        personalization_type
        == "birth_month_group"
    ):
        return random.choice(
            BIRTH_MONTH_GROUPS
        )

    if (
        personalization_type
        == "birth_day_range"
    ):
        return random.choice(
            BIRTH_DAY_RANGES
        )

    if (
        personalization_type
        == "birth_day_digit"
    ):
        return random.choice(
            BIRTH_DAY_DIGITS
        )

    if (
        personalization_type
        == "birth_period"
    ):
        return random.choice(
            BIRTH_PERIODS
        )

    raise ValueError(
        f"Unknown personalization type: "
        f"{personalization_type}"
    )


def choose_personalization():
    personalization_type = (
        choose_personalization_type()
    )

    personalization_value = (
        choose_personalization_value(
            personalization_type
        )
    )

    return (
        personalization_type,
        personalization_value,
    )


# ============================================================
# ARCHETYPES
# ============================================================

def choose_archetypes(
    archetypes,
    reading_type,
):

    names = list(
        archetypes.keys()
    )

    if not names:
        raise ValueError(
            "No archetypes available."
        )

    # --------------------------------------------------------
    # PICK 3
    # --------------------------------------------------------

    if reading_type == "pick_3":

        if len(names) < 3:
            raise ValueError(
                "pick_3 requires at least "
                "3 archetypes."
            )

        selected = random.sample(
            names,
            3,
        )

        return (
            selected[0],
            selected[1],
            selected[2],
        )

    # --------------------------------------------------------
    # NORMAL READING
    # --------------------------------------------------------

    selected = random.choice(
        names
    )

    return (
        selected,
        "",
        "",
    )


# ============================================================
# DUPLICATE CHECK
# ============================================================

def get_existing_combinations(rows):
    combinations = set()

    for row in rows:

        combination = (
            row.get(
                "reading_type",
                "",
            ).strip(),

            row.get(
                "personalization_type",
                "",
            ).strip(),

            row.get(
                "personalization_value",
                "",
            ).strip(),

            row.get(
                "archetype_1",
                "",
            ).strip(),

            row.get(
                "archetype_2",
                "",
            ).strip(),

            row.get(
                "archetype_3",
                "",
            ).strip(),
        )

        combinations.add(
            combination
        )

    return combinations


# ============================================================
# BUILD
# ============================================================

def build_queue():

    # --------------------------------------------------------
    # ENSURE DIRECTORIES
    # --------------------------------------------------------

    os.makedirs(
        QUEUE_DIR,
        exist_ok=True,
    )

    os.makedirs(
        DATA_DIR,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    archetypes = (
        load_archetypes()
    )

    existing_rows = (
        load_existing_rows()
    )

    next_number = (
        get_next_job_number(
            existing_rows
        )
    )

    used_combinations = (
        get_existing_combinations(
            existing_rows
        )
    )

    # --------------------------------------------------------
    # BUILD NEW ROWS
    # --------------------------------------------------------

    new_rows = []

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    attempts = 0

    max_attempts = (
        JOBS_TO_GENERATE
        * 100
    )

    while (
        len(new_rows)
        < JOBS_TO_GENERATE
        and attempts
        < max_attempts
    ):

        attempts += 1

        # ----------------------------------------------------
        # READING TYPE
        # ----------------------------------------------------

        reading_type = (
            choose_reading_type()
        )

        # ----------------------------------------------------
        # PERSONALIZATION
        # ----------------------------------------------------

        (
            personalization_type,
            personalization_value,
        ) = choose_personalization()

        # ----------------------------------------------------
        # ARCHETYPES
        # ----------------------------------------------------

        (
            archetype_1,
            archetype_2,
            archetype_3,
        ) = choose_archetypes(
            archetypes,
            reading_type,
        )

        # ----------------------------------------------------
        # CHECK DUPLICATE
        # ----------------------------------------------------

        combination = (
            reading_type,
            personalization_type,
            personalization_value,
            archetype_1,
            archetype_2,
            archetype_3,
        )

        if (
            combination
            in used_combinations
        ):
            continue

        # ----------------------------------------------------
        # ID
        # ----------------------------------------------------

        job_number = (
            next_number
            + len(new_rows)
        )

        job_id = (
            f"THR"
            f"{job_number:06d}"
        )

        # ----------------------------------------------------
        # ROW
        # ----------------------------------------------------

        row = {
            "reading_job_id":
                job_id,

            "created_at":
                now,

            "reading_type":
                reading_type,

            "personalization_type":
                personalization_type,

            "personalization_value":
                personalization_value,

            "archetype_1":
                archetype_1,

            "archetype_2":
                archetype_2,

            "archetype_3":
                archetype_3,

            "status":
                "pending",

            "post_text":
                "",

            "reply_1":
                "",

            "reply_2":
                "",

            "reply_3":
                "",

            "error":
                "",
        }

        new_rows.append(
            row
        )

        used_combinations.add(
            combination
        )

    # --------------------------------------------------------
    # COMBINE
    # --------------------------------------------------------

    all_rows = (
        existing_rows
        + new_rows
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    with open(
        QUEUE_FILE,
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
            all_rows
        )

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    print()
    print(
        "=" * 60
    )

    print(
        f"[OK] Added "
        f"{len(new_rows)} "
        f"reading jobs."
    )

    print(
        f"[OK] Queue: "
        f"{QUEUE_FILE}"
    )

    if (
        len(new_rows)
        < JOBS_TO_GENERATE
    ):

        print(
            f"[WARN] Requested "
            f"{JOBS_TO_GENERATE} jobs "
            f"but only generated "
            f"{len(new_rows)}."
        )

    # --------------------------------------------------------
    # SHOW NEW JOBS
    # --------------------------------------------------------

    if new_rows:

        print()
        print(
            "[NEW JOBS]"
        )

        for row in new_rows:

            print(
                f"{row['reading_job_id']} "
                f"| "
                f"{row['reading_type']} "
                f"| "
                f"{row['personalization_value']} "
                f"| "
                f"{row['archetype_1']}"
            )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    build_queue()