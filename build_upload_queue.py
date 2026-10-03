import csv
import os


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

VIDEOS_ROOT = os.path.join(
    BASE_DIR,
    "videos"
)

QUEUE_DIR = os.path.join(
    BASE_DIR,
    "queue"
)

UPLOAD_QUEUE_FILE = os.path.join(
    QUEUE_DIR,
    "upload_queue.csv"
)


# ============================================================
# CATEGORIES
# ============================================================

ENABLED_CATEGORIES = [
    "lipstick",
    "sandal",
]

# Chỉ tạo queue cho một category:
# ENABLED_CATEGORIES = ["lipstick"]
# ENABLED_CATEGORIES = ["sandal"]


# ============================================================
# QUEUE FIELDS
# ============================================================

FIELDNAMES = [
    "job_id",
    "category",
    "product_id",
    "video_path",
    "status",
    "error",
]


# ============================================================
# HELPERS
# ============================================================

def ensure_dirs():
    os.makedirs(
        QUEUE_DIR,
        exist_ok=True
    )

    os.makedirs(
        VIDEOS_ROOT,
        exist_ok=True
    )

    for category in ENABLED_CATEGORIES:
        category_video_dir = os.path.join(
            VIDEOS_ROOT,
            category
        )

        os.makedirs(
            category_video_dir,
            exist_ok=True
        )


def normalize_path(path):
    """
    Chuyển đường dẫn tuyệt đối thành đường dẫn tương đối.

    Ví dụ:

    videos/lipstick/LP001.mp4
    videos/sandal/SDL001.mp4
    """

    return (
        os.path.relpath(
            path,
            BASE_DIR
        )
        .replace("\\", "/")
    )


def resolve_path(path):
    """
    Chuyển đường dẫn trong queue thành đường dẫn tuyệt đối.
    """

    if not path:
        return ""

    path = str(path).strip()

    if os.path.isabs(path):
        return os.path.normpath(
            path
        )

    return os.path.normpath(
        os.path.join(
            BASE_DIR,
            path.replace("/", os.sep)
        )
    )


def file_exists_and_not_empty(path):
    return (
        os.path.isfile(path)
        and os.path.getsize(path) > 0
    )


# ============================================================
# QUEUE HANDLING
# ============================================================

def load_existing_queue():
    if not os.path.exists(
        UPLOAD_QUEUE_FILE
    ):
        return []

    with open(
        UPLOAD_QUEUE_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:
        return list(
            csv.DictReader(file)
        )


def save_queue(rows):
    temporary_file = (
        UPLOAD_QUEUE_FILE + ".temporary"
    )

    with open(
        temporary_file,
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
        temporary_file,
        UPLOAD_QUEUE_FILE
    )


# ============================================================
# VALIDATE EXISTING ROW
# ============================================================

def is_valid_existing_row(row):
    """
    Kiểm tra job cũ còn đúng với cấu trúc mới không.

    Cấu trúc mới:

    videos/{category}/{product_id}.mp4
    """

    category = (
        row.get("category")
        or ""
    ).strip()

    product_id = (
        row.get("product_id")
        or ""
    ).strip()

    video_path = (
        row.get("video_path")
        or ""
    ).strip()

    if not category:
        return False

    if category not in ENABLED_CATEGORIES:
        return False

    if not product_id:
        return False

    expected_video_path = (
        f"videos/{category}/{product_id}.mp4"
    )

    if video_path != expected_video_path:
        return False

    absolute_video_path = resolve_path(
        video_path
    )

    if not file_exists_and_not_empty(
        absolute_video_path
    ):
        return False

    return True


# ============================================================
# SCAN CATEGORY VIDEOS
# ============================================================

def get_category_videos(category):
    """
    Quét video cuối của một category.

    Ví dụ:

    videos/lipstick/LP001.mp4
    videos/sandal/SDL001.mp4
    """

    category_video_dir = os.path.join(
        VIDEOS_ROOT,
        category
    )

    if not os.path.isdir(
        category_video_dir
    ):
        return []

    video_files = [
        filename
        for filename in os.listdir(
            category_video_dir
        )
        if filename.lower().endswith(
            ".mp4"
        )
        and file_exists_and_not_empty(
            os.path.join(
                category_video_dir,
                filename
            )
        )
    ]

    video_files.sort(
        key=str.lower
    )

    return video_files


# ============================================================
# BUILD UPLOAD QUEUE
# ============================================================

def build_upload_queue():
    ensure_dirs()

    # --------------------------------------------------------
    # GIỮ NHỮNG JOB CŨ CÒN HỢP LỆ
    # --------------------------------------------------------

    valid_existing_rows = []

    for row in load_existing_queue():
        if is_valid_existing_row(
            row
        ):
            valid_existing_rows.append(
                row
            )

        else:
            category = (
                row.get("category")
                or "unknown"
            )

            product_id = (
                row.get("product_id")
                or "unknown"
            )

            print(
                "Remove invalid old row:",
                f"{category}/{product_id}"
            )

    # Phải dùng category + product_id làm khóa.
    # Không chỉ dùng product_id.
    existing_product_keys = {
        (
            row["category"],
            row["product_id"]
        )
        for row in valid_existing_rows
    }

    new_rows = []

    total_videos_scanned = 0

    # --------------------------------------------------------
    # QUÉT VIDEO THEO CATEGORY
    # --------------------------------------------------------

    for category in ENABLED_CATEGORIES:
        category_video_dir = os.path.join(
            VIDEOS_ROOT,
            category
        )

        print("=" * 50)
        print(
            "Scanning category:",
            category
        )
        print(
            "Video folder:",
            category_video_dir
        )

        video_files = get_category_videos(
            category
        )

        total_videos_scanned += len(
            video_files
        )

        print(
            "Videos found:",
            len(video_files)
        )

        for filename in video_files:
            product_id = os.path.splitext(
                filename
            )[0]

            product_key = (
                category,
                product_id
            )

            # Job đã tồn tại và vẫn hợp lệ.
            if (
                product_key
                in existing_product_keys
            ):
                print(
                    "Keep existing upload job:",
                    f"{category}/{product_id}"
                )

                continue

            video_path_abs = os.path.join(
                category_video_dir,
                filename
            )

            row = {
                "job_id": (
                    f"u_{category}_{product_id}"
                ),
                "category": category,
                "product_id": product_id,
                "video_path": normalize_path(
                    video_path_abs
                ),
                "status": "pending",
                "error": "",
            }

            new_rows.append(
                row
            )

            print(
                "Added upload job:",
                row["job_id"]
            )

    # --------------------------------------------------------
    # GỘP QUEUE
    # --------------------------------------------------------

    all_rows = (
        valid_existing_rows
        + new_rows
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
        )
    )

    save_queue(
        all_rows
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    lipstick_jobs = sum(
        1
        for row in all_rows
        if row.get("category") == "lipstick"
    )

    sandal_jobs = sum(
        1
        for row in all_rows
        if row.get("category") == "sandal"
    )

    pending_jobs = sum(
        1
        for row in all_rows
        if (
            row.get("status", "")
            .strip()
            .lower()
            == "pending"
        )
    )

    done_jobs = sum(
        1
        for row in all_rows
        if (
            row.get("status", "")
            .strip()
            .lower()
            == "done"
        )
    )

    print("=" * 50)
    print(
        "Upload queue created:",
        UPLOAD_QUEUE_FILE
    )
    print(
        "Videos scanned:",
        total_videos_scanned
    )
    print(
        "Valid existing jobs:",
        len(valid_existing_rows)
    )
    print(
        "New jobs added:",
        len(new_rows)
    )
    print(
        "Lipstick jobs:",
        lipstick_jobs
    )
    print(
        "Sandal jobs:",
        sandal_jobs
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
        "Total jobs:",
        len(all_rows)
    )
    print("=" * 50)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    build_upload_queue()