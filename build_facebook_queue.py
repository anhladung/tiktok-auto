import csv
import os

from datetime import datetime
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

VIDEOS_DIR = Path(
    r"C:\Users\Thinkbook 14G2\Downloads\tiktok-auto\videos"
)

QUEUE_DIR = BASE_DIR / "queue"

FACEBOOK_QUEUE_FILE = (
    QUEUE_DIR / "facebook_queue.csv"
)


# ============================================================
# CATEGORIES
# ============================================================

ENABLED_CATEGORIES = [
    "snack",
    "keychain",
    "phone_case",
]


# ============================================================
# QUEUE FIELDS
# ============================================================

FIELDNAMES = [
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
# HELPERS
# ============================================================

def now_text():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def file_exists_and_not_empty(path):
    return (
        path.is_file()
        and path.stat().st_size > 0
    )


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
            fieldnames=FIELDNAMES,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(rows)

    os.replace(
        temp_file,
        path
    )


def normalize_rows(rows):
    """
    Chuẩn hóa queue cũ và mới.

    Queue cũ không có category sẽ được gán category rỗng.
    Khi tìm thấy video tương ứng, row cũ sẽ được chuyển
    sang cấu trúc mới.
    """

    normalized = []

    for raw_row in rows:
        row = {
            field: str(
                raw_row.get(
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

        row["attempts"] = (
            row["attempts"]
            or "0"
        )

        row["updated_at"] = (
            row["updated_at"]
            or now_text()
        )

        normalized.append(
            row
        )

    return normalized


# ============================================================
# VIDEO NAME HANDLING
# ============================================================

def get_product_id(video_path):
    """
    Ví dụ:

        LP001.mp4
            -> LP001

        LP001_merged.mp4
            -> LP001

        SDL001.mp4
            -> SDL001

        KC001.mp4
            -> KC001
    """

    stem = video_path.stem.strip()

    if stem.lower().endswith(
        "_merged"
    ):
        stem = stem[:-7]

    return stem.strip()


def get_video_priority(video_path):
    """
    Giữ nguyên logic cũ:

    Nếu có cả:
        LP001_merged.mp4
        LP001.mp4

    thì ưu tiên LP001_merged.mp4.
    """

    if video_path.stem.lower().endswith(
        "_merged"
    ):
        return 0

    return 1


# ============================================================
# DISCOVER VIDEOS
# ============================================================

def discover_videos():
    """
    Quét video theo cấu trúc:

        videos/lipstick/LP001.mp4
        videos/sandal/SDL001.mp4
        videos/keychain/KC001.mp4

    Kết quả có dạng:

        {
            ("lipstick", "LP001"): Path(...),
            ("sandal", "SDL001"): Path(...),
            ("keychain", "KC001"): Path(...),
        }
    """

    if not VIDEOS_DIR.exists():
        print(
            "Videos directory not found:",
            VIDEOS_DIR
        )

        return {}

    videos_by_product = {}

    for category in ENABLED_CATEGORIES:
        category_video_dir = (
            VIDEOS_DIR / category
        )

        if not category_video_dir.exists():
            print(
                "Category video directory not found:",
                category_video_dir
            )

            continue

        video_files = sorted(
            (
                path
                for path in category_video_dir.iterdir()
                if (
                    file_exists_and_not_empty(path)
                    and path.suffix.lower() == ".mp4"
                )
            ),
            key=lambda path: (
                get_product_id(path).lower(),
                get_video_priority(path),
                path.name.lower(),
            )
        )

        for video_path in video_files:
            product_id = get_product_id(
                video_path
            )

            if not product_id:
                continue

            product_key = (
                category,
                product_id
            )

            # Do danh sách đã được sort theo priority,
            # file đầu tiên sẽ được giữ lại.
            if product_key not in videos_by_product:
                videos_by_product[
                    product_key
                ] = video_path

    return videos_by_product


# ============================================================
# BUILD FACEBOOK QUEUE
# ============================================================

def build_facebook_queue():
    existing_rows = normalize_rows(
        load_csv(
            FACEBOOK_QUEUE_FILE
        )
    )

    # Job theo cấu trúc mới.
    existing_by_job_id = {
        row["job_id"]: row
        for row in existing_rows
        if row["job_id"]
    }

    # Hỗ trợ queue cũ chưa có category.
    legacy_by_product_id = {
        row["product_id"]: row
        for row in existing_rows
        if (
            row["product_id"]
            and not row["category"]
        )
    }

    videos_by_product = discover_videos()

    if not videos_by_product:
        print(
            "No .mp4 videos found in:",
            VIDEOS_DIR
        )

        return

    discovered_rows = []

    # Dùng id(row) để biết row cũ nào đã được tái sử dụng.
    used_existing_rows = set()

    sorted_product_keys = sorted(
        videos_by_product,
        key=lambda item: (
            item[0].lower(),
            item[1].lower(),
        )
    )

    for category, product_id in sorted_product_keys:
        video_path = videos_by_product[
            (
                category,
                product_id
            )
        ]

        job_id = (
            f"{category}_"
            f"{product_id}_facebook"
        )

        media_path = str(
            video_path.resolve()
        )

        # ====================================================
        # GIỮ JOB CŨ THEO JOB_ID MỚI
        # ====================================================

        if job_id in existing_by_job_id:
            row = existing_by_job_id[
                job_id
            ]

            used_existing_rows.add(
                id(row)
            )

            row["category"] = category
            row["product_id"] = product_id
            row["media_path"] = media_path

            discovered_rows.append(
                row
            )

            continue

        # ====================================================
        # CHUYỂN JOB CŨ CHƯA CÓ CATEGORY
        # ====================================================

        legacy_row = legacy_by_product_id.get(
            product_id
        )

        if legacy_row is not None:
            used_existing_rows.add(
                id(legacy_row)
            )

            legacy_row["job_id"] = job_id
            legacy_row["category"] = category
            legacy_row["product_id"] = product_id
            legacy_row["media_path"] = media_path
            legacy_row["updated_at"] = now_text()

            discovered_rows.append(
                legacy_row
            )

            print(
                "Migrated legacy Facebook job:",
                f"{category}/{product_id}"
            )

            continue

        # ====================================================
        # TẠO JOB MỚI
        # ====================================================

        discovered_rows.append({
            "job_id": job_id,
            "category": category,
            "product_id": product_id,
            "media_path": media_path,
            "caption": "",
            "status": "pending",
            "attempts": "0",
            "error": "",
            "updated_at": now_text(),
        })

    discovered_job_ids = {
        row["job_id"]
        for row in discovered_rows
    }

    # Giữ nguyên logic cũ:
    # các job cũ không còn video vẫn được giữ lại.
    old_rows = [
        row
        for row in existing_rows
        if (
            id(row) not in used_existing_rows
            and row["job_id"]
            not in discovered_job_ids
        )
    ]

    all_rows = (
        discovered_rows
        + old_rows
    )

    all_rows.sort(
        key=lambda row: (
            row.get(
                "category",
                ""
            ).lower(),

            row.get(
                "product_id",
                ""
            ).lower(),

            row.get(
                "job_id",
                ""
            ).lower(),
        )
    )

    save_csv(
        FACEBOOK_QUEUE_FILE,
        all_rows
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    snack_jobs = sum(
        1
        for row in discovered_rows
        if row.get("category") == "snack"
    )

    keychain_jobs = sum(
        1
        for row in discovered_rows
        if row.get("category") == "keychain"
    )

    phone_case_jobs = sum(
        1
        for row in discovered_rows
        if row.get("category") == "phone_case"
    )

    pending_jobs = sum(
        1
        for row in discovered_rows
        if (
            row.get("status", "")
            .strip()
            .lower()
            == "pending"
        )
    )

    done_jobs = sum(
        1
        for row in discovered_rows
        if (
            row.get("status", "")
            .strip()
            .lower()
            == "done"
        )
    )

    print("=" * 60)

    print(
        "Facebook queue created:",
        FACEBOOK_QUEUE_FILE
    )

    print(
        "Video directory:",
        VIDEOS_DIR
    )

    print(
        "Runnable jobs:",
        len(discovered_rows)
    )

    print(
        "Snack jobs:",
        snack_jobs
    )

    print(
        "Keychain jobs:",
        keychain_jobs
    )

    print(
        "Phone case jobs:",
        phone_case_jobs
    )

    print(
        "Pending jobs:",
        pending_jobs
    )

    print(
        "Done jobs:",
        done_jobs
    )

    print(
        "Old jobs retained:",
        len(old_rows)
    )

    print("=" * 60)

    for row in discovered_rows:
        print(
            f"{row['category']}/"
            f"{row['product_id']}",
            "->",
            row["media_path"]
        )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    build_facebook_queue()