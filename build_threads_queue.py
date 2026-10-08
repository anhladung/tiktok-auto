import csv
import os

from datetime import datetime
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PRODUCTS_ROOT = BASE_DIR / "products"

VIDEO_ROOT = BASE_DIR / "videos"

QUEUE_DIR = BASE_DIR / "queue"

QUEUE_FILE = (
    QUEUE_DIR
    / "threads_queue.csv"
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
# CAPTION SOURCES
# ============================================================

CAPTION_CANDIDATES = [
    "caption.txt",
    "output/caption.txt",
    "output/scripts/caption.txt",
    "output/script.txt",
]


# ============================================================
# BASIC HELPERS
# ============================================================

def now_text():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def ensure_dirs():
    QUEUE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


def file_exists_and_not_empty(path):
    return (
        path.is_file()
        and path.stat().st_size > 0
    )


# ============================================================
# QUEUE HANDLING
# ============================================================

def load_existing_queue():
    if not QUEUE_FILE.exists():
        return []

    with QUEUE_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return list(
            csv.DictReader(file)
        )


def normalize_existing_rows(rows):
    """
    Chuẩn hóa queue cũ sang cấu trúc mới.

    Queue cũ chưa có category sẽ nhận category rỗng.
    Khi tìm thấy đúng video và sản phẩm, row cũ sẽ được
    chuyển sang job có category.
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


def save_queue(rows):
    temp_file = QUEUE_FILE.with_suffix(
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
        QUEUE_FILE
    )


# ============================================================
# PATH HANDLING
# ============================================================

def to_relative_path(path):
    """
    Nếu file nằm trong project thì lưu đường dẫn tương đối.

    Ví dụ:

        videos/lipstick/LP001.mp4
        videos/sandal/SDL001.mp4
        videos/keychain/KC001.mp4
    """

    try:
        return (
            path.resolve()
            .relative_to(
                BASE_DIR.resolve()
            )
            .as_posix()
        )

    except ValueError:
        return str(
            path.resolve()
        )


# ============================================================
# VIDEO FINDING
# ============================================================

def find_video(
    category,
    product_id
):
    """
    Tìm video cuối theo cấu trúc:

        videos/{category}/{product_id}.mp4

    Vẫn giữ thứ tự ưu tiên cũ:

        1. {product_id}_merged.mp4
        2. {product_id}.mp4
    """

    category_video_dir = (
        VIDEO_ROOT
        / category
    )

    if not category_video_dir.exists():
        return None

    patterns = [
        f"{product_id}_merged.mp4",
        f"{product_id}.mp4",
    ]

    for pattern in patterns:
        video_path = (
            category_video_dir
            / pattern
        )

        if file_exists_and_not_empty(
            video_path
        ):
            return video_path

    return None


# ============================================================
# CAPTION
# ============================================================

def read_caption(product_dir):
    """
    Đọc caption từ folder sản phẩm:

        products/{category}/{product_id}/...
    """

    for relative_path in CAPTION_CANDIDATES:
        caption_file = (
            product_dir
            / relative_path
        )

        if (
            caption_file.exists()
            and caption_file.is_file()
        ):
            text = caption_file.read_text(
                encoding="utf-8"
            ).strip()

            if text:
                return text

    return ""


# ============================================================
# JOB ID
# ============================================================

def build_job_id(
    category,
    product_id
):
    return (
        f"{category}_"
        f"{product_id}_threads"
    )


# ============================================================
# PRODUCT DISCOVERY
# ============================================================

def discover_products():
    """
    Trả về danh sách:

        [
            ("lipstick", Path(.../LP001)),
            ("sandal", Path(.../SDL001)),
            ("keychain", Path(.../KC001)),
        ]
    """

    discovered = []

    for category in ENABLED_CATEGORIES:
        category_products_dir = (
            PRODUCTS_ROOT
            / category
        )

        if not category_products_dir.exists():
            print(
                "Category products directory not found:",
                category_products_dir
            )

            continue

        product_dirs = sorted(
            (
                path
                for path
                in category_products_dir.iterdir()
                if path.is_dir()
            ),
            key=lambda path: (
                path.name.lower()
            )
        )

        for product_dir in product_dirs:
            discovered.append(
                (
                    category,
                    product_dir
                )
            )

    return discovered


# ============================================================
# BUILD THREADS QUEUE
# ============================================================

def build_threads_queue():
    ensure_dirs()

    existing_rows = normalize_existing_rows(
        load_existing_queue()
    )

    existing_by_job_id = {
        row["job_id"]: row
        for row in existing_rows
        if row.get("job_id")
    }

    # Hỗ trợ queue cũ chưa có category.
    legacy_by_product_id = {
        row["product_id"]: row
        for row in existing_rows
        if (
            row.get("product_id")
            and not row.get("category")
        )
    }

    discovered_rows = []

    skipped_products = []

    used_existing_rows = set()

    if not PRODUCTS_ROOT.exists():
        print(
            f"Products directory not found: "
            f"{PRODUCTS_ROOT}"
        )

        return

    discovered_products = (
        discover_products()
    )

    for category, product_dir in discovered_products:
        product_id = (
            product_dir.name.strip()
        )

        if not product_id:
            continue

        video_path = find_video(
            category,
            product_id
        )

        if video_path is None:
            skipped_products.append(
                (
                    category,
                    product_id
                )
            )

            continue

        job_id = build_job_id(
            category,
            product_id
        )

        media_path = to_relative_path(
            video_path
        )

        caption = read_caption(
            product_dir
        )

        # ====================================================
        # GIỮ JOB CŨ THEO JOB ID MỚI
        # ====================================================

        if job_id in existing_by_job_id:
            row = existing_by_job_id[
                job_id
            ]

            used_existing_rows.add(
                id(row)
            )

            # Chỉ cập nhật dữ liệu nguồn.
            # Không reset status hoặc attempts.
            row["category"] = category
            row["product_id"] = product_id
            row["media_path"] = media_path

            if caption:
                row["caption"] = caption

            discovered_rows.append(
                row
            )

            continue

        # ====================================================
        # MIGRATE JOB CŨ CHƯA CÓ CATEGORY
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

            if caption:
                legacy_row["caption"] = caption

            discovered_rows.append(
                legacy_row
            )

            print(
                "Migrated legacy Threads job:",
                f"{category}/{product_id}"
            )

            continue

        # ====================================================
        # CREATE NEW JOB
        # ====================================================

        discovered_rows.append({
            "job_id": job_id,
            "category": category,
            "product_id": product_id,
            "media_path": media_path,
            "caption": caption,
            "status": "pending",
            "attempts": "0",
            "error": "",
            "updated_at": now_text(),
        })

    # ========================================================
    # KEEP OLD ORPHANED ROWS
    # ========================================================

    discovered_ids = {
        row["job_id"]
        for row in discovered_rows
    }

    orphaned_old_rows = [
        row
        for row in existing_rows
        if (
            id(row)
            not in used_existing_rows
            and row["job_id"]
            not in discovered_ids
        )
    ]

    all_rows = (
        discovered_rows
        + orphaned_old_rows
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

    save_queue(
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
        f"Threads queue created: "
        f"{QUEUE_FILE}"
    )

    print(
        "Products scanned:",
        len(discovered_products)
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
        len(orphaned_old_rows)
    )

    print(
        "Skipped without video:",
        len(skipped_products)
    )

    if skipped_products:
        print(
            "Skipped products:"
        )

        for category, product_id in skipped_products:
            print(
                f"  - {category}/{product_id}"
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
    build_threads_queue()