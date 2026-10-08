import csv
import os


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

PRODUCTS_ROOT_DIR = os.path.join(
    BASE_DIR,
    "products"
)

PROMPTS_ROOT_DIR = os.path.join(
    BASE_DIR,
    "prompts"
)

QUEUE_DIR = os.path.join(
    BASE_DIR,
    "queue"
)

QUEUE_FILE = os.path.join(
    QUEUE_DIR,
    "script_queue.csv"
)


# ============================================================
# CATEGORY CONFIG
# ============================================================

# Chạy đồ ăn vặt, móc khóa, ốp lưng
ENABLED_CATEGORIES = [
    "snack",
    "keychain",
    "phone_case",
]

# Test riêng:
# ENABLED_CATEGORIES = ["snack"]
# ENABLED_CATEGORIES = ["keychain"]
# ENABLED_CATEGORIES = ["phone_case"]


CATEGORY_CONFIG = {
    # ========================================================
    # SNACK (ĐỒ ĂN VẶT)
    # ========================================================
    "snack": {
        "products_dir": os.path.join(
            PRODUCTS_ROOT_DIR,
            "snack"
        ),

        "prompt_file": os.path.join(
            PROMPTS_ROOT_DIR,
            "snack",
            "script_generation",
            "snack_script.txt"
        ),

        # Dùng Frame 01 là ảnh cầm sản phẩm trên tay
        # làm input duy nhất cho script generation.
        "script_images": [
            "01_hand_holding.png",
        ],
    },

    # ========================================================
    # KEYCHAIN
    # ========================================================
    "keychain": {
        "products_dir": os.path.join(
            PRODUCTS_ROOT_DIR,
            "keychain"
        ),

        "prompt_file": os.path.join(
            PROMPTS_ROOT_DIR,
            "keychain",
            "script_generation",
            "keychain_script.txt"
        ),

        # Pipeline mới của keychain chỉ còn 1 clip.
        # Dùng Frame 03 là ảnh cầm móc khóa trên tay
        # làm input duy nhất cho script generation.
        "script_images": [
            "03_hand_holding.png",
        ],
    },

    # ========================================================
    # PHONE CASE
    # ========================================================
    "phone_case": {
        "products_dir": os.path.join(
            PRODUCTS_ROOT_DIR,
            "phone_case"
        ),

        "prompt_file": os.path.join(
            PROMPTS_ROOT_DIR,
            "phone_case",
            "script_generation",
            "phone_case_script.txt"
        ),

        # Pipeline mới chỉ còn 2 frame / 1 clip.
        # Dùng Frame 01 làm ảnh đại diện cho script generation.
        "script_images": [
            "01_clip_01_first_frame.png",
        ],
    },
}


# ============================================================
# QUEUE COLUMNS
# ============================================================

QUEUE_FIELDNAMES = [
    "job_id",
    "category",
    "product_id",
    "status",
    "attempts",
    "prompt_file",
    "image_1",
    "image_2",
    "output",
    "error",
]


IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


# ============================================================
# FILE HELPERS
# ============================================================

def file_exists_and_not_empty(file_path):
    """
    Kiểm tra file có tồn tại và không rỗng.
    """

    return (
        os.path.isfile(file_path)
        and os.path.getsize(file_path) > 0
    )


def get_first_image_in_folder(folder_path):
    """
    Lấy ảnh đầu tiên trong folder theo thứ tự tên file.
    """

    if not os.path.isdir(folder_path):
        return ""

    image_files = [
        file_name
        for file_name in os.listdir(folder_path)
        if (
            os.path.isfile(
                os.path.join(
                    folder_path,
                    file_name
                )
            )
            and os.path.splitext(
                file_name
            )[1].lower()
            in IMAGE_EXTENSIONS
        )
    ]

    image_files.sort(
        key=str.lower
    )

    if not image_files:
        return ""

    return os.path.join(
        folder_path,
        image_files[0]
    )


def get_product_directories(products_dir):
    """
    Lấy danh sách mã sản phẩm trong một category.

    Ví dụ:

    products/lipstick/
        LP001
        LP002

    products/sandal/
        SDL001
        SDL002

    products/keychain/
        KC001
        KC002

    products/phone_case/
        PC001
        PC002

    products/mask/
        MSK001
        MSK002
    """

    if not os.path.isdir(products_dir):
        return []

    product_ids = [
        product_id
        for product_id in os.listdir(products_dir)
        if os.path.isdir(
            os.path.join(
                products_dir,
                product_id
            )
        )
    ]

    product_ids.sort(
        key=str.lower
    )

    return product_ids


# ============================================================
# BUILD CATEGORY ROWS
# ============================================================

def build_category_rows(
    category,
    category_config
):
    rows = []

    products_dir = category_config[
        "products_dir"
    ]

    prompt_file = category_config[
        "prompt_file"
    ]

    script_image_source = category_config.get(
        "script_image_source",
        "ai"
    )

    script_images = category_config.get(
        "script_images",
        []
    )

    print("=" * 60)
    print(
        f"Category: {category}"
    )
    print(
        f"Products: {products_dir}"
    )
    print(
        f"Prompt:   {prompt_file}"
    )

    # Hỗ trợ category dùng 1 hoặc 2 ảnh:
    # - lipstick: 2 ảnh
    # - sandal: 1 ảnh
    # - keychain: 1 ảnh
    # - phone_case: 1 ảnh
    # - mask: 1 ảnh
    if (
        script_image_source == "ai"
        and len(script_images) not in (1, 2)
    ):
        raise ValueError(
            f"Category '{category}' phải có "
            f"1 hoặc 2 script_images."
        )

    if not os.path.isdir(products_dir):
        print(
            f"Skip category. Products folder "
            f"not found: {products_dir}"
        )

        return rows, 0

    if not file_exists_and_not_empty(
        prompt_file
    ):
        raise FileNotFoundError(
            f"Prompt file not found or empty "
            f"for category '{category}': "
            f"{prompt_file}"
        )

    product_ids = get_product_directories(
        products_dir
    )

    print(
        "Found products:",
        len(product_ids)
    )

    for product_id in product_ids:
        product_dir = os.path.join(
            products_dir,
            product_id
        )

        ai_dir = os.path.join(
            product_dir,
            "images",
            "ai"
        )

        if script_image_source == "raw_product":
            raw_product_dir = os.path.join(
                product_dir,
                "images",
                "raw",
                "product"
            )

            image_1 = get_first_image_in_folder(
                raw_product_dir
            )

            image_2 = ""

        else:
            image_1 = os.path.join(
                ai_dir,
                script_images[0]
            )

            image_2 = (
                os.path.join(
                    ai_dir,
                    script_images[1]
                )
                if len(script_images) > 1
                else ""
            )

        script_dir = os.path.join(
            product_dir,
            "output",
            "scripts"
        )

        os.makedirs(
            script_dir,
            exist_ok=True
        )

        output_file = os.path.join(
            script_dir,
            f"{product_id}.txt"
        )

        missing_images = []

        if not file_exists_and_not_empty(
            image_1
        ):
            if script_image_source == "raw_product":
                missing_images.append(
                    "raw product image"
                )
            else:
                missing_images.append(
                    script_images[0]
                )

        if (
            script_image_source == "ai"
            and len(script_images) > 1
            and not file_exists_and_not_empty(
                image_2
            )
        ):
            missing_images.append(
                script_images[1]
            )

        if missing_images:
            print(
                f"Skip {category}/{product_id} "
                f"— missing: "
                f"{', '.join(missing_images)}"
            )

            continue

        if file_exists_and_not_empty(
            output_file
        ):
            status = "done"
        else:
            status = "pending"

        job_id = (
            f"{category}_"
            f"{product_id}_script"
        )

        rows.append({
            "job_id": job_id,
            "category": category,
            "product_id": product_id,
            "status": status,
            "attempts": "0",
            "prompt_file": prompt_file,
            "image_1": image_1,
            "image_2": image_2 if image_2 else "",
            "output": output_file,
            "error": "",
        })

        print(
            f"Added job: {job_id} "
            f"[{status}]"
        )

    return rows, len(product_ids)


# ============================================================
# BUILD ALL ROWS
# ============================================================

def build_rows():
    rows = []

    total_scanned_products = 0

    for category in ENABLED_CATEGORIES:
        category_config = CATEGORY_CONFIG.get(
            category
        )

        if category_config is None:
            print(
                f"Skip. Category config not found: "
                f"{category}"
            )

            continue

        category_rows, scanned_count = (
            build_category_rows(
                category=category,
                category_config=category_config
            )
        )

        rows.extend(
            category_rows
        )

        total_scanned_products += (
            scanned_count
        )

    rows.sort(
        key=lambda row: (
            row["category"].lower(),
            row["product_id"].lower(),
        )
    )

    return rows, total_scanned_products


# ============================================================
# SAVE CSV
# ============================================================

def save_csv(rows):
    os.makedirs(
        QUEUE_DIR,
        exist_ok=True
    )

    temporary_file = (
        QUEUE_FILE + ".temporary"
    )

    with open(
        temporary_file,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=QUEUE_FIELDNAMES,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(rows)

    os.replace(
        temporary_file,
        QUEUE_FILE
    )


# ============================================================
# SUMMARY
# ============================================================

def print_summary(
    rows,
    total_scanned_products
):
    done_jobs = sum(
        1
        for row in rows
        if row["status"] == "done"
    )

    pending_jobs = sum(
        1
        for row in rows
        if row["status"] == "pending"
    )

    snack_jobs = sum(
        1
        for row in rows
        if row["category"] == "snack"
    )

    keychain_jobs = sum(
        1
        for row in rows
        if row["category"] == "keychain"
    )

    phone_case_jobs = sum(
        1
        for row in rows
        if row["category"] == "phone_case"
    )

    queued_products = len({
        (
            row["category"],
            row["product_id"]
        )
        for row in rows
    })

    print("=" * 60)
    print(
        "Script queue created."
    )
    print(
        "Products scanned:",
        total_scanned_products
    )
    print(
        "Products queued:",
        queued_products
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
        "Total jobs:",
        len(rows)
    )
    print(
        "Done:",
        done_jobs
    )
    print(
        "Pending:",
        pending_jobs
    )
    print(
        "Saved:",
        QUEUE_FILE
    )
    print("=" * 60)


# ============================================================
# MAIN
# ============================================================

def main():
    rows, total_scanned_products = (
        build_rows()
    )

    save_csv(
        rows
    )

    print_summary(
        rows=rows,
        total_scanned_products=total_scanned_products
    )


if __name__ == "__main__":
    main()
