import csv
import os


# ============================================================
# PATHS
# ============================================================

QUEUE_DIR = "queue"

QUEUE_FILE = os.path.join(
    QUEUE_DIR,
    "image_queue.csv"
)

SUPPORTED_IMAGE_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
)

os.makedirs(
    QUEUE_DIR,
    exist_ok=True
)


# ============================================================
# CATEGORY SETTINGS
# ============================================================

# Khi muốn test riêng đồ ăn vặt:
# ENABLED_CATEGORIES = ["snack"]
#
# Khi muốn test riêng móc khóa:
# ENABLED_CATEGORIES = ["keychain"]
#
# Khi muốn test riêng ốp lưng:
# ENABLED_CATEGORIES = ["phone_case"]
#
# Khi muốn test riêng mắt kính:
# ENABLED_CATEGORIES = ["eyeglasses"]
#
# Khi chạy pipeline chung:
ENABLED_CATEGORIES = [
    "snack",
    "keychain",
    "phone_case",
    "eyeglasses",
    "shoes",
]


CATEGORY_CONFIG = {
    # ========================================================
    # SNACK (ĐỒ ĂN VẶT)
    # ========================================================
    "snack": {
        "products_dir": os.path.join(
            "products",
            "snack"
        ),

        "product_inputs": {
            "product_image": os.path.join(
                "images",
                "raw",
                "product"
            ),
        },

        "shared_inputs": {
            "background_image": {
                "folder": os.path.join(
                    "references",
                    "snack",
                    "backgrounds"
                ),
                "mode": "first",
            },
        },

        "steps": [
            {
                "step": "01_hand_holding",
                "step_order": 1,
                "output_key": "frame_01",
                "output_filename": "01_hand_holding.png",
                "input_1": "{product_image}",
                "input_2": "{background_image}",
            },
        ],
    },

    # ========================================================
    # KEYCHAIN (1 CHANNEL DUY NHẤT VỚI BACKGROUND SỐ 1)
    # ========================================================
    "keychain": {
        "products_dir": os.path.join(
            "products",
            "keychain"
        ),

        "product_inputs": {
            "product_image": os.path.join(
                "images",
                "raw",
                "product"
            ),
        },

        "shared_inputs": {
            # Sử dụng background số 1 duy nhất
            "hand_background": {
                "folder": os.path.join(
                    "references",
                    "keychain",
                    "backgrounds"
                ),
                "mode": "named",
                "name": "1",
            },
        },

        "steps": [
            {
                "step": "03_hand_holding",
                "step_order": 1,
                "output_key": "frame_03",
                "output_filename": "03_hand_holding.png",

                # Ảnh sản phẩm + lifestyle hand background số 1
                "input_1": "{product_image}",
                "input_2": "{hand_background}",
            },
            {
                "step": "04_hand_holding_next_frame",
                "step_order": 2,
                "output_key": "frame_04",
                "output_filename": "04_hand_holding_next_frame.png",

                # Chuyển động nối tiếp Frame 03
                "input_1": "{frame_03}",
                "input_2": "",
            },
        ],
    },

    # ========================================================
    # PHONE CASE (2 FRAMES / 1 CLIP ONLY)
    # ========================================================
    "phone_case": {
        "products_dir": os.path.join(
            "products",
            "phone_case"
        ),

        "product_inputs": {
            "product_image": os.path.join(
                "images",
                "raw",
                "product"
            ),
        },

        "shared_inputs": {
            # Background desk setup
            "desk_background": {
                "folder": os.path.join(
                    "references",
                    "phone_case",
                    "backgrounds"
                ),
                "mode": "first",
            },
        },

        "steps": [
            {
                "step": "01_clip_01_first_frame",
                "step_order": 1,
                "output_key": "frame_01",
                "output_filename": "01_clip_01_first_frame.png",

                "input_1": "{product_image}",
                "input_2": "{desk_background}",
            },
            {
                "step": "02_clip_01_last_frame",
                "step_order": 2,
                "output_key": "frame_02",
                "output_filename": "02_clip_01_last_frame.png",

                "input_1": "{frame_01}",
                "input_2": "",
            },
        ],
    },

    # ========================================================
    # EYEGLASSES (2 FRAMES / 1 CLIP, MULTI-CHANNEL BACKGROUNDS)
    # ========================================================
    "eyeglasses": {
        "products_dir": os.path.join(
            "products",
            "eyeglasses"
        ),

        "product_inputs": {
            # Ảnh sản phẩm kính gốc.
            "product_image": os.path.join(
                "images",
                "raw",
                "product"
            ),
        },

        "shared_inputs": {
            # Dùng để validate rằng thư mục background không rỗng.
            # Channel mode sẽ thay hand_background bằng từng ảnh 1.*, 2.* ...
            "hand_background": {
                "folder": os.path.join(
                    "references",
                    "eyeglasses",
                    "backgrounds"
                ),
                "mode": "first",
            },
        },

        # Mỗi background có tên số tạo một variation/channel riêng.
        "channel_backgrounds": {
            "folder": os.path.join(
                "references",
                "eyeglasses",
                "backgrounds"
            ),
            "context_key": "hand_background",
        },

        "steps": [
            {
                # Frame đầu: ảnh sản phẩm kính + background aesthetic.
                "step": "01_hand_holding",
                "step_order": 1,
                "output_key": "frame_01",
                "output_filename": "01_hand_holding.png",

                "input_1": "{product_image}",
                "input_2": "{hand_background}",
            },
            {
                # Frame cuối: chuyển động nối tiếp, đưa kính gần camera hơn.
                # Chỉ dùng Frame 01 để ưu tiên continuity tuyệt đối.
                "step": "02_closeup",
                "step_order": 2,
                "output_key": "frame_02",
                "output_filename": "02_closeup.png",

                "input_1": "{frame_01}",
                "input_2": "",
            },
        ],
    },
    # ========================================================
    # SHOES (GIÀY: 2 FRAMES / 1 CLIP)
    # ========================================================
    "shoes": {
        "products_dir": os.path.join(
            "products",
            "shoes"
        ),

        "product_inputs": {
            "product_image": os.path.join(
                "images",
                "raw",
                "product"
            ),
        },

        "shared_inputs": {
            "lifestyle_background": {
                "folder": os.path.join(
                    "references",
                    "shoes",
                    "backgrounds"
                ),
                "mode": "first",
            },
        },

        "steps": [
            {
                "step": "01_crossed_legs",
                "step_order": 1,
                "output_key": "frame_01",
                "output_filename": "01_crossed_legs.png",
                "input_1": "{product_image}",
                "input_2": "{lifestyle_background}",
            },
            {
                "step": "02_both_feet_on_floor",
                "step_order": 2,
                "output_key": "frame_02",
                "output_filename": "02_both_feet_on_floor.png",
                "input_1": "{frame_01}",
                "input_2": "",
            },
        ],
    },
}


# ============================================================
# IMAGE HELPERS
# ============================================================

def is_supported_image(filename):
    return filename.lower().endswith(
        SUPPORTED_IMAGE_EXTENSIONS
    )


def get_first_image(folder):
    """
    Lấy ảnh đầu tiên trong folder.

    Hỗ trợ:
    - .png
    - .jpg
    - .jpeg
    - .webp
    """
    if not os.path.isdir(folder):
        return None

    images = sorted(
        [
            os.path.join(folder, filename)
            for filename in os.listdir(folder)
            if (
                os.path.isfile(
                    os.path.join(folder, filename)
                )
                and is_supported_image(filename)
            )
        ],
        key=lambda path: os.path.basename(path).lower()
    )

    if not images:
        return None

    return images[0]


def get_named_image(folder, image_name):
    """
    Tìm ảnh theo tên file nhưng không phụ thuộc phần mở rộng.

    Ví dụ image_name = "1" có thể tìm được:
    - 1.jpg
    - 1.jpeg
    - 1.png
    - 1.webp
    """
    if not os.path.isdir(folder):
        return None

    normalized_name = str(image_name).strip().lower()

    matches = sorted(
        [
            os.path.join(folder, filename)
            for filename in os.listdir(folder)
            if (
                os.path.isfile(
                    os.path.join(folder, filename)
                )
                and is_supported_image(filename)
                and os.path.splitext(filename)[0].lower()
                == normalized_name
            )
        ],
        key=lambda path: os.path.basename(path).lower()
    )

    if not matches:
        return None

    if len(matches) > 1:
        raise RuntimeError(
            "Multiple images found with the same name "
            f"'{image_name}' in '{folder}': {matches}"
        )

    return matches[0]


def resolve_shared_input(input_config):
    """
    Resolve một shared input từ config.

    mode = first:
        Lấy ảnh đầu tiên trong folder.

    mode = named:
        Tìm ảnh theo tên, không phụ thuộc extension.
    """
    folder = input_config["folder"]
    mode = input_config.get("mode", "first")

    if mode == "first":
        return get_first_image(folder)

    if mode == "named":
        image_name = input_config.get("name")

        if image_name is None:
            raise ValueError(
                f"Missing image name for shared input: {input_config}"
            )

        return get_named_image(
            folder,
            image_name
        )

    raise ValueError(
        f"Unsupported shared input mode: {mode}"
    )


def get_channel_backgrounds(folder):
    """
    Lấy background theo channel.

    Ví dụ:
    1.png
    2.jpg
    3.webp

    Trả về:
    [
        ("1", "path/1.png"),
        ("2", "path/2.jpg")
    ]
    """
    if not os.path.isdir(folder):
        return []

    backgrounds = []

    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)

        if not os.path.isfile(path):
            continue

        if not is_supported_image(filename):
            continue

        channel_id = os.path.splitext(filename)[0]

        if channel_id.isdigit():
            backgrounds.append(
                (
                    channel_id,
                    path
                )
            )

    return sorted(
        backgrounds,
        key=lambda item: int(item[0])
    )


# ============================================================
# QUEUE HELPERS
# ============================================================

def format_input(template, context):
    """
    Thay các placeholder như:
    {product_image}
    {frame_01}
    {desk_background}
    """
    if not template:
        return ""

    try:
        return template.format_map(context)
    except KeyError as error:
        missing_key = error.args[0]

        raise KeyError(
            f"Missing context value: {missing_key}"
        ) from error


def make_row(
    category,
    job_id,
    product_id,
    step,
    step_order,
    input_1,
    input_2,
    output,
    channel_id=""
):
    if os.path.exists(output):
        status = "done"
    else:
        status = "pending"

    return {
        "job_id": job_id,
        "category": category,
        "product_id": product_id,
        "channel_id": channel_id,
        "step": step,
        "step_order": step_order,
        "status": status,
        "attempts": 0,
        "input_1": input_1,
        "input_2": input_2,
        "output": output,
        "error": "",
    }


# ============================================================
# BUILD IMAGE QUEUE
# ============================================================

rows = []

for category in ENABLED_CATEGORIES:
    print("=" * 60)
    print("Category:", category)

    config = CATEGORY_CONFIG.get(category)

    if config is None:
        print(
            f"Skip. No category config found: {category}"
        )
        continue

    products_dir = config["products_dir"]

    if not os.path.isdir(products_dir):
        print(
            f"Skip. Products directory not found: "
            f"{products_dir}"
        )
        continue

    # --------------------------------------------------------
    # Resolve shared inputs của category
    # --------------------------------------------------------

    shared_context = {}
    missing_shared_input = False

    for input_name, input_config in config.get(
        "shared_inputs",
        {}
    ).items():
        image_path = resolve_shared_input(
            input_config
        )

        if image_path is None:
            folder = input_config["folder"]
            mode = input_config.get("mode", "first")
            image_name = input_config.get("name", "")

            if mode == "named":
                print(
                    f"Skip category '{category}'. "
                    f"No image named '{image_name}' found in: "
                    f"{folder}"
                )
            else:
                print(
                    f"Skip category '{category}'. "
                    f"No image found in: {folder}"
                )

            missing_shared_input = True
            break

        shared_context[input_name] = image_path

        print(
            f"Shared input {input_name}: {image_path}"
        )

    if missing_shared_input:
        continue

    # --------------------------------------------------------
    # Lấy danh sách mã sản phẩm từ tên folder
    # --------------------------------------------------------

    product_ids = sorted(
        [
            name
            for name in os.listdir(products_dir)
            if os.path.isdir(
                os.path.join(products_dir, name)
            )
        ],
        key=str.lower
    )

    if not product_ids:
        print(
            f"No product folders found in: {products_dir}"
        )
        continue

    # --------------------------------------------------------
    # Build job cho từng sản phẩm
    # --------------------------------------------------------

    for product_id in product_ids:
        print("-" * 60)
        print("Category:", category)
        print("Product:", product_id)

        product_dir = os.path.join(
            products_dir,
            product_id
        )

        ai_dir = os.path.join(
            product_dir,
            "images",
            "ai"
        )

        os.makedirs(
            ai_dir,
            exist_ok=True
        )

        context = dict(shared_context)
        missing_product_input = False

        # ----------------------------------------------------
        # Resolve ảnh input riêng của sản phẩm
        # ----------------------------------------------------

        for input_name, relative_folder in config.get(
            "product_inputs",
            {}
        ).items():
            input_folder = os.path.join(
                product_dir,
                relative_folder
            )

            image_path = get_first_image(
                input_folder
            )

            if image_path is None:
                print(
                    f"Skip product '{product_id}'. "
                    f"No {input_name} found in: "
                    f"{input_folder}"
                )

                missing_product_input = True
                break

            context[input_name] = image_path

            print(
                f"Product input {input_name}: {image_path}"
            )

        if missing_product_input:
            continue

        # ----------------------------------------------------
        # CHANNEL BACKGROUND MODE
        #
        # Category nào khai báo "channel_backgrounds" sẽ chạy
        # nhiều channel. Mỗi background tên số (1.*, 2.*, 3.* ...)
        # tạo một bộ output riêng trong images/ai/channel_<id>/.
        #
        # Hiện tại áp dụng cho:
        # - keychain
        # - eyeglasses
        # ----------------------------------------------------

        channel_config = config.get("channel_backgrounds")

        if channel_config:
            channel_backgrounds = get_channel_backgrounds(
                channel_config["folder"]
            )

            if not channel_backgrounds:
                print(
                    f"Skip product '{product_id}'. "
                    f"No numeric channel backgrounds found in: "
                    f"{channel_config['folder']}"
                )
                continue

        else:
            channel_backgrounds = [
                ("", None)
            ]


        for channel_id, channel_background in channel_backgrounds:

            channel_context = dict(context)

            if channel_config:

                if channel_background is None:
                    continue

                context_key = channel_config["context_key"]
                channel_context[context_key] = (
                    channel_background
                )

                channel_ai_dir = os.path.join(
                    ai_dir,
                    f"channel_{channel_id}"
                )

            else:
                channel_ai_dir = ai_dir


            os.makedirs(
                channel_ai_dir,
                exist_ok=True
            )


            # Tạo trước toàn bộ output path
            for step_config in config["steps"]:

                output_path = os.path.join(
                    channel_ai_dir,
                    step_config["output_filename"]
                )

                channel_context[
                    step_config["output_key"]
                ] = output_path


            # Tạo queue rows
            for step_config in config["steps"]:

                step = step_config["step"]
                step_order = step_config["step_order"]

                output_path = channel_context[
                    step_config["output_key"]
                ]

                input_1 = format_input(
                    step_config.get("input_1", ""),
                    channel_context
                )

                input_2 = format_input(
                    step_config.get("input_2", ""),
                    channel_context
                )

                job_id = (
                    f"{category}_"
                    f"{product_id}_"
                    f"CH{channel_id}_"
                    f"{step}"
                    if channel_id
                    else
                    f"{category}_"
                    f"{product_id}_"
                    f"{step}"
                )

                row = make_row(
                    category=category,
                    job_id=job_id,
                    product_id=product_id,
                    step=step,
                    step_order=step_order,
                    input_1=input_1,
                    input_2=input_2,
                    output=output_path,
                    channel_id=channel_id,
                )

                rows.append(row)

                print(
                    f"Added job: {job_id} "
                    f"[{row['status']}]"
                )


# ============================================================
# SAVE CSV
# ============================================================

fieldnames = [
    "job_id",
    "category",
    "product_id",
    "channel_id",
    "step",
    "step_order",
    "status",
    "attempts",
    "input_1",
    "input_2",
    "output",
    "error",
]

with open(
    QUEUE_FILE,
    "w",
    newline="",
    encoding="utf-8-sig"
) as file:
    writer = csv.DictWriter(
        file,
        fieldnames=fieldnames
    )

    writer.writeheader()
    writer.writerows(rows)


# ============================================================
# SUMMARY
# ============================================================

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

category_job_counts = {}

for row in rows:
    row_category = row["category"]
    category_job_counts[row_category] = (
        category_job_counts.get(row_category, 0) + 1
    )


print("=" * 60)
print("Image queue created.")
print(f"Done: {done_jobs}")
print(f"Pending: {pending_jobs}")

for category in ENABLED_CATEGORIES:
    print(
        f"{category} jobs: "
        f"{category_job_counts.get(category, 0)}"
    )

print(f"Total jobs: {len(rows)}")
print(f"Saved: {QUEUE_FILE}")