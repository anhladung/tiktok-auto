import glob
import json
import os
import re
import subprocess
import random

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

FINAL_VIDEO_ROOT = os.path.join(
    BASE_DIR,
    "videos"
)

ASSETS_DIR = os.path.join(
    BASE_DIR,
    "assets"
)

MUSIC_DIR = os.path.join(
    ASSETS_DIR,
    "music"
)

SFX_DIR = os.path.join(
    ASSETS_DIR,
    "sfx"
)

# ============================================================
# CATEGORIES
# ============================================================

ENABLED_CATEGORIES = [
    "snack",
    "keychain",
    "phone_case",
    "shoes",
]

# Chạy riêng một loại:
# ENABLED_CATEGORIES = ["snack"]
# ENABLED_CATEGORIES = ["keychain"]
# ENABLED_CATEGORIES = ["phone_case"]


# ============================================================
# AUDIO / VIDEO SETTINGS
# ============================================================

MUSIC_VOLUME = 0.5

CLIP_DURATION_SECONDS = 8

# Duration cuối phụ thuộc số clip thực tế của từng category.
# snack / keychain / phone_case: 1 clip = 8s
DEFAULT_FINAL_VIDEO_DURATION_SECONDS = 8

# ============================================================
# PHONE CASE TITLE OVERLAY IMAGE
# ============================================================

PHONE_CASE_TEXT_ENABLED = True

# Nội dung chữ
# Nội dung chữ — mỗi lần build sẽ chọn ngẫu nhiên 1 câu trong danh sách.
PHONE_CASE_TITLE_OPTIONS = [
    "phone case check",
    "new phone case",
    "phone case swap",
    "current phone case",
    "phone case rotation",
    "just a phone case",
    "phone case pick",
    "todays phone case",
]

PHONE_CASE_DECOR_TEXT = "· ✦ · ✧ ★ ✧ · ✦ ·"
# Font: mặc định dùng font có sẵn trên Windows.
# Segoe Script = font viết tay mảnh, nghệ thuật cho dòng chữ chính.
# Arial = font thường cho dòng ký tự (script font hay thiếu glyph ★).
PHONE_CASE_TITLE_FONT = os.path.join(
    ASSETS_DIR,
    "fonts",
    "AlexBrush-Regular.ttf"
)

PHONE_CASE_DECOR_FONT = os.path.join(
    ASSETS_DIR,
    "fonts",
    "seguisym.ttf"
)

# Cỡ chữ tính theo % chiều rộng video, tự scale mọi kích thước video.
PHONE_CASE_TITLE_FONTSIZE_RATIO = 0.06
PHONE_CASE_DECOR_FONTSIZE_RATIO = 0.03

# Vị trí theo % chiều cao video
PHONE_CASE_TITLE_Y_RATIO = 0.2
PHONE_CASE_DECOR_Y_RATIO = 0.22

# Màu chữ trắng + viền đen mảnh để nổi trên mọi nền
PHONE_CASE_TEXT_COLOR = "white"
PHONE_CASE_BORDER_COLOR = "black"

# ============================================================
# CLIP ORDER BY CATEGORY
# ============================================================

CATEGORY_CLIP_ORDER = {
    # Snack:
    # CHỈ có clip_01.
    "snack": [
        1,
    ],

    # Keychain:
    # CHỈ còn clip_02 = 03_hand_holding -> 04_hand_holding_next_frame.
    "keychain": [
        2,
    ],

    # Phone case:
    # CHỈ có clip_01.
    "phone_case": [
        1,
    ],

    # Shoes:
    # CHỈ có clip_01.
    "shoes": [
        1,
    ],
}

# ============================================================
# FFMPEG
# ============================================================

FFMPEG_DIR = (
    r"C:\Users\Thinkbook 14G2\Downloads"
    r"\ffmpeg-2026-06-29-git-de6bcf5c05-full_build"
    r"\ffmpeg-2026-06-29-git-de6bcf5c05-full_build"
    r"\bin"
)

FFMPEG = os.path.join(
    FFMPEG_DIR,
    "ffmpeg.exe"
)


# ============================================================
# PATH HELPERS
# ============================================================

def get_final_video_duration(category):
    """
    Tính thời lượng final video theo số clip hợp lệ
    của pipeline hiện tại.

    lipstick / sandal = 2 clip = 16 giây
    keychain / phone_case / mask = 1 clip = 8 giây
    shoes = 1 clip = 10 giây
    """

    if category == "shoes":
        return 10

    clip_order = CATEGORY_CLIP_ORDER.get(
        category
    )

    if not clip_order:
        return DEFAULT_FINAL_VIDEO_DURATION_SECONDS

    return (
        len(clip_order)
        * CLIP_DURATION_SECONDS
    )


def file_exists_and_not_empty(path):
    return (
            os.path.isfile(path)
            and os.path.getsize(path) > 0
    )


def resolve_project_path(path):
    """
    Audio plan có thể chứa đường dẫn tương đối:

        assets/music/music_01.mp3
        assets/sfx/click.mp3

    Hoặc đường dẫn tuyệt đối.
    """

    if not path:
        return None

    path = str(path).strip()

    path = path.replace(
        "/",
        os.sep
    )

    if os.path.isabs(path):
        return os.path.normpath(
            path
        )

    return os.path.normpath(
        os.path.join(
            BASE_DIR,
            path
        )
    )


# ============================================================
# 1. GET ALL PRODUCTS
# ============================================================

def get_all_products():
    """
    Trả về danh sách:

        [
            ("lipstick", "LP001"),
            ("sandal", "SDL001"),
            ("keychain", "KC001"),
            ("phone_case", "PC001"),
            ("mask", "MSK001"),
        ]
    """

    products = []

    for category in ENABLED_CATEGORIES:
        category_dir = os.path.join(
            PRODUCTS_ROOT,
            category
        )

        if not os.path.isdir(
                category_dir
        ):
            print(
                "Category folder not found:",
                category_dir
            )

            continue

        product_ids = [
            name
            for name in os.listdir(
                category_dir
            )
            if os.path.isdir(
                os.path.join(
                    category_dir,
                    name
                )
            )
        ]

        product_ids.sort(
            key=str.lower
        )

        for product_id in product_ids:
            products.append(
                (
                    category,
                    product_id
                )
            )

    return products


# ============================================================
# 2. LOAD AUDIO PLAN
# ============================================================

def load_audio_plan(
        category,
        product_id
):
    path = os.path.join(
        PRODUCTS_ROOT,
        category,
        product_id,
        "output",
        "audio_plan",
        f"{product_id}.json"
    )

    if not os.path.exists(path):
        return None

    with open(
            path,
            "r",
            encoding="utf-8"
    ) as file:
        return json.load(file)


def extract_audio_from_plan(
        plan,
        category
):
    music_path = None
    sfx_events = []

    # ========================================================
    # BACKGROUND MUSIC
    # ========================================================

    background_music = plan.get(
        "background_music"
    )

    if background_music:
        background_music_file = (
            background_music.get("file")
        )

        if background_music_file:
            resolved_music_path = (
                resolve_project_path(
                    background_music_file
                )
            )

            if file_exists_and_not_empty(
                    resolved_music_path
            ):
                music_path = (
                    resolved_music_path
                )

            else:
                print(
                    "Warning: music file not found:",
                    resolved_music_path
                )

    # ========================================================
    # SFX EVENTS
    # ========================================================

    clips = plan.get(
        "clips",
        []
    )

    desired_order = CATEGORY_CLIP_ORDER.get(
        category
    )

    if desired_order:
        clips_by_number = {}

        for clip in clips:
            try:
                clip_number = int(
                    clip.get(
                        "clip",
                        999
                    )
                )

            except (
                    TypeError,
                    ValueError
            ):
                clip_number = 999

            clips_by_number[
                clip_number
            ] = clip

        ordered_clips = []

        for clip_number in desired_order:
            clip = clips_by_number.get(
                clip_number
            )

            if clip:
                ordered_clips.append(
                    clip
                )

        used_clip_ids = {
            id(clip)
            for clip in ordered_clips
        }

        remaining_clips = [
            clip
            for clip in clips
            if id(clip) not in used_clip_ids
        ]

        ordered_clips.extend(
            remaining_clips
        )

        clips = ordered_clips

    offset = 0

    for clip in clips:
        for event in clip.get(
                "events",
                []
        ):
            event_file = event.get(
                "file"
            )

            if not event_file:
                continue

            sfx_path = resolve_project_path(
                event_file
            )

            if not file_exists_and_not_empty(
                    sfx_path
            ):
                print(
                    "Warning: SFX file not found:",
                    sfx_path
                )

                continue

            try:
                event_time = float(
                    event.get(
                        "time",
                        0
                    )
                )

            except (
                    TypeError,
                    ValueError
            ):
                event_time = 0

            try:
                event_volume = float(
                    event.get(
                        "volume",
                        0.1
                    )
                )

            except (
                    TypeError,
                    ValueError
            ):
                event_volume = 0.1

            sfx_events.append({
                "path": sfx_path,

                # Offset dựa trên thứ tự clip mới.
                "time": (
                        offset
                        + event_time
                ),

                "volume": event_volume,
            })

        offset += CLIP_DURATION_SECONDS

    return (
        music_path,
        sfx_events
    )


# ============================================================
# 3. GET CLIPS FROM PRODUCT
# ============================================================

def get_clips(
        video_dir,
        product_id
):
    """
    Chỉ lấy bản video mới nhất của mỗi clip.

    Ví dụ trong folder có:

        SDL001_clip_01_20260720_100000.mp4
        SDL001_clip_01_20260721_110000.mp4
        SDL001_clip_02_20260721_120000.mp4

    Kết quả chỉ lấy:

        SDL001_clip_01_20260721_110000.mp4
        SDL001_clip_02_20260721_120000.mp4
    """

    if not os.path.isdir(
            video_dir
    ):
        return []

    pattern = os.path.join(
        video_dir,
        f"{product_id}_clip_*.mp4"
    )

    files = [
        path
        for path in glob.glob(pattern)
        if file_exists_and_not_empty(path)
    ]

    latest_by_clip = {}

    clip_pattern = re.compile(
        rf"^{re.escape(product_id)}"
        rf"_clip_(\d+)"
        rf"(?:_.*)?\.mp4$",
        re.IGNORECASE
    )

    for file_path in files:
        filename = os.path.basename(
            file_path
        )

        match = clip_pattern.match(
            filename
        )

        if not match:
            continue

        clip_number = int(
            match.group(1)
        )

        current_path = latest_by_clip.get(
            clip_number
        )

        if current_path is None:
            latest_by_clip[
                clip_number
            ] = file_path

            continue

        if (
                os.path.getmtime(file_path)
                > os.path.getmtime(current_path)
        ):
            latest_by_clip[
                clip_number
            ] = file_path

    return [
        latest_by_clip[clip_number]
        for clip_number in sorted(
            latest_by_clip
        )
    ]


def get_clip_number(
        video_path
):
    filename = os.path.basename(
        video_path
    )

    match = re.search(
        r"_clip_(\d+)",
        filename,
        re.IGNORECASE
    )

    if not match:
        return 999

    return int(
        match.group(1)
    )


def order_clips_by_category(
        category,
        clips
):
    """
    Lipstick:
        clip_01 -> clip_02

    Sandal:
        clip_01 -> clip_02

    Keychain:
        ONLY clip_02

    Phone case:
        ONLY clip_01

    Mask:
        ONLY clip_01
    """

    desired_order = CATEGORY_CLIP_ORDER.get(
        category
    )

    if not desired_order:
        return clips

    clips_by_number = {
        get_clip_number(clip_path): clip_path
        for clip_path in clips
    }

    ordered_clips = []

    # Thêm clip theo thứ tự được cấu hình.
    for clip_number in desired_order:
        clip_path = clips_by_number.get(
            clip_number
        )

        if clip_path:
            ordered_clips.append(
                clip_path
            )

    # Pipeline mới yêu cầu chỉ dùng đúng các clip
    # được khai báo trong CATEGORY_CLIP_ORDER.
    #
    # Không append clip cũ ngoài cấu hình, vì:
    # - keychain có thể còn clip_01 backpack từ pipeline cũ;
    # - phone_case có thể còn clip_02 cũ;
    # - các file stale này không được phép xuất hiện trong final video.
    return ordered_clips


# ============================================================
# PHONE CASE TITLE OVERLAY IMAGE
# ============================================================

def ffmpeg_escape_path(path):
    """
    ffmpeg filter dùng ':' làm ký tự phân cách option,
    nên đường dẫn Windows kiểu C:\\... phải escape lại.
    """
    escaped = path.replace(
        "\\",
        "/"
    )

    escaped = escaped.replace(
        ":",
        r"\:"
    )

    return escaped


def ffmpeg_escape_text(text):
    """
    Escape ký tự đặc biệt trong nội dung drawtext.
    """
    escaped = text.replace(
        "\\",
        r"\\"
    )

    escaped = escaped.replace(
        ":",
        r"\:"
    )

    escaped = escaped.replace(
        "'",
        r"\'"
    )

    escaped = escaped.replace(
        "%",
        r"\%"
    )

    return escaped


def add_phone_case_title(
        input_video,
        output_video
):
    """
    Overlay chữ + ký tự trang trí bằng drawtext,
    thay cho ảnh PNG.
    """

    if not PHONE_CASE_TEXT_ENABLED:
        os.replace(
            input_video,
            output_video
        )
        return

    for font_path in (
            PHONE_CASE_TITLE_FONT,
            PHONE_CASE_DECOR_FONT
    ):
        if not file_exists_and_not_empty(
                font_path
        ):
            print(
                "Font not found, skip title:",
                font_path
            )

            os.replace(
                input_video,
                output_video
            )
            return

    title_font = ffmpeg_escape_path(
        PHONE_CASE_TITLE_FONT
    )

    decor_font = ffmpeg_escape_path(
        PHONE_CASE_DECOR_FONT
    )

    title_text = ffmpeg_escape_text(
        random.choice(
            PHONE_CASE_TITLE_OPTIONS
        )
    )

    decor_text = ffmpeg_escape_text(
        PHONE_CASE_DECOR_TEXT
    )

    filter_complex = (
        f"drawtext="
        f"fontfile='{title_font}':"
        f"text='{title_text}':"
        f"fontsize=main_w*{PHONE_CASE_TITLE_FONTSIZE_RATIO}:"
        f"fontcolor={PHONE_CASE_TEXT_COLOR}:"
        f"x=(main_w-text_w)/2:"
        f"y=main_h*{PHONE_CASE_TITLE_Y_RATIO}-text_h/2"
        f","
        f"drawtext="
        f"fontfile='{decor_font}':"
        f"text='{decor_text}':"
        f"fontsize=main_w*{PHONE_CASE_DECOR_FONTSIZE_RATIO}:"
        f"fontcolor={PHONE_CASE_TEXT_COLOR}:"
        f"x=(main_w-text_w)/2:"
        f"y=main_h*{PHONE_CASE_DECOR_Y_RATIO}-text_h/2"
    )

    subprocess.run(
        [
            FFMPEG,
            "-y",

            "-i",
            input_video,

            "-vf",
            filter_complex,

            "-c:v",
            "libx264",

            "-preset",
            "medium",

            "-crf",
            "18",

            "-pix_fmt",
            "yuv420p",

            "-c:a",
            "copy",

            output_video,
        ],
        check=True
    )

    print(
        "Phone case title text added:",
        output_video
    )


# ============================================================
# 4. MERGE VIDEOS
# ============================================================

def merge_videos(
        video_list,
        output_path
):
    if not video_list:
        raise ValueError(
            "No videos supplied for merge"
        )

    # NẾU CÓ ĐÚNG 1 VIDEO THÌ KHÔNG CẦN CHẠY LỆNH CONCAT CỦA FFMPEG, COPY/RENAME THẲNG
    if len(video_list) == 1:
        import shutil
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.copy(video_list[0], output_path)
        print("Copied single video instead of merging:", output_path)
        return

    os.makedirs(
        os.path.dirname(output_path),
        exist_ok=True
    )

    list_file = (
            output_path
            + ".ffmpeg_list.txt"
    )

    try:
        with open(
                list_file,
                "w",
                encoding="utf-8"
        ) as file:
            for video_path in video_list:
                absolute_path = os.path.abspath(
                    video_path
                )

                # FFmpeg concat hoạt động ổn định hơn
                # với dấu gạch chéo xuôi.
                ffmpeg_path = absolute_path.replace(
                    "\\",
                    "/"
                )

                # Escape dấu nháy đơn nếu tên file có.
                ffmpeg_path = ffmpeg_path.replace(
                    "'",
                    "'\\''"
                )

                file.write(
                    f"file '{ffmpeg_path}'\n"
                )

        subprocess.run(
            [
                FFMPEG,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                list_file,
                "-c",
                "copy",
                output_path,
            ],
            check=True
        )

    finally:
        if os.path.exists(
                list_file
        ):
            os.remove(
                list_file
            )

    print(
        "Merged:",
        output_path
    )


# ============================================================
# 5. ADD VOICE
# LEGACY VOICE-ONLY FALLBACK
# ============================================================

def add_voice(
        video_path,
        audio_path,
        output_path,
        category
):
    os.makedirs(
        os.path.dirname(output_path),
        exist_ok=True
    )

    # Sử dụng thời lượng đúng theo pipeline từng category.
    duration = get_final_video_duration(
        category
    )

    subprocess.run(
        [
            FFMPEG,
            "-y",

            "-i",
            video_path,

            "-i",
            audio_path,

            "-filter_complex",
            "[1:a]atempo=1.5,volume=2.2[audio]",

            "-map",
            "0:v:0",

            "-map",
            "[audio]",

            "-c:v",
            "copy",

            "-c:a",
            "aac",

            "-t",
            str(
                duration
            ),

            output_path,
        ],
        check=True
    )

    print(
        "Voice added:",
        output_path
    )


# ============================================================
# 6. BUILD FFMPEG FILTER COMPLEX
# ============================================================

def build_filter_complex(
        has_music,
        sfx_events
):
    """
    Input order:

        0 = merged video
        1 = voice
        2 = music, nếu có
        tiếp theo = SFX
    """

    filters = []
    mix_labels = []

    filters.append(
        "[1:a]"
        "atempo=1.5,"
        "volume=2.2,"
        "apad"
        "[voice]"
    )

    mix_labels.append(
        "[voice]"
    )

    next_index = 2

    if has_music:
        filters.append(
            f"[{next_index}:a]"
            f"volume={MUSIC_VOLUME}"
            f"[music]"
        )

        mix_labels.append(
            "[music]"
        )

        next_index += 1

    for index, sfx in enumerate(
            sfx_events
    ):
        delay_ms = int(
            sfx["time"] * 1000
        )

        if delay_ms < 0:
            delay_ms = 0

        label = (
            f"sfx{index}"
        )

        filters.append(
            f"[{next_index}:a]"
            f"adelay={delay_ms}|{delay_ms},"
            f"volume={sfx['volume'] * 0.5},"
            f"apad"
            f"[{label}]"
        )

        mix_labels.append(
            f"[{label}]"
        )

        next_index += 1

    mix_inputs = "".join(
        mix_labels
    )

    filters.append(
        f"{mix_inputs}"
        f"amix="
        f"inputs={len(mix_labels)}:"
        f"duration=first:"
        f"dropout_transition=0:"
        f"normalize=1"
        f"[aout]"
    )

    filter_complex = ";".join(
        filters
    )

    return (
        filter_complex,
        next_index
    )


# ============================================================
# 7. FINAL AUDIO MIX
# ============================================================

def add_audio(
        merged_video,
        voice_path,
        music_path,
        sfx_events,
        output_path,
        category
):
    """
    Trộn:

        Voice + Background Music + SFX

    Âm thanh gốc của Google Flow bị loại bỏ.
    """

    has_music = bool(
        music_path
    )

    inputs = [
        merged_video,
        voice_path
    ]

    if has_music:
        inputs.append(
            music_path
        )

    for sfx in sfx_events:
        inputs.append(
            sfx["path"]
        )

    filter_complex, _ = (
        build_filter_complex(
            has_music,
            sfx_events
        )
    )

    # Sử dụng thời lượng đúng theo pipeline từng category.
    duration = get_final_video_duration(
        category
    )

    command = [
        FFMPEG,
        "-y"
    ]

    for input_path in inputs:
        command += [
            "-i",
            input_path
        ]

    command += [
        "-filter_complex",
        filter_complex,

        "-map",
        "0:v:0",

        "-map",
        "[aout]",

        "-c:v",
        "copy",

        "-c:a",
        "aac",

        "-t",
        str(
            duration
        ),

        output_path,
    ]

    os.makedirs(
        os.path.dirname(output_path),
        exist_ok=True
    )

    subprocess.run(
        command,
        check=True
    )

    print(
        "Audio mixed "
        "(voice + music + sfx):",
        output_path
    )


# ============================================================
# 8. BUILD ONE PRODUCT
# ============================================================

def build_product(
        category,
        product_id
):
    product_dir = os.path.join(
        PRODUCTS_ROOT,
        category,
        product_id
    )

    video_dir = os.path.join(
        product_dir,
        "output",
        "videos"
    )

    audio_dir = os.path.join(
        product_dir,
        "output",
        "audio"
    )

    voice_path = os.path.join(
        audio_dir,
        f"{product_id}.mp3"
    )

    merged_path = os.path.join(
        video_dir,
        f"{product_id}_merged.mp4"
    )

    # Video cuối được phân theo category.
    #
    # Ví dụ:
    # videos/lipstick/LP001.mp4
    # videos/sandal/SDL001.mp4
    # videos/keychain/KC001.mp4
    # videos/phone_case/PC001.mp4
    # videos/mask/MSK001.mp4
    final_video_dir = os.path.join(
        FINAL_VIDEO_ROOT,
        category
    )

    os.makedirs(
        final_video_dir,
        exist_ok=True
    )

    final_path = os.path.join(
        final_video_dir,
        f"{product_id}.mp4"
    )

    # ========================================================
    # SKIP VIDEO ĐÃ HOÀN THÀNH
    # ========================================================
    #
    # Nếu final video đã tồn tại và file không rỗng:
    # - không merge clip lại;
    # - không mix voice / music / SFX lại;
    # - chuyển thẳng sang product tiếp theo.
    #
    # Nếu file tồn tại nhưng rỗng (0 byte), vẫn build lại.
    if file_exists_and_not_empty(
            final_path
    ):
        print(
            "Skip (final video already completed):",
            f"{category}/{product_id}"
        )

        print(
            "Existing final video:",
            final_path
        )

        return

    if not os.path.exists(
            video_dir
    ):
        print(
            "Skip (no video folder):",
            f"{category}/{product_id}"
        )

        return

    clips = get_clips(
        video_dir,
        product_id
    )

    clips = order_clips_by_category(
        category,
        clips
    )

    expected_clip_numbers = CATEGORY_CLIP_ORDER.get(
        category,
        []
    )

    if expected_clip_numbers:
        actual_clip_numbers = [
            get_clip_number(clip_path)
            for clip_path in clips
        ]

        missing_clip_numbers = [
            clip_number
            for clip_number in expected_clip_numbers
            if clip_number not in actual_clip_numbers
        ]

        if missing_clip_numbers:
            print(
                "Skip (missing required clips):",
                f"{category}/{product_id}",
                "| Missing:",
                missing_clip_numbers
            )
            return

    if len(clips) < 1:
        print(
            "Skip (no clips):",
            f"{category}/{product_id}"
        )

        return

    print("=" * 60)

    print(
        "Processing:",
        f"{category}/{product_id}"
    )

    print(
        "Clips found:"
    )

    for clip_path in clips:
        print(
            " -",
            os.path.basename(
                clip_path
            )
        )

    merge_videos(
        clips,
        merged_path
    )

    # ========================================================
    # KHÔNG CÓ VOICE
    # ========================================================

    if not file_exists_and_not_empty(
            voice_path
    ):
        print(
            "No voice found, skipping audio"
        )

        # os.replace cho phép ghi đè video cuối cũ.
        os.replace(
            merged_path,
            final_path
        )

        print(
            "DONE:",
            final_path
        )

        return

    print(
        "Voice found:",
        voice_path
    )

    # ========================================================
    # LOAD AUDIO PLAN
    # ========================================================

    plan = load_audio_plan(
        category,
        product_id
    )

    if plan:
        music_path, sfx_events = (
            extract_audio_from_plan(
                plan,
                category
            )
        )

        print(
            "Audio plan loaded"
        )

        print(
            f"SFX events: "
            f"{len(sfx_events)}"
        )

        if music_path:
            print(
                "Music:",
                music_path
            )

        for sfx in sfx_events:
            print(
                f" - {sfx['time']:.2f}s | "
                f"{os.path.basename(sfx['path'])}"
            )

    else:
        print(
            "No audio plan found"
        )

        music_path = None
        sfx_events = []

    # ========================================================
    # BUILD FINAL VIDEO
    # ========================================================

    if (
            not music_path
            and not sfx_events
    ):
        add_voice(
            merged_path,
            voice_path,
            final_path,
            category
        )

    else:
        add_audio(
            merged_path,
            voice_path,
            music_path,
            sfx_events,
            final_path,
            category
        )

    # ========================================================
    # PHONE CASE TITLE
    # ========================================================

    if category == "phone_case":
        title_video = (
                final_path
                + ".title.mp4"
        )

        add_phone_case_title(
            final_path,
            title_video
        )

        os.replace(
            title_video,
            final_path
        )

    print(
        "DONE:",
        final_path
    )


# ============================================================
# 9. BATCH ALL PRODUCTS
# ============================================================

def build_all_products():
    if not os.path.isfile(
            FFMPEG
    ):
        print(
            "FFmpeg not found:",
            FFMPEG
        )

        return

    products = get_all_products()

    print(
        "FOUND PRODUCTS:"
    )

    for category, product_id in products:
        print(
            " -",
            f"{category}/{product_id}"
        )

    for category, product_id in products:
        try:
            build_product(
                category,
                product_id
            )

        except Exception as error:
            print(
                "FAILED:",
                f"{category}/{product_id}",
                error
            )


# ============================================================
# 10. RUN
# ============================================================

if __name__ == "__main__":
    build_all_products()
