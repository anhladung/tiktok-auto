import csv
import os


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

PRODUCTS_ROOT = os.path.join(
    BASE_DIR,
    "products"
)

QUEUE_DIR = os.path.join(
    BASE_DIR,
    "queue"
)

VOICE_QUEUE_FILE = os.path.join(
    QUEUE_DIR,
    "voice_queue.csv"
)


# ============================================================
# CATEGORIES
# ============================================================

ENABLED_CATEGORIES = [
    "snack",
    "keychain",
    "phone_case",
]

# Chạy riêng một loại để kiểm tra:
# ENABLED_CATEGORIES = ["snack"]
# ENABLED_CATEGORIES = ["keychain"]
# ENABLED_CATEGORIES = ["phone_case"]


# ============================================================
# QUEUE FIELDS
# ============================================================

FIELDNAMES = [
    "job_id",
    "category",
    "product_id",
    "script_path",
    "output_audio_path",
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


def normalize_path(path):
    """
    Chuyển đường dẫn tuyệt đối thành đường dẫn tương đối
    tính từ folder project.

    Ví dụ:

    products/lipstick/LP001/output/scripts/LP001.txt
    products/sandal/SDL001/output/audio/SDL001.mp3
    products/keychain/KC001/output/scripts/KC001.txt
    products/phone_case/PC001/output/scripts/PC001.txt
    products/phone_case/PC001/output/audio/PC001.mp3
    products/mask/MSK001/output/scripts/MSK001.txt
    products/mask/MSK001/output/audio/MSK001.mp3
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
    Chuyển đường dẫn tương đối trong queue
    thành đường dẫn tuyệt đối.
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
        VOICE_QUEUE_FILE
    ):
        return []

    with open(
        VOICE_QUEUE_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:
        return list(
            csv.DictReader(file)
        )


def save_queue(rows):
    temporary_file = (
        VOICE_QUEUE_FILE + ".temporary"
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
        VOICE_QUEUE_FILE
    )


# ============================================================
# EXISTING ROW VALIDATION
# ============================================================

def is_valid_existing_row(row):
    """
    Kiểm tra job cũ còn đúng với cấu trúc mới hay không.

    Cấu trúc mới:

    products/{category}/{product_id}/output/scripts/{product_id}.txt
    products/{category}/{product_id}/output/audio/{product_id}.mp3
    """

    category = (
        row.get("category")
        or ""
    ).strip()

    product_id = (
        row.get("product_id")
        or ""
    ).strip()

    script_path = (
        row.get("script_path")
        or ""
    ).strip()

    output_audio_path = (
        row.get("output_audio_path")
        or ""
    ).strip()

    if not category:
        return False

    if category not in ENABLED_CATEGORIES:
        return False

    if not product_id:
        return False

    expected_script_path = (
        f"products/{category}/{product_id}/"
        f"output/scripts/{product_id}.txt"
    )

    expected_audio_path = (
        f"products/{category}/{product_id}/"
        f"output/audio/{product_id}.mp3"
    )

    if script_path != expected_script_path:
        return False

    if output_audio_path != expected_audio_path:
        return False

    absolute_script_path = resolve_path(
        script_path
    )

    if not file_exists_and_not_empty(
        absolute_script_path
    ):
        return False

    return True


# ============================================================
# PRODUCT SCANNING
# ============================================================

def get_product_ids(category):
    category_products_dir = os.path.join(
        PRODUCTS_ROOT,
        category
    )

    if not os.path.isdir(
        category_products_dir
    ):
        return []

    product_ids = [
        name
        for name in os.listdir(
            category_products_dir
        )
        if os.path.isdir(
            os.path.join(
                category_products_dir,
                name
            )
        )
    ]

    product_ids.sort(
        key=str.lower
    )

    return product_ids


# ============================================================
# BUILD VOICE QUEUE
# ============================================================

def build_voice_queue():
    ensure_dirs()

    # --------------------------------------------------------
    # Giữ lại những row cũ vẫn hợp lệ
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

    # Dùng category + product_id làm khóa,
    # tránh trùng nếu hai category có cùng product_id.
    existing_product_keys = {
        (
            row["category"],
            row["product_id"]
        )
        for row in valid_existing_rows
    }

    new_rows = []

    total_products_scanned = 0

    # --------------------------------------------------------
    # Quét từng category
    # --------------------------------------------------------

    for category in ENABLED_CATEGORIES:
        category_products_dir = os.path.join(
            PRODUCTS_ROOT,
            category
        )

        print("=" * 50)
        print(
            "Scanning category:",
            category
        )

        if not os.path.isdir(
            category_products_dir
        ):
            print(
                "Products folder not found:",
                category_products_dir
            )

            continue

        product_ids = get_product_ids(
            category
        )

        total_products_scanned += len(
            product_ids
        )

        print(
            "Products found:",
            len(product_ids)
        )

        for product_id in product_ids:
            product_key = (
                category,
                product_id
            )

            product_dir_abs = os.path.join(
                category_products_dir,
                product_id
            )

            # Job đã có trong queue và vẫn hợp lệ.
            if (
                product_key
                in existing_product_keys
            ):
                print(
                    "Keep existing voice job:",
                    f"{category}/{product_id}"
                )

                continue

            # ------------------------------------------------
            # Script đầu vào
            # ------------------------------------------------

            script_path_abs = os.path.join(
                product_dir_abs,
                "output",
                "scripts",
                f"{product_id}.txt"
            )

            if not file_exists_and_not_empty(
                script_path_abs
            ):
                print(
                    "Skip missing script:",
                    f"{category}/{product_id}"
                )

                continue

            # ------------------------------------------------
            # Audio đầu ra
            # ------------------------------------------------

            output_audio_dir_abs = os.path.join(
                product_dir_abs,
                "output",
                "audio"
            )

            output_audio_path_abs = os.path.join(
                output_audio_dir_abs,
                f"{product_id}.mp3"
            )

            os.makedirs(
                output_audio_dir_abs,
                exist_ok=True
            )

            # Giữ nguyên logic cũ:
            # audio đã có thì không tạo job mới.
            if file_exists_and_not_empty(
                output_audio_path_abs
            ):
                print(
                    "Skip existing audio:",
                    f"{category}/{product_id}"
                )

                continue

            # ------------------------------------------------
            # Tạo job mới
            # ------------------------------------------------

            row = {
                "job_id": (
                    f"v_{category}_{product_id}"
                ),
                "category": category,
                "product_id": product_id,
                "script_path": normalize_path(
                    script_path_abs
                ),
                "output_audio_path": normalize_path(
                    output_audio_path_abs
                ),
                "status": "pending",
                "error": "",
            }

            new_rows.append(
                row
            )

            print(
                "Added voice job:",
                row["job_id"]
            )

    # --------------------------------------------------------
    # Gộp queue cũ hợp lệ và job mới
    # --------------------------------------------------------

    all_rows = (
        valid_existing_rows
        + new_rows
    )

    save_queue(
        all_rows
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    snack_jobs = sum(
        1
        for row in all_rows
        if row.get("category") == "snack"
    )

    keychain_jobs = sum(
        1
        for row in all_rows
        if row.get("category") == "keychain"
    )

    phone_case_jobs = sum(
        1
        for row in all_rows
        if row.get("category") == "phone_case"
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
        "Voice queue created:",
        VOICE_QUEUE_FILE
    )
    print(
        "Products scanned:",
        total_products_scanned
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
        "Total jobs:",
        len(all_rows)
    )
    print("=" * 50)


if __name__ == "__main__":
    build_voice_queue()
