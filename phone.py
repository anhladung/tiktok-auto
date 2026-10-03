from pathlib import Path

# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(
    r"C:\Users\Thinkbook 14G2\Downloads\tiktok-auto\products\phone_case"
)


# ============================================================
# PROCESS IMAGES
# ============================================================

def process_images(product_dir):

    ai_folder = (
        product_dir
        / "images"
        / "ai"
    )

    if not ai_folder.exists():
        print(
            f"[SKIP] Không tìm thấy: {ai_folder}"
        )
        return

    print("\n" + "=" * 60)
    print(f"PRODUCT: {product_dir.name}")
    print(f"AI FOLDER: {ai_folder}")
    print("=" * 60)

    # --------------------------------------------------------
    # 1. XÓA ẢNH 01 + 02 CŨ
    # --------------------------------------------------------

    old_images = [
        ai_folder / "01_clip_01_first_frame.png",
        ai_folder / "02_clip_01_last_frame.png",
    ]

    for file in old_images:

        if file.exists():

            print(
                f"[DELETE IMAGE] {file.name}"
            )

            file.unlink()

        else:

            print(
                f"[NOT FOUND] {file.name}"
            )

    # --------------------------------------------------------
    # 2. ĐỔI 03 → 01
    # --------------------------------------------------------

    image_03 = (
        ai_folder
        / "03_clip_02_first_frame.png"
    )

    image_01 = (
        ai_folder
        / "01_clip_01_first_frame.png"
    )

    if image_03.exists():

        image_03.rename(
            image_01
        )

        print(
            "[RENAME] "
            "03_clip_02_first_frame.png"
            " → "
            "01_clip_01_first_frame.png"
        )

    else:

        print(
            "[NOT FOUND] "
            "03_clip_02_first_frame.png"
        )

    # --------------------------------------------------------
    # 3. ĐỔI 04 → 02
    # --------------------------------------------------------

    image_04 = (
        ai_folder
        / "04_clip_02_last_frame.png"
    )

    image_02 = (
        ai_folder
        / "02_clip_01_last_frame.png"
    )

    if image_04.exists():

        image_04.rename(
            image_02
        )

        print(
            "[RENAME] "
            "04_clip_02_last_frame.png"
            " → "
            "02_clip_01_last_frame.png"
        )

    else:

        print(
            "[NOT FOUND] "
            "04_clip_02_last_frame.png"
        )


# ============================================================
# PROCESS VIDEOS
# ============================================================

def process_videos(product_dir):

    video_folder = (
        product_dir
        / "output"
        / "videos"
    )

    if not video_folder.exists():
        print(
            f"[SKIP VIDEO] Không tìm thấy: {video_folder}"
        )
        return

    # --------------------------------------------------------
    # XÓA CLIP 01
    # --------------------------------------------------------

    for file in video_folder.glob(
        "*_clip_01_*.mp4"
    ):

        print(
            f"[DELETE CLIP 01] {file.name}"
        )

        file.unlink()

    # --------------------------------------------------------
    # ĐỔI CLIP 02 → CLIP 01
    # --------------------------------------------------------

    for file in video_folder.glob(
        "*_clip_02_*.mp4"
    ):

        new_name = file.name.replace(
            "_clip_02_",
            "_clip_01_",
            1
        )

        destination = (
            video_folder
            / new_name
        )

        file.rename(
            destination
        )

        print(
            f"[RENAME CLIP] "
            f"{file.name} → {new_name}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    if not BASE_DIR.exists():

        print(
            "[ERROR] Không tìm thấy:"
        )

        print(BASE_DIR)

        return

    for product_dir in BASE_DIR.iterdir():

        if not product_dir.is_dir():
            continue

        process_images(
            product_dir
        )

        process_videos(
            product_dir
        )

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()