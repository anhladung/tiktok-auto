import csv
import glob
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

PROMPTS_ROOT = os.path.join(
    BASE_DIR,
    "prompts"
)

QUEUE_DIR = os.path.join(
    BASE_DIR,
    "queue"
)

QUEUE_FILE = os.path.join(
    QUEUE_DIR,
    "render_queue.csv"
)

os.makedirs(
    QUEUE_DIR,
    exist_ok=True
)

# ============================================================
# CHANNEL CONFIG
# ============================================================

# Chỉ áp dụng nhân 5 channel cho keychain
KEYCHAIN_CHANNEL_COUNT = 5
DEFAULT_CHANNEL_COUNT = 1


# ============================================================
# CATEGORY CONFIG
# ============================================================

# Chạy son, dép, móc khóa, ốp lưng và khẩu trang
ENABLED_CATEGORIES = [
    "keychain",
]

# Test riêng:
# ENABLED_CATEGORIES = ["lipstick"]
# ENABLED_CATEGORIES = ["sandal"]
# ENABLED_CATEGORIES = ["keychain"]
# ENABLED_CATEGORIES = ["phone_case"]
# ENABLED_CATEGORIES = ["mask"]


CATEGORY_CONFIG = {
    # ========================================================
    # LIPSTICK
    # ========================================================
    "lipstick": {
        "products_dir": os.path.join(
            PRODUCTS_ROOT,
            "lipstick"
        ),

        "prompt_dir": os.path.join(
            PROMPTS_ROOT,
            "lipstick",
            "video_generation"
        ),

        "clips": [
            {
                "clip_index": "1",
                "start_image": "01_hand_holding.png",
                "end_image": "02_opened_product.png",
                "prompt_file": "clip_01_product_showcase.txt",
            },
            {
                "clip_index": "2",
                "start_image": "03_mid_swatch.png",
                "end_image": "04_final_swatch.png",
                "prompt_file": "clip_02_swatch.txt",
            },
        ],
    },

    # ========================================================
    # SANDAL
    # ========================================================
    "sandal": {
        "products_dir": os.path.join(
            PRODUCTS_ROOT,
            "sandal"
        ),

        "prompt_dir": os.path.join(
            PROMPTS_ROOT,
            "sandal",
            "video_generation"
        ),

        "clips": [
            {
                "clip_index": "1",
                "start_image": "01_hand_holding.png",
                "end_image": "02_product_closeup.png",
                "prompt_file": "clip_01_product_showcase.txt",
            },
            {
                "clip_index": "2",
                "start_image": "03_on_foot.png",
                "end_image": "04_on_foot_next_frame.png",
                "prompt_file": "clip_02_on_foot.txt",
            },
        ],
    },

    # ========================================================
    # KEYCHAIN
    # ========================================================
    "keychain": {
        "products_dir": os.path.join(
            PRODUCTS_ROOT,
            "keychain"
        ),

        "prompt_dir": os.path.join(
            PROMPTS_ROOT,
            "keychain",
            "video_generation"
        ),

        "clips": [
            {
                # Pipeline mới chỉ còn 1 clip.
                # Giữ semantics clip 02:
                # 03_hand_holding -> 04_hand_holding_next_frame.
                "clip_index": "2",
                "start_image": "03_hand_holding.png",
                "end_image": "04_hand_holding_next_frame.png",
                "prompt_file": "clip_02_hand_holding.txt",
            },
        ],
    },

    # ========================================================
    # PHONE CASE
    # ========================================================
    "phone_case": {
        "products_dir": os.path.join(
            PRODUCTS_ROOT,
            "phone_case"
        ),

        "prompt_dir": os.path.join(
            PROMPTS_ROOT,
            "phone_case",
            "video_generation"
        ),

        "clips": [
            {
                # Pipeline mới chỉ còn 2 frame / 1 clip.
                "clip_index": "1",
                "start_image": "01_clip_01_first_frame.png",
                "end_image": "02_clip_01_last_frame.png",
                "prompt_file": "clip_01_installed_showcase.txt",
            },
        ],
    },

    # ========================================================
    # MASK
    # ========================================================
    "mask": {
        "products_dir": os.path.join(
            PRODUCTS_ROOT,
            "mask"
        ),

        "prompt_dir": os.path.join(
            PROMPTS_ROOT,
            "mask",
            "video_generation"
        ),

        "clips": [
            {
                # Mask chỉ có 1 clip:
                # side / 3-4 view -> front view.
                "clip_index": "1",
                "start_image": "01_side_view.png",
                "end_image": "02_front_view.png",
                "prompt_file": "clip_01_showcase.txt",
            },
        ],
    },
}


# ============================================================
# CSV FIELDS
# ============================================================

FIELDNAMES = [
    "job_id",
    "category",
    "product_id",
    "channel",
    "clip_index",
    "start_image",
    "end_image",
    "prompt_file",
    "status",
    "attempts",
    "profile",
    "video_path",
    "error",
    "updated_at",
]


# ============================================================
# HELPERS
# ============================================================

def file_exists_and_not_empty(file_path):
    return (
        os.path.isfile(file_path)
        and os.path.getsize(file_path) > 0
    )


def get_product_ids(products_dir):
    """
    Lấy danh sách mã sản phẩm trong một category.

    Ví dụ:
        products/lipstick/LP001
        products/sandal/SDL001
        products/keychain/KC001
        products/phone_case/PC001
        products/mask/MSK001
    """

    if not os.path.isdir(products_dir):
        return []

    product_ids = [
        name
        for name in os.listdir(products_dir)
        if os.path.isdir(
            os.path.join(
                products_dir,
                name
            )
        )
    ]

    product_ids.sort(
        key=str.lower
    )

    return product_ids


def find_existing_video(
    video_dir,
    product_id,
    channel_id,
    clip_number
):
    """
    Tìm video render đã tồn tại.

    Ví dụ:

        LP010_clip_01.mp4
        LP010_clip_01_20260710_113841.mp4

        SDL001_clip_02.mp4
        SDL001_clip_02_20260710_113841.mp4

        KC001_clip_02.mp4
        KC001_clip_02_20260710_113841.mp4

        PC001_clip_01.mp4
        PC001_clip_01_20260710_113841.mp4

        MSK001_clip_01.mp4
        MSK001_clip_01_20260710_113841.mp4
    """

    pattern = os.path.join(
        video_dir,
        (
            f"{product_id}_"
            f"CH{channel_id}_"
            f"clip_{clip_number}*.mp4"
        )
    )

    files = [
        file_path
        for file_path in glob.glob(pattern)
        if file_exists_and_not_empty(
            file_path
        )
    ]

    if not files:
        return None

    # Lấy video mới nhất.
    files.sort(
        key=os.path.getmtime,
        reverse=True
    )

    return files[0]


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

    prompt_dir = category_config[
        "prompt_dir"
    ]

    clips = category_config[
        "clips"
    ]

    print("=" * 60)
    print(
        "Category:",
        category
    )
    print(
        "Products:",
        products_dir
    )
    print(
        "Prompts:",
        prompt_dir
    )

    if not os.path.isdir(
        products_dir
    ):
        print(
            "Skip category — products folder "
            f"not found: {products_dir}"
        )

        return rows, 0

    product_ids = get_product_ids(
        products_dir
    )

    print(
        "Products found:",
        len(product_ids)
    )

    for product_id in product_ids:
        product_dir = os.path.join(
            products_dir,
            product_id
        )

        ai_root_dir = os.path.join(
            product_dir,
            "images",
            "ai"
        )

        # Keychain pipeline mới:
        # mỗi channel có folder riêng:
        #
        # images/ai/channel_1/
        # images/ai/channel_2/
        # ...
        #
        # Category khác vẫn dùng:
        #
        # images/ai/

        channel_count = (
            KEYCHAIN_CHANNEL_COUNT
            if category == "keychain"
            else DEFAULT_CHANNEL_COUNT
        )

        valid_channels = []

        for channel_index in range(1, channel_count + 1):

            if category == "keychain":
                channel_ai_dir = os.path.join(
                    ai_root_dir,
                    f"channel_{channel_index}"
                )
            else:
                channel_ai_dir = ai_root_dir

            required_images = {
                image_name
                for clip in clips
                for image_name in [
                    clip["start_image"],
                    clip["end_image"],
                ]
            }

            missing_images = [
                image_name
                for image_name in sorted(
                    required_images
                )
                if not file_exists_and_not_empty(
                    os.path.join(
                        channel_ai_dir,
                        image_name
                    )
                )
            ]

            if missing_images:
                print(
                    f"Skip {category}/{product_id}/CH{channel_index} "
                    f"— missing images: "
                    f"{', '.join(missing_images)}"
                )

                continue

            valid_channels.append(
                (
                    str(channel_index).zfill(2),
                    channel_ai_dir
                )
            )

        if not valid_channels:
            continue

        # Kiểm tra prompt cho từng clip.
        missing_prompts = []

        for clip in clips:
            prompt_path = os.path.join(
                prompt_dir,
                clip["prompt_file"]
            )

            if not file_exists_and_not_empty(
                prompt_path
            ):
                missing_prompts.append(
                    clip["prompt_file"]
                )

        if missing_prompts:
            print(
                f"Skip {category}/{product_id} "
                f"— missing prompts: "
                f"{', '.join(missing_prompts)}"
            )

            continue

        video_dir = os.path.join(
            product_dir,
            "output",
            "videos"
        )

        os.makedirs(
            video_dir,
            exist_ok=True
        )

        for channel_id, ai_dir in valid_channels:

            for clip in clips:
                clip_number = (
                    str(clip["clip_index"])
                    .zfill(2)
                )

                start_image_path = os.path.join(
                    ai_dir,
                    clip["start_image"]
                )

                end_image_path = os.path.join(
                    ai_dir,
                    clip["end_image"]
                )

                prompt_path = os.path.join(
                    prompt_dir,
                    clip["prompt_file"]
                )

                existing_video = find_existing_video(
                    video_dir=video_dir,
                    product_id=product_id,
                    channel_id=channel_id,
                    clip_number=clip_number
                )

                if existing_video:
                    status = "done"
                    video_path = existing_video

                else:
                    status = "pending"

                    video_path = os.path.join(
                        video_dir,
                        (
                            f"{product_id}_"
                            f"CH{channel_id}_"
                            f"clip_{clip_number}.mp4"
                        )
                    )

                job_id = (
                    f"{category}_"
                    f"{product_id}_"
                    f"CH{channel_id}_"
                    f"clip_{clip_number}"
                )

                rows.append({
                    "job_id": job_id,
                    "category": category,
                    "product_id": product_id,
                    "channel": channel_id,
                    "clip_index": clip["clip_index"],
                    "start_image": start_image_path,
                    "end_image": end_image_path,
                    "prompt_file": prompt_path,
                    "status": status,
                    "attempts": "0",
                    "profile": "",
                    "video_path": video_path,
                    "error": "",
                    "updated_at": "",
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
                "Skip — category config "
                f"not found: {category}"
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
            int(row.get("channel", "0")),
            int(row["clip_index"]),
        )
    )

    return rows, total_scanned_products


# ============================================================
# SAVE QUEUE
# ============================================================

def save_queue(rows):
    temporary_file = (
        QUEUE_FILE + ".temporary"
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

    queued_product_count = len({
        (
            row["category"],
            row["product_id"]
        )
        for row in rows
    })

    lipstick_jobs = sum(
        1
        for row in rows
        if row["category"] == "lipstick"
    )

    sandal_jobs = sum(
        1
        for row in rows
        if row["category"] == "sandal"
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

    mask_jobs = sum(
        1
        for row in rows
        if row["category"] == "mask"
    )

    print("=" * 60)
    print(
        "Render queue generated."
    )
    print(
        "Products scanned:",
        total_scanned_products
    )
    print(
        "Products queued:",
        queued_product_count
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
        "Keychain jobs:",
        keychain_jobs
    )
    print(
        "Phone case jobs:",
        phone_case_jobs
    )
    print(
        "Mask jobs:",
        mask_jobs
    )
    print(
        "Jobs:",
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

    save_queue(
        rows
    )

    print_summary(
        rows=rows,
        total_scanned_products=total_scanned_products
    )


if __name__ == "__main__":
    main()