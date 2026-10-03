import os

from PIL import Image, ImageOps


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

PRODUCTS_DIR = os.path.join(
    BASE_DIR,
    "products"
)


# Chỉ quét ảnh đầu vào gốc.
#
# Lipstick:
#   images/raw/product
#   images/raw/shade
#
# Sandal:
#   images/raw/product
#
# Keychain:
#   images/raw/product
#
# Nếu một category không có folder nào đó,
# chương trình sẽ tự bỏ qua.
RAW_IMAGE_FOLDERS = [
    os.path.join(
        "images",
        "raw",
        "product"
    ),
    os.path.join(
        "images",
        "raw",
        "shade"
    ),
]


# ============================================================
# SETTINGS
# ============================================================

# True:
# Nếu file PNG đã tồn tại thì ghi đè.
#
# False:
# Nếu file PNG đã tồn tại thì bỏ qua.
OVERWRITE_EXISTING = False


# True:
# Xóa file WEBP sau khi chuyển thành PNG thành công.
#
# False:
# Giữ lại cả WEBP và PNG.
#
# Nên để False trong lúc test.
DELETE_SOURCE_WEBP = True


# ============================================================
# IMAGE HELPERS
# ============================================================

def is_webp(filename):
    return os.path.splitext(
        filename
    )[1].lower() == ".webp"


def image_has_transparency(image):
    """
    Kiểm tra ảnh có alpha hoặc transparency hay không.
    """

    if "A" in image.getbands():
        return True

    if "transparency" in image.info:
        return True

    return False


def prepare_image_for_png(image):
    """
    Chuẩn hóa ảnh trước khi lưu PNG:

    - Sửa chiều ảnh theo EXIF.
    - Nếu WEBP động thì lấy frame đầu tiên.
    - Giữ nền trong suốt nếu ảnh có alpha.
    - Ảnh thường chuyển sang RGB.
    """

    if getattr(image, "is_animated", False):
        image.seek(0)

    image = ImageOps.exif_transpose(
        image
    )

    if image_has_transparency(image):
        return image.convert("RGBA")

    return image.convert("RGB")


# ============================================================
# CONVERSION
# ============================================================

def convert_webp_file(webp_path):
    """
    Chuyển một file WEBP sang PNG.

    Trả về:
        converted
        skipped
        failed
    """

    png_path = os.path.splitext(
        webp_path
    )[0] + ".png"

    if (
        os.path.exists(png_path)
        and not OVERWRITE_EXISTING
    ):
        print(
            f"Skipped, PNG already exists: "
            f"{png_path}"
        )
        return "skipped"

    # Lưu vào file tạm trước để tránh tạo ra
    # file PNG hỏng nếu quá trình bị gián đoạn.
    temporary_path = (
        png_path + ".temporary"
    )

    try:
        with Image.open(webp_path) as image:
            converted_image = prepare_image_for_png(
                image
            )

            converted_image.save(
                temporary_path,
                format="PNG",
                optimize=True
            )

            converted_image.close()

        os.replace(
            temporary_path,
            png_path
        )

        if DELETE_SOURCE_WEBP:
            os.remove(
                webp_path
            )

        print(
            f"Converted: {webp_path}"
        )
        print(
            f"       To: {png_path}"
        )

        return "converted"

    except Exception as error:
        if os.path.exists(temporary_path):
            try:
                os.remove(
                    temporary_path
                )
            except OSError:
                pass

        print(
            f"Failed: {webp_path}"
        )
        print(
            f"Error:  {error}"
        )

        return "failed"


# ============================================================
# PRODUCT DISCOVERY
# ============================================================

def get_category_directories():
    """
    Tự lấy tất cả category bên trong products/.

    Ví dụ:
        products/lipstick
        products/sandal
        products/keychain
        products/bag
        products/shoes

    Không cần thêm category vào danh sách cố định.
    Chỉ cần category có folder trong products/.
    """

    if not os.path.isdir(PRODUCTS_DIR):
        return []

    category_directories = [
        os.path.join(
            PRODUCTS_DIR,
            category_name
        )
        for category_name in os.listdir(
            PRODUCTS_DIR
        )
        if os.path.isdir(
            os.path.join(
                PRODUCTS_DIR,
                category_name
            )
        )
    ]

    category_directories.sort(
        key=lambda path: os.path.basename(
            path
        ).lower()
    )

    return category_directories


def get_product_directories(category_dir):
    """
    Lấy các folder mã sản phẩm trong category.

    Ví dụ:
        products/lipstick/LP001
        products/sandal/SDL001
        products/keychain/KC001
    """

    product_directories = [
        os.path.join(
            category_dir,
            product_id
        )
        for product_id in os.listdir(
            category_dir
        )
        if os.path.isdir(
            os.path.join(
                category_dir,
                product_id
            )
        )
    ]

    product_directories.sort(
        key=lambda path: os.path.basename(
            path
        ).lower()
    )

    return product_directories


def get_webp_files(folder):
    """
    Tìm toàn bộ WEBP trong folder.
    Hỗ trợ cả folder con nếu sau này có thêm.
    """

    webp_files = []

    if not os.path.isdir(folder):
        return webp_files

    for root, dirs, files in os.walk(folder):
        dirs.sort(
            key=str.lower
        )

        for filename in sorted(
            files,
            key=str.lower
        ):
            if not is_webp(filename):
                continue

            webp_files.append(
                os.path.join(
                    root,
                    filename
                )
            )

    return webp_files


# ============================================================
# MAIN
# ============================================================

def main():
    if not os.path.isdir(PRODUCTS_DIR):
        raise FileNotFoundError(
            f"Không tìm thấy products folder: "
            f"{PRODUCTS_DIR}"
        )

    converted_count = 0
    skipped_count = 0
    failed_count = 0
    found_count = 0

    category_directories = get_category_directories()

    if not category_directories:
        print(
            f"Không có category nào trong: "
            f"{PRODUCTS_DIR}"
        )
        return

    for category_dir in category_directories:
        category = os.path.basename(
            category_dir
        )

        print("=" * 60)
        print(
            f"Category: {category}"
        )

        product_directories = get_product_directories(
            category_dir
        )

        if not product_directories:
            print(
                "Không có product folder."
            )
            continue

        for product_dir in product_directories:
            product_id = os.path.basename(
                product_dir
            )

            product_webp_files = []

            for relative_folder in RAW_IMAGE_FOLDERS:
                raw_folder = os.path.join(
                    product_dir,
                    relative_folder
                )

                product_webp_files.extend(
                    get_webp_files(
                        raw_folder
                    )
                )

            if not product_webp_files:
                continue

            print("-" * 60)
            print(
                f"Product: {product_id}"
            )

            # Loại file trùng nếu nhiều target folder
            # vô tình trỏ đến cùng một vị trí.
            product_webp_files = sorted(
                set(product_webp_files),
                key=str.lower
            )

            for webp_path in product_webp_files:
                found_count += 1

                result = convert_webp_file(
                    webp_path
                )

                if result == "converted":
                    converted_count += 1

                elif result == "skipped":
                    skipped_count += 1

                elif result == "failed":
                    failed_count += 1

    print("=" * 60)
    print("DONE")
    print(
        f"WEBP found: {found_count}"
    )
    print(
        f"Converted:  {converted_count}"
    )
    print(
        f"Skipped:    {skipped_count}"
    )
    print(
        f"Failed:     {failed_count}"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()