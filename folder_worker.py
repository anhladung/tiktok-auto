import os
import re
import shutil


# ============================================================
# BASE PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

INPUT_PRODUCTS_DIR = os.path.join(
    BASE_DIR,
    "input_products"
)

PRODUCTS_DIR = os.path.join(
    BASE_DIR,
    "products"
)


IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


# ============================================================
# CATEGORY CONFIG
# ============================================================

# Muốn chạy cả đồ ăn vặt, móc khóa, ốp lưng và mắt kính:
ENABLED_CATEGORIES = [
    "snack",
    "keychain",
    "phone_case",
    "eyeglasses",
    "shoes",
]

# Muốn test riêng đồ ăn vặt:
# ENABLED_CATEGORIES = ["snack"]

# Muốn test riêng móc khóa:
# ENABLED_CATEGORIES = ["keychain"]

# Muốn test riêng ốp lưng:
# ENABLED_CATEGORIES = ["phone_case"]


CATEGORY_CONFIG = {
    # ========================================================
    # SNACK (ĐỒ ĂN VẶT)
    # ========================================================
    "snack": {
        "input_dir": os.path.join(
            INPUT_PRODUCTS_DIR,
            "snack"
        ),

        "products_dir": os.path.join(
            PRODUCTS_DIR,
            "snack"
        ),

        # Mã sản phẩm:
        # SNK001, SNK002, SNK003...
        "product_prefix": "SNK",

        "product_id_digits": 3,

        # Mỗi sản phẩm đồ ăn vặt chỉ cần 1 ảnh sản phẩm.
        # Background reference sẽ được xử lý ở build_image_queue.py.
        "inputs": [
            {
                "label": "Product",
                "target_folder": os.path.join(
                    "images",
                    "raw",
                    "product"
                ),
                "target_filename": "1",
            },
        ],
    },

    # ========================================================
    # KEYCHAIN
    # ========================================================
    "keychain": {
        "input_dir": os.path.join(
            INPUT_PRODUCTS_DIR,
            "keychain"
        ),

        "products_dir": os.path.join(
            PRODUCTS_DIR,
            "keychain"
        ),

        # Mã sản phẩm:
        # KC001, KC002, KC003...
        "product_prefix": "KC",

        "product_id_digits": 3,

        # Mỗi sản phẩm móc khóa chỉ cần 1 ảnh sản phẩm.
        "inputs": [
            {
                "label": "Product",
                "target_folder": os.path.join(
                    "images",
                    "raw",
                    "product"
                ),
                "target_filename": "1",
            },
        ],
    },

    # ========================================================
    # PHONE CASE
    # ========================================================
    "phone_case": {
        "input_dir": os.path.join(
            INPUT_PRODUCTS_DIR,
            "phone_case"
        ),

        "products_dir": os.path.join(
            PRODUCTS_DIR,
            "phone_case"
        ),

        # Mã sản phẩm:
        # PC001, PC002, PC003...
        "product_prefix": "PC",

        "product_id_digits": 3,

        # Mỗi sản phẩm ốp lưng chỉ cần 1 ảnh sản phẩm.
        "inputs": [
            {
                "label": "Product",
                "target_folder": os.path.join(
                    "images",
                    "raw",
                    "product"
                ),
                "target_filename": "1",
            },
        ],
    },

    # ========================================================
    # EYEGLASSES
    # ========================================================
    "eyeglasses": {
        "input_dir": os.path.join(
            INPUT_PRODUCTS_DIR,
            "eyeglasses"
        ),

        "products_dir": os.path.join(
            PRODUCTS_DIR,
            "eyeglasses"
        ),

        # Mã sản phẩm:
        # GL001, GL002, GL003...
        "product_prefix": "GL",

        "product_id_digits": 3,

        # Mỗi sản phẩm mắt kính chỉ cần 1 ảnh sản phẩm gốc.
        # Background aesthetic / hand reference sẽ được xử lý
        # ở bước build image queue, không copy vào từng sản phẩm.
        "inputs": [
            {
                "label": "Product",
                "target_folder": os.path.join(
                    "images",
                    "raw",
                    "product"
                ),
                "target_filename": "1",
            },
        ],
    },

    # ========================================================
    # SHOES (GIÀY)
    # ========================================================
    "shoes": {
        "input_dir": os.path.join(
            INPUT_PRODUCTS_DIR,
            "shoes"
        ),

        "products_dir": os.path.join(
            PRODUCTS_DIR,
            "shoes"
        ),

        # Mã sản phẩm:
        # SH001, SH002, SH003...
        "product_prefix": "SH",

        "product_id_digits": 3,

        # Mỗi sản phẩm giày chỉ cần 1 ảnh sản phẩm gốc.
        # Background reference sẽ được xử lý ở bước build image queue.
        "inputs": [
            {
                "label": "Product",
                "target_folder": os.path.join(
                    "images",
                    "raw",
                    "product"
                ),
                "target_filename": "1",
            },
        ],
    },
}


# ============================================================
# FOLDER STRUCTURE
# ============================================================

COMMON_PRODUCT_FOLDERS = [
    os.path.join(
        "images",
        "ai"
    ),
    os.path.join(
        "output",
        "audio"
    ),
    os.path.join(
        "output",
        "audio_plan"
    ),
    os.path.join(
        "output",
        "prompts"
    ),
    os.path.join(
        "output",
        "scripts"
    ),
    os.path.join(
        "output",
        "videos"
    ),
]


def create_product_structure(
    product_dir,
    category_config
):
    """
    Tạo cấu trúc thư mục cho một sản phẩm.

    Các thư mục output được dùng chung.

    Thư mục images/raw được tạo dựa trên config:
    - lipstick: product + shade
    - sandal: product
    - keychain: product
    - phone_case: product
    - mask: product
    - eyeglasses: product
    """

    folders = list(
        COMMON_PRODUCT_FOLDERS
    )

    for input_config in category_config["inputs"]:
        folders.append(
            input_config["target_folder"]
        )

    # Loại bỏ folder trùng nhau nhưng vẫn giữ thứ tự.
    folders = list(
        dict.fromkeys(folders)
    )

    for folder in folders:
        os.makedirs(
            os.path.join(
                product_dir,
                folder
            ),
            exist_ok=True
        )


# ============================================================
# PRODUCT ID
# ============================================================

def get_next_product_index(
    products_dir,
    product_prefix
):
    """
    Tìm mã sản phẩm lớn nhất của một category
    rồi trả về số tiếp theo.

    Ví dụ:

    products/lipstick:
        LP001
        LP002

    Kết quả tiếp theo:
        3

    products/sandal:
        SDL001
        SDL005

    Kết quả tiếp theo:
        6

    products/keychain:
        KC001
        KC004

    Kết quả tiếp theo:
        5

    products/phone_case:
        PC001
        PC009

    Kết quả tiếp theo:
        10

    products/mask:
        MSK001
        MSK004

    Kết quả tiếp theo:
        5
    """

    if not os.path.isdir(products_dir):
        return 1

    existing_indexes = []

    pattern = rf"{re.escape(product_prefix)}(\d+)"

    for name in os.listdir(products_dir):
        folder_path = os.path.join(
            products_dir,
            name
        )

        if not os.path.isdir(folder_path):
            continue

        match = re.fullmatch(
            pattern,
            name,
            flags=re.IGNORECASE
        )

        if match:
            existing_indexes.append(
                int(match.group(1))
            )

    if not existing_indexes:
        return 1

    return max(existing_indexes) + 1


def build_product_id(
    product_prefix,
    product_index,
    product_id_digits
):
    """
    Tạo mã sản phẩm có số 0 ở đầu.

    Ví dụ:
        LP + 1 + 3 chữ số  -> LP001
        SDL + 12 + 3 chữ số -> SDL012
    """

    return (
        f"{product_prefix}"
        f"{product_index:0{product_id_digits}d}"
    )


# ============================================================
# INPUT IMAGE HELPERS
# ============================================================

def is_supported_image(file_name):
    extension = os.path.splitext(
        file_name
    )[1].lower()

    return extension in IMAGE_EXTENSIONS


def get_input_images(input_dir):
    """
    Lấy danh sách ảnh trực tiếp trong input folder.

    Không lấy ảnh trong folder con.
    """

    if not os.path.isdir(input_dir):
        return []

    images = [
        file_name
        for file_name in os.listdir(input_dir)
        if (
            os.path.isfile(
                os.path.join(
                    input_dir,
                    file_name
                )
            )
            and is_supported_image(file_name)
        )
    ]

    images.sort(
        key=str.lower
    )

    return images


# ============================================================
# COPY PRODUCT FILES
# ============================================================

def copy_product_inputs(
    input_dir,
    product_dir,
    source_images,
    category_config
):
    """
    Copy ảnh đầu vào vào đúng thư mục của sản phẩm.

    source_images được ghép với category_config["inputs"]
    theo đúng thứ tự.

    Lipstick:
        source_images[0] -> raw/product
        source_images[1] -> raw/shade

    Sandal:
        source_images[0] -> raw/product

    Keychain:
        source_images[0] -> raw/product

    Phone case:
        source_images[0] -> raw/product

    Mask:
        source_images[0] -> raw/product

    Eyeglasses:
        source_images[0] -> raw/product
    """

    copied_files = []

    input_configs = category_config["inputs"]

    if len(source_images) != len(input_configs):
        raise ValueError(
            "Số ảnh nguồn không khớp với cấu hình category."
        )

    for source_file_name, input_config in zip(
        source_images,
        input_configs
    ):
        source_path = os.path.join(
            input_dir,
            source_file_name
        )

        source_extension = os.path.splitext(
            source_file_name
        )[1].lower()

        target_folder = os.path.join(
            product_dir,
            input_config["target_folder"]
        )

        target_file_name = (
            f"{input_config['target_filename']}"
            f"{source_extension}"
        )

        target_path = os.path.join(
            target_folder,
            target_file_name
        )

        shutil.copy2(
            source_path,
            target_path
        )

        copied_files.append({
            "label": input_config["label"],
            "source": source_file_name,
            "target": target_path,
        })

    return copied_files


# ============================================================
# PROCESS CATEGORY
# ============================================================

def process_category(
    category,
    category_config
):
    input_dir = category_config["input_dir"]
    products_dir = category_config["products_dir"]

    product_prefix = category_config[
        "product_prefix"
    ]

    product_id_digits = category_config[
        "product_id_digits"
    ]

    inputs_per_product = len(
        category_config["inputs"]
    )

    print("=" * 60)
    print(f"Category: {category}")
    print(f"Input:    {input_dir}")
    print(f"Products: {products_dir}")

    os.makedirs(
        input_dir,
        exist_ok=True
    )

    os.makedirs(
        products_dir,
        exist_ok=True
    )

    images = get_input_images(
        input_dir
    )

    if not images:
        print(
            f"Không có ảnh trong: {input_dir}"
        )
        return 0

    if inputs_per_product <= 0:
        raise ValueError(
            f"Category '{category}' không có input config."
        )

    if len(images) % inputs_per_product != 0:
        raise ValueError(
            f"Category '{category}' có {len(images)} ảnh, "
            f"nhưng mỗi sản phẩm cần "
            f"{inputs_per_product} ảnh. "
            f"Số ảnh phải chia hết cho "
            f"{inputs_per_product}."
        )

    product_index = get_next_product_index(
        products_dir=products_dir,
        product_prefix=product_prefix
    )

    first_product_id = build_product_id(
        product_prefix=product_prefix,
        product_index=product_index,
        product_id_digits=product_id_digits
    )

    print(
        f"Start from: {first_product_id}"
    )

    created_count = 0

    for image_position in range(
        0,
        len(images),
        inputs_per_product
    ):
        source_images = images[
            image_position:
            image_position + inputs_per_product
        ]

        # Nếu folder sản phẩm đã tồn tại thì tăng index
        # cho đến khi tìm được mã chưa sử dụng.
        while True:
            product_id = build_product_id(
                product_prefix=product_prefix,
                product_index=product_index,
                product_id_digits=product_id_digits
            )

            product_dir = os.path.join(
                products_dir,
                product_id
            )

            if not os.path.exists(product_dir):
                break

            print(
                f"Skip existing folder: {product_id}"
            )

            product_index += 1

        create_product_structure(
            product_dir=product_dir,
            category_config=category_config
        )

        copied_files = copy_product_inputs(
            input_dir=input_dir,
            product_dir=product_dir,
            source_images=source_images,
            category_config=category_config
        )

        print("-" * 60)
        print(
            f"{category}/{product_id} created:"
        )

        for copied_file in copied_files:
            print(
                f"  {copied_file['label']}: "
                f"{copied_file['source']}"
            )

        created_count += 1
        product_index += 1

    print(
        f"Created {created_count} "
        f"product(s) for category: {category}"
    )

    return created_count


# ============================================================
# MAIN
# ============================================================

def main():
    os.makedirs(
        INPUT_PRODUCTS_DIR,
        exist_ok=True
    )

    os.makedirs(
        PRODUCTS_DIR,
        exist_ok=True
    )

    total_created = 0

    errors = []

    for category in ENABLED_CATEGORIES:
        category_config = CATEGORY_CONFIG.get(
            category
        )

        if category_config is None:
            errors.append(
                f"Không tìm thấy config cho category: "
                f"{category}"
            )
            continue

        try:
            created_count = process_category(
                category=category,
                category_config=category_config
            )

            total_created += created_count

        except Exception as error:
            errors.append(
                f"{category}: {error}"
            )

            print(
                f"ERROR [{category}]: {error}"
            )

    print("=" * 60)
    print("DONE")
    print(f"Total products created: {total_created}")

    if errors:
        print("-" * 60)
        print("Errors:")

        for error in errors:
            print(f"  - {error}")

    print("=" * 60)


if __name__ == "__main__":
    main()