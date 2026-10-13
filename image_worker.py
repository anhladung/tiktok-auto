from playwright.sync_api import sync_playwright
from PIL import Image, ImageOps, UnidentifiedImageError
import csv
import hashlib
import os
import random
import re
import time


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

CHATGPT_URL = (
    "https://chatgpt.com/"
)

# ChatGPT hiện không cho vào thẳng project bằng link nữa,
# nên worker sẽ vào trang chủ rồi tự bấm vào project này
# trong sidebar theo TÊN (không theo mã DOM/class, vì mã đó
# giống nhau giữa rất nhiều project khác nhau).
PROJECT_NAME = "Mỹ phẩm"

CHATGPT_PROFILE_DIR = r"C:\chatgpt_auto_profile"

QUEUE_FILE = os.path.join(
    BASE_DIR,
    "queue",
    "image_queue.csv"
)

PROMPTS_ROOT_DIR = os.path.join(
    BASE_DIR,
    "prompts"
)

DEBUG_DIR = os.path.join(
    BASE_DIR,
    "debug"
)

UPLOAD_CACHE_DIR = os.path.join(
    DEBUG_DIR,
    "image_upload_cache"
)

os.makedirs(
    DEBUG_DIR,
    exist_ok=True
)

os.makedirs(
    UPLOAD_CACHE_DIR,
    exist_ok=True
)


# ============================================================
# SETTINGS
# ============================================================

MAX_ATTEMPTS = 3

# Trước: 450 giây (7 phút 30 giây).
# Rút ngắn lại còn 300 giây = 5 phút.
# Nếu ChatGPT chưa ra ảnh sau 5 phút thì coi như render timeout,
# job quay lại pending/failed theo attempts thay vì đợi quá lâu.
MAX_RENDER_TIME = 330

# Chu kỳ kiểm tra khi đang chờ ảnh được tạo (giây).
# Giảm từ 10 xuống 5 để phát hiện ảnh xong hoặc lỗi
# (rate limit, hết hạn mức, vi phạm guardrails...) nhanh hơn.
RENDER_POLL_INTERVAL_SECONDS = 5

# Tối đa 3 phút chờ ảnh input upload xong.
MAX_UPLOAD_WAIT = 180

# Nút Send phải enabled liên tục 3 giây
# mới được xem là ảnh đã upload ổn định.
UPLOAD_READY_STABLE_SECONDS = 3

# Đóng và mở lại Chrome sau khi hoàn thành
# toàn bộ ảnh của một sản phẩm.
RESTART_AFTER_PRODUCT = True

# Áp dụng cho tất cả category:
# lipstick, sandal, keychain, phone_case và category thêm sau này.
#
# Sau khi một ảnh được tạo và tải thành công:
# - đóng browser hiện tại;
# - xóa trạng thái browser/page hiện tại;
# - vòng lặp kế tiếp tự mở browser mới.
RESTART_AFTER_EACH_IMAGE = True

# Thời gian chờ sau khi đóng browser để Chrome
# và profile được giải phóng hoàn toàn.
BROWSER_RESTART_DELAY = 10


# ============================================================
# RATE LIMIT AND REQUEST PACING
# ============================================================

# Sau mỗi ảnh thành công, chờ thêm khoảng thời gian này
# trước khi bắt đầu job kế tiếp (giây).
# 300 giây = 5 phút.
DELAY_AFTER_SUCCESS_SECONDS = 300

# Giữ các biến này để không phá cấu trúc code cũ,
# nhưng trong continuous mode sẽ không dùng để ép nghỉ nữa.
IMAGES_PER_BATCH = 0
BATCH_COOLDOWN_SECONDS = 0

# Khi xuất hiện "Too many requests", cooldown tăng dần.
# Tối thiểu 30 phút ngay từ lần đầu tiên.
RATE_LIMIT_COOLDOWNS = [
    2400,  # lần 1: 30 phút
    3000,  # lần 2: 40 phút
    3600,  # lần 3: 50 phút
    4000,  # lần 4 trở đi: 60 phút
]

RATE_LIMIT_JITTER_MIN_SECONDS = 15
RATE_LIMIT_JITTER_MAX_SECONDS = 60


# ============================================================
# PLUS IMAGE GENERATION LIMIT
# ============================================================

# Cộng thêm thời gian đệm sau mốc reset ChatGPT thông báo.
IMAGE_LIMIT_RESET_BUFFER_SECONDS = 120

# Chỉ dùng khi thấy thông báo hết hạn mức nhưng không đọc được
# thời gian reset tương đối trong nội dung.
IMAGE_LIMIT_FALLBACK_WAIT_SECONDS = 3600


class TooManyRequestsError(RuntimeError):
    """
    ChatGPT đang tạm giới hạn request.

    Lỗi này được xử lý riêng:
    - không tăng attempts của job;
    - đưa job về pending;
    - đóng browser;
    - cooldown rồi mới thử lại.
    """


class ContentPolicyViolationError(RuntimeError):
    """
    ChatGPT từ chối tạo ảnh vì nghi ngờ vi phạm guardrails
    (ví dụ: "may violate our guardrails concerning similarity
    to third-party content").

    Đây KHÔNG phải lỗi tạm thời như rate limit hay hết hạn mức,
    và thử lại nhiều lần với cùng input/prompt thường vẫn sẽ
    bị từ chối tương tự. Vì vậy job này được đánh "failed"
    ngay lập tức (không tăng attempts theo kiểu retry-3-lần
    thông thường, không cooldown) rồi worker chuyển sang job
    kế tiếp.
    """


class ImageGenerationLimitError(RuntimeError):
    """Hết hạn mức tạo ảnh của ChatGPT Plus."""

    def __init__(
        self,
        message,
        wait_seconds,
        reset_description=""
    ):
        super().__init__(message)
        self.wait_seconds = int(wait_seconds)
        self.reset_description = str(
            reset_description or ""
        )


# ============================================================
# SAFE IMAGE UPLOAD SETTINGS
# ============================================================

# Ảnh input quá lớn hoặc có metadata/color profile bất thường
# có thể làm composer của ChatGPT đơ sau khi upload.
#
# Worker sẽ tạo một bản upload chuẩn hóa trong debug cache.
# Ảnh gốc không bị sửa hoặc xóa.
NORMALIZE_IMAGES_BEFORE_UPLOAD = True

# Giữ cạnh dài tối đa ở mức này.
# 2560 px vẫn đủ chi tiết cho ảnh reference nhưng nhẹ hơn
# đáng kể so với ảnh điện thoại 4000-8000 px.
MAX_UPLOAD_IMAGE_EDGE = 2560

# JPEG dùng cho ảnh không có nền trong suốt.
UPLOAD_JPEG_QUALITY = 92

# Nếu file đã nhỏ và chuẩn thì vẫn tạo bản sạch metadata.
# Việc này loại EXIF, ICC profile lạ và progressive encoding.
ALWAYS_CREATE_CLEAN_UPLOAD_COPY = True


QUEUE_FIELDNAMES = [
    "job_id",
    "category",
    "channel_id",
    "product_id",
    "step",
    "step_order",
    "status",
    "attempts",
    "input_1",
    "input_2",
    "output",
    "error",
]


# ============================================================
# GENERAL HELPERS
# ============================================================

def read_text(path):
    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:
        return file.read().strip()


def resolve_project_path(path):
    """
    Queue có thể lưu đường dẫn tương đối hoặc tuyệt đối.

    Đường dẫn tương đối sẽ được tính từ folder project,
    tức folder chứa file image_worker.py.
    """

    if not path:
        return ""

    path = os.path.expandvars(
        os.path.expanduser(
            path.strip()
        )
    )

    if os.path.isabs(path):
        return os.path.normpath(path)

    return os.path.normpath(
        os.path.join(
            BASE_DIR,
            path
        )
    )


def get_prompt_file(category, step):
    """
    Tự chọn prompt dựa trên category.

    Ví dụ:

    prompts/
        lipstick/
            image_generation/
                01_hand_holding.txt

        sandal/
            image_generation/
                01_hand_holding.txt

        keychain/
            image_generation/
                03_hand_holding.txt
                04_hand_holding_next_frame.txt

        phone_case/
            image_generation/
                01_clip_01_first_frame.txt
                02_clip_01_last_frame.txt

        mask/
            image_generation/
                01_side_view.txt
                02_front_view.txt
    """

    return os.path.join(
        PROMPTS_ROOT_DIR,
        category,
        "image_generation",
        f"{step}.txt"
    )


def sanitize_filename(value):
    """
    Làm sạch job_id trước khi dùng làm tên ảnh debug.
    """

    return re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        value
    )


def bytes_to_megabytes(size_bytes):
    return size_bytes / (1024 * 1024)


def image_has_transparency(image):
    """
    Kiểm tra ảnh có alpha/transparency hay không.
    """

    if "A" in image.getbands():
        return True

    return "transparency" in image.info


def build_upload_cache_path(source_path):
    """
    Tạo tên cache dựa trên:
    - đường dẫn nguồn;
    - dung lượng;
    - thời gian sửa file;
    - cấu hình resize.

    Nếu ảnh nguồn thay đổi, cache mới sẽ được tạo.
    """

    stat = os.stat(source_path)

    cache_key = "|".join([
        os.path.abspath(source_path),
        str(stat.st_size),
        str(stat.st_mtime_ns),
        str(MAX_UPLOAD_IMAGE_EDGE),
        str(UPLOAD_JPEG_QUALITY),
    ])

    digest = hashlib.sha256(
        cache_key.encode("utf-8")
    ).hexdigest()[:16]

    source_name = os.path.splitext(
        os.path.basename(source_path)
    )[0]

    safe_name = sanitize_filename(
        source_name
    )[:50]

    return os.path.join(
        UPLOAD_CACHE_DIR,
        f"{safe_name}_{digest}"
    )


def normalize_image_for_upload(source_path):
    """
    Kiểm tra và tạo bản ảnh upload an toàn.

    Xử lý:
    - phát hiện ảnh hỏng trước khi mở browser;
    - lấy frame đầu nếu là ảnh động;
    - sửa chiều theo EXIF;
    - thu nhỏ ảnh quá lớn;
    - chuyển mode lạ về RGB/RGBA;
    - loại EXIF, ICC profile và metadata không cần thiết;
    - lưu ảnh thường thành JPEG chuẩn;
    - giữ PNG nếu có nền trong suốt.

    Không sửa ảnh gốc.
    """

    if not os.path.isfile(source_path):
        raise FileNotFoundError(
            f"Không tìm thấy ảnh input: {source_path}"
        )

    source_size = os.path.getsize(
        source_path
    )

    try:
        with Image.open(source_path) as probe:
            probe.verify()

    except UnidentifiedImageError as error:
        raise ValueError(
            f"File không phải ảnh hợp lệ: {source_path}"
        ) from error

    except Exception as error:
        raise ValueError(
            f"Ảnh input bị lỗi hoặc không đọc được: "
            f"{source_path} | {error}"
        ) from error

    with Image.open(source_path) as image:
        if getattr(
            image,
            "is_animated",
            False
        ):
            image.seek(0)

        image = ImageOps.exif_transpose(
            image
        )

        original_width, original_height = (
            image.size
        )

        if (
            original_width <= 0
            or original_height <= 0
        ):
            raise ValueError(
                f"Kích thước ảnh không hợp lệ: "
                f"{source_path} -> {image.size}"
            )

        transparency = image_has_transparency(
            image
        )

        if transparency:
            prepared_image = image.convert(
                "RGBA"
            )
            output_extension = ".png"
        else:
            prepared_image = image.convert(
                "RGB"
            )
            output_extension = ".jpg"

        longest_edge = max(
            prepared_image.size
        )

        resized = False

        if longest_edge > MAX_UPLOAD_IMAGE_EDGE:
            scale = (
                MAX_UPLOAD_IMAGE_EDGE
                / longest_edge
            )

            resized_size = (
                max(
                    1,
                    round(
                        prepared_image.width
                        * scale
                    )
                ),
                max(
                    1,
                    round(
                        prepared_image.height
                        * scale
                    )
                ),
            )

            prepared_image = (
                prepared_image.resize(
                    resized_size,
                    Image.Resampling.LANCZOS
                )
            )

            resized = True

        cache_base = build_upload_cache_path(
            source_path
        )

        upload_path = (
            cache_base
            + output_extension
        )

        if (
            os.path.isfile(upload_path)
            and os.path.getsize(upload_path) > 0
        ):
            print(
                "Using cached safe upload image:",
                upload_path
            )

            return upload_path

        temporary_path = (
            upload_path + ".temporary"
        )

        try:
            if output_extension == ".png":
                prepared_image.save(
                    temporary_path,
                    format="PNG",
                    optimize=True
                )
            else:
                prepared_image.save(
                    temporary_path,
                    format="JPEG",
                    quality=UPLOAD_JPEG_QUALITY,
                    optimize=True,
                    progressive=False,
                    subsampling=0
                )

            os.replace(
                temporary_path,
                upload_path
            )

        finally:
            prepared_image.close()

            if os.path.exists(temporary_path):
                try:
                    os.remove(
                        temporary_path
                    )
                except OSError:
                    pass

    upload_size = os.path.getsize(
        upload_path
    )

    print(
        "Prepared safe upload image:"
    )
    print(
        "  Source:",
        source_path
    )
    print(
        "  Original:",
        f"{original_width}x{original_height},",
        f"{bytes_to_megabytes(source_size):.2f} MB"
    )
    print(
        "  Upload:",
        upload_path
    )

    with Image.open(upload_path) as check_image:
        upload_width, upload_height = (
            check_image.size
        )

    print(
        "  Prepared:",
        f"{upload_width}x{upload_height},",
        f"{bytes_to_megabytes(upload_size):.2f} MB,",
        f"resized={resized}"
    )

    return upload_path


def prepare_job_upload_paths(input_paths):
    """
    Chuẩn hóa toàn bộ input trước khi upload.

    Nếu tắt NORMALIZE_IMAGES_BEFORE_UPLOAD,
    worker dùng lại đường dẫn gốc.
    """

    if not NORMALIZE_IMAGES_BEFORE_UPLOAD:
        return [
            os.path.abspath(path)
            for path in input_paths
        ]

    prepared_paths = []

    for input_path in input_paths:
        prepared_paths.append(
            normalize_image_for_upload(
                input_path
            )
        )

    return prepared_paths


# ============================================================
# QUEUE
# ============================================================

def validate_queue_columns(fieldnames):
    missing_columns = [
        column
        for column in QUEUE_FIELDNAMES
        if column not in fieldnames
    ]

    if missing_columns:
        raise ValueError(
            "Image queue thiếu các cột bắt buộc: "
            + ", ".join(missing_columns)
        )


def load_queue():
    if not os.path.isfile(QUEUE_FILE):
        raise FileNotFoundError(
            f"Không tìm thấy image queue: {QUEUE_FILE}"
        )

    with open(
        QUEUE_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:
        reader = csv.DictReader(file)

        validate_queue_columns(
            reader.fieldnames or []
        )

        return list(reader)


def save_queue(rows):
    """
    Ghi queue qua file tạm rồi thay thế file chính.

    Cách này giảm nguy cơ làm hỏng CSV nếu worker
    bị dừng giữa lúc đang ghi file.
    """

    os.makedirs(
        os.path.dirname(QUEUE_FILE),
        exist_ok=True
    )

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
            fieldnames=QUEUE_FIELDNAMES,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(rows)

    os.replace(
        temporary_file,
        QUEUE_FILE
    )


def update_job(job_id, **updates):
    rows = load_queue()
    found = False

    for row in rows:
        if row["job_id"] != job_id:
            continue

        for key, value in updates.items():
            if key not in QUEUE_FIELDNAMES:
                raise KeyError(
                    f"Queue field không hợp lệ: {key}"
                )

            row[key] = str(value)

        found = True
        break

    if not found:
        raise KeyError(
            f"Không tìm thấy job_id trong queue: {job_id}"
        )

    save_queue(rows)


def parse_step_order(row):
    try:
        return int(
            row.get("step_order") or 0
        )
    except ValueError:
        return 0


def get_blocking_previous_steps(
    rows,
    current_job
):
    """
    Bảo đảm các frame của cùng một sản phẩm chạy đúng step_order.

    Áp dụng generic cho mọi category.

    Ví dụ pipeline mới:

    keychain:
        1. 03_hand_holding
        2. 04_hand_holding_next_frame

    phone_case:
        1. 01_clip_01_first_frame
        2. 02_clip_01_last_frame

    mask:
        1. 01_side_view
        2. 02_front_view

    Một step chỉ được chạy khi tất cả step_order trước đó
    của cùng category + product_id đã có status = done.

    Điều này cũng giữ an toàn cho lipstick và sandal,
    vì các frame nối tiếp của chúng phụ thuộc output trước.
    """

    category = (
        current_job.get("category") or ""
    ).strip().lower()

    product_id = (
        current_job.get("product_id") or ""
    ).strip()

    current_step_order = parse_step_order(
        current_job
    )

    if (
        not category
        or not product_id
        or current_step_order <= 1
    ):
        return []

    blocking_rows = []

    for row in rows:
        row_category = (
            row.get("category") or ""
        ).strip().lower()

        row_product_id = (
            row.get("product_id") or ""
        ).strip()

        row_step_order = parse_step_order(
            row
        )

        if row_category != category:
            continue

        if row_product_id != product_id:
            continue

        if row_step_order >= current_step_order:
            continue

        row_status = (
            row.get("status") or ""
        ).strip().lower()

        if row_status != "done":
            blocking_rows.append(
                row
            )

    blocking_rows.sort(
        key=parse_step_order
    )

    return blocking_rows


def get_job_input_paths(job):
    """
    input_1 là bắt buộc.
    input_2 là tùy chọn và được quyết định hoàn toàn bởi queue.

    Pipeline hiện tại:

    Lipstick:
        4 frame, input thay đổi theo từng step.

    Sandal:
        4 frame, input thay đổi theo từng step.

    Keychain — pipeline mới:
        Step 1 / 03_hand_holding:
            product + hand background.

        Step 2 / 04_hand_holding_next_frame:
            output của Step 1.

        Không còn frame balo.

    Phone case — pipeline mới:
        Step 1 / 01_clip_01_first_frame:
            product + background.

        Step 2 / 02_clip_01_last_frame:
            output của Step 1.

        Chỉ còn 2 frame / 1 clip.

    Mask:
        Step 1 / 01_side_view:
            product + hand background.

        Step 2 / 02_front_view:
            output Frame 01 + product reference.

        Chỉ có 2 frame / 1 clip.

    Worker không hard-code số input theo category.
    Nó đọc trực tiếp input_1 và input_2 từ image_queue.csv.
    """


    input_paths = []

    input_1_raw = (
        job.get("input_1") or ""
    ).strip()

    input_2_raw = (
        job.get("input_2") or ""
    ).strip()

    if input_1_raw:
        input_paths.append(
            resolve_project_path(
                input_1_raw
            )
        )

    if input_2_raw:
        input_paths.append(
            resolve_project_path(
                input_2_raw
            )
        )

    return input_paths


def get_next_pending_job(rows):
    pending = [
        row
        for row in rows
        if (
            row.get("status", "")
            .strip()
            .lower()
            == "pending"
        )
    ]

    print(
        "Pending jobs:",
        len(pending)
    )

    pending.sort(
        key=lambda row: (
            row.get(
                "category",
                ""
            ).lower(),

            row.get(
                "product_id",
                ""
            ).lower(),

            parse_step_order(row),
        )
    )

    for job in pending:
        job_id = (
            job.get("job_id") or ""
        ).strip()

        category = (
            job.get("category") or ""
        ).strip()

        product_id = (
            job.get("product_id") or ""
        ).strip()

        step = (
            job.get("step") or ""
        ).strip()

        print("=" * 60)
        print(
            "Checking:",
            job_id
        )

        if not category:
            print(
                "SKIP REASON: queue job thiếu category"
            )
            continue

        if not product_id:
            print(
                "SKIP REASON: queue job thiếu product_id"
            )
            continue

        if not step:
            print(
                "SKIP REASON: queue job thiếu step"
            )
            continue

        step_order = parse_step_order(
            job
        )

        print(
            "Step order:",
            step_order
        )

        blocking_previous_steps = (
            get_blocking_previous_steps(
                rows,
                job
            )
        )

        if blocking_previous_steps:
            print(
                "SKIP REASON: previous step(s) of this "
                "product are not done yet"
            )

            for blocking_row in blocking_previous_steps:
                print(
                    "  Waiting:",
                    blocking_row.get("job_id", ""),
                    "| step_order=",
                    parse_step_order(
                        blocking_row
                    ),
                    "| status=",
                    (
                        blocking_row.get("status")
                        or ""
                    ).strip()
                )

            continue

        prompt_file = get_prompt_file(
            category,
            step
        )

        input_paths = get_job_input_paths(
            job
        )

        print(
            "Category:",
            category
        )

        print(
            "Prompt:",
            prompt_file,
            os.path.isfile(prompt_file)
        )

        if input_paths:
            for index, input_path in enumerate(
                input_paths,
                start=1
            ):
                print(
                    f"Input {index}:",
                    input_path,
                    os.path.isfile(input_path)
                )
        else:
            print(
                "Inputs: none"
            )

        if not os.path.isfile(prompt_file):
            print(
                "SKIP REASON: missing prompt"
            )
            continue

        if not input_paths:
            print(
                "SKIP REASON: missing input_1"
            )
            continue

        missing_inputs = [
            input_path
            for input_path in input_paths
            if not os.path.isfile(input_path)
        ]

        if missing_inputs:
            print(
                "SKIP REASON: one or more inputs "
                "do not exist"
            )

            for missing_input in missing_inputs:
                print(
                    "  Missing:",
                    missing_input
                )

            continue

        output_path = resolve_project_path(
            job.get("output") or ""
        )

        if not output_path:
            print(
                "SKIP REASON: missing output path"
            )
            continue

        runnable_job = dict(job)

        runnable_job["category"] = category
        runnable_job["product_id"] = product_id
        runnable_job["step"] = step

        runnable_job["prompt_file"] = (
            prompt_file
        )

        runnable_job["input_paths"] = (
            input_paths
        )

        runnable_job["output_path"] = (
            output_path
        )

        print(
            "Runnable job found:",
            job_id
        )

        return runnable_job

    return None


def is_product_finished(
    rows,
    category,
    product_id
):
    """
    Không dùng tên step cuối cố định.

    Sản phẩm hoàn thành khi tất cả job thuộc đúng
    category và product_id đều có status done.
    """

    product_jobs = [
        row
        for row in rows
        if (
            (
                row.get("category") or ""
            ).strip()
            == category
            and
            (
                row.get("product_id") or ""
            ).strip()
            == product_id
        )
    ]

    if not product_jobs:
        return False

    return all(
        (
            row.get("status", "")
            .strip()
            .lower()
            == "done"
        )
        for row in product_jobs
    )


# ============================================================
# CHATGPT PLUS IMAGE GENERATION LIMIT
# ============================================================

def parse_relative_reset_seconds(message_text):
    """
    Đọc thời gian từ các câu như:
    limit resets in 4 hours and 23 minutes.
    """

    normalized = " ".join(
        str(message_text or "")
        .lower()
        .split()
    )

    reset_match = re.search(
        r"limit\s+resets?\s+in\s+([^\.\n]+)",
        normalized,
        flags=re.IGNORECASE
    )

    if not reset_match:
        return None, ""

    reset_description = (
        reset_match.group(1).strip()
    )

    unit_patterns = [
        (86400, r"(\d+)\s*(?:days?|d)\b"),
        (3600, r"(\d+)\s*(?:hours?|hrs?|h)\b"),
        (60, r"(\d+)\s*(?:minutes?|mins?|min|m)\b"),
        (1, r"(\d+)\s*(?:seconds?|secs?|sec|s)\b"),
    ]

    total_seconds = 0
    found_any = False

    for multiplier, pattern in unit_patterns:
        unit_match = re.search(
            pattern,
            reset_description,
            flags=re.IGNORECASE
        )

        if not unit_match:
            continue

        found_any = True
        total_seconds += (
            int(unit_match.group(1))
            * multiplier
        )

    if not found_any or total_seconds <= 0:
        return None, reset_description

    return total_seconds, reset_description


def format_wait_duration(total_seconds):
    total_seconds = max(0, int(total_seconds))

    days, remainder = divmod(
        total_seconds,
        86400
    )
    hours, remainder = divmod(
        remainder,
        3600
    )
    minutes, seconds = divmod(
        remainder,
        60
    )

    parts = []

    if days:
        parts.append(f"{days} day(s)")
    if hours:
        parts.append(f"{hours} hour(s)")
    if minutes:
        parts.append(f"{minutes} minute(s)")
    if seconds or not parts:
        parts.append(f"{seconds} second(s)")

    return " ".join(parts)


def get_new_assistant_messages(
    page,
    before_assistant_count
):
    """
    Chỉ lấy assistant message mới của job hiện tại.
    """

    if page is None or page.is_closed():
        return []

    messages = page.locator(
        "div[data-message-author-role='assistant']"
    )

    try:
        current_count = messages.count()
    except Exception:
        return []

    if current_count <= before_assistant_count:
        return []

    new_texts = []

    for index in range(
        before_assistant_count,
        current_count
    ):
        try:
            message = messages.nth(index)
            message_text = (
                message.inner_text(
                    timeout=10000
                ).strip()
            )

            if message_text:
                new_texts.append(message_text)
        except Exception:
            continue

    return new_texts


def raise_if_image_generation_limit(
    page,
    before_assistant_count,
    stage
):
    """
    Phát hiện phản hồi hết hạn mức tạo ảnh Plus, đọc thời gian
    reset tương đối rồi yêu cầu main đợi đúng thời gian đó.
    """

    new_messages = get_new_assistant_messages(
        page,
        before_assistant_count
    )

    if not new_messages:
        return

    limit_phrases = [
        (
            "you've hit the plus plan limit "
            "for image generations requests"
        ),
        (
            "you have hit the plus plan limit "
            "for image generations requests"
        ),
        (
            "you've hit the plus plan limit "
            "for image generation requests"
        ),
        (
            "you have hit the plus plan limit "
            "for image generation requests"
        ),
        (
            "i was unable to invoke the "
            "image-generation tool right now"
        ),
    ]

    for message_text in new_messages:
        normalized = " ".join(
            message_text.lower().split()
        )

        if not any(
            phrase in normalized
            for phrase in limit_phrases
        ):
            continue

        parsed_seconds, reset_description = (
            parse_relative_reset_seconds(
                message_text
            )
        )

        if parsed_seconds is None:
            parsed_seconds = (
                IMAGE_LIMIT_FALLBACK_WAIT_SECONDS
            )
            print(
                "Could not parse reset time. "
                "Using fallback wait."
            )

        wait_seconds = (
            parsed_seconds
            + IMAGE_LIMIT_RESET_BUFFER_SECONDS
        )

        print("=" * 60)
        print(
            "PLUS IMAGE GENERATION LIMIT DETECTED"
        )
        print("Stage:", stage)
        print(
            "Reset text:",
            reset_description or "not parsed"
        )
        print(
            "Wait before retry:",
            format_wait_duration(wait_seconds)
        )
        print("=" * 60)

        raise ImageGenerationLimitError(
            (
                "ChatGPT Plus image-generation limit "
                f"detected at stage: {stage}"
            ),
            wait_seconds=wait_seconds,
            reset_description=reset_description
        )


# Các cụm từ ChatGPT dùng khi từ chối ảnh vì nghi ngờ vi phạm
# guardrails / giống nội dung bên thứ ba. So khớp dạng đã
# normalize (lowercase, gộp khoảng trắng) nên không cần khớp
# hoa/thường hay xuống dòng chính xác.
CONTENT_POLICY_VIOLATION_PHRASES = [
    (
        "may violate our guardrails concerning "
        "similarity to third-party content"
    ),
    (
        "may violate our content policy"
    ),
    (
        "can't generate that image"
    ),
    (
        "unable to create this image due to our "
        "content policies"
    ),
]


def raise_if_content_policy_violation(
    page,
    before_assistant_count,
    stage
):
    """
    Phát hiện phản hồi kiểu "may violate our guardrails
    concerning similarity to third-party content" (hoặc các
    cụm từ chối tương tự do vi phạm chính sách nội dung).

    Khác với rate limit / hết hạn mức Plus (là lỗi tạm thời,
    có thể đợi rồi thử lại), đây là lỗi liên quan tới NỘI DUNG
    của job (ảnh input/prompt bị ChatGPT coi là giống bên thứ
    ba), nên raise một exception RIÊNG để main() đánh job này
    là "failed" ngay, không cooldown, không đợi, và chuyển
    sang job kế tiếp luôn.
    """

    new_messages = get_new_assistant_messages(
        page,
        before_assistant_count
    )

    if not new_messages:
        return

    for message_text in new_messages:
        normalized = " ".join(
            message_text.lower().split()
        )

        matched_phrase = next(
            (
                phrase
                for phrase in (
                    CONTENT_POLICY_VIOLATION_PHRASES
                )
                if phrase in normalized
            ),
            None
        )

        if matched_phrase is None:
            continue

        print("=" * 60)
        print(
            "CONTENT POLICY / GUARDRAILS VIOLATION DETECTED"
        )
        print("Stage:", stage)
        print(
            "Matched phrase:",
            matched_phrase
        )
        print(
            "Full message:",
            message_text
        )
        print("=" * 60)

        raise ContentPolicyViolationError(
            "ChatGPT refused image due to guardrails/content "
            f"policy at stage: {stage} | message: {message_text}"
        )


# ============================================================
# CLOUDFLARE HUMAN VERIFICATION
# ============================================================

def handle_human_verification_checkbox(page):
    """
    Cloudflare Turnstile thỉnh thoảng chèn ô
    "Verify you are human" vào trang.

    Widget này thường nằm trong iframe riêng (không phải
    page chính), nên phải quét qua tất cả frame hiện có.

    Hàm không raise lỗi: nếu không tìm thấy hoặc click thất bại,
    coi như không có gì để xử lý và để luồng chính tự thử lại
    ở vòng lặp sau.
    """

    if (
        page is None
        or page.is_closed()
    ):
        return False

    try:
        frames = list(page.frames)
    except Exception:
        return False

    for frame in frames:
        try:
            checkbox = frame.locator(
                'input[type="checkbox"]'
                '[aria-label="Verify you are human"]'
            ).first

            if checkbox.count() == 0:
                continue

            if not checkbox.is_visible():
                continue

            if checkbox.is_checked():
                continue

            print(
                "Cloudflare human verification checkbox "
                "detected. Clicking checkbox."
            )

            checkbox.click(
                force=True,
                timeout=5000
            )

            print(
                "Clicked human verification checkbox."
            )

            time.sleep(3)

            return True

        except Exception:
            continue

    return False


# ============================================================
# CHATGPT RATE LIMIT
# ============================================================

def get_too_many_requests_dialog(page):
    """
    Tìm hộp thoại rate limit bằng role và nội dung ổn định,
    không dùng radix id động.
    """

    if (
        page is None
        or page.is_closed()
    ):
        return None

    dialog = (
        page.locator(
            "div[role='dialog']"
        )
        .filter(
            has_text="Too many requests"
        )
        .first
    )

    try:
        if (
            dialog.count() > 0
            and dialog.is_visible()
        ):
            return dialog
    except Exception:
        return None

    return None


def raise_if_too_many_requests(
    page,
    stage
):
    """
    Nếu thấy Too many requests thì đóng bảng Got it và
    raise lỗi riêng để main dừng request, đóng browser và nghỉ.
    """

    dialog = get_too_many_requests_dialog(
        page
    )

    if dialog is None:
        return

    print("=" * 60)
    print(
        "TOO MANY REQUESTS DETECTED"
    )
    print(
        "Stage:",
        stage
    )
    print("=" * 60)

    try:
        got_it_button = (
            dialog.get_by_role(
                "button",
                name="Got it"
            )
            .first
        )

        if (
            got_it_button.count() > 0
            and got_it_button.is_visible()
        ):
            got_it_button.click(
                force=True
            )

            print(
                "Clicked Got it."
            )

            time.sleep(1)

    except Exception as dismiss_error:
        print(
            "Could not dismiss rate-limit dialog:",
            dismiss_error
        )

    raise TooManyRequestsError(
        "ChatGPT Too many requests "
        f"detected at stage: {stage}"
    )


def get_rate_limit_cooldown(
    consecutive_rate_limits
):
    """
    Cooldown tăng dần và có jitter.
    """

    index = min(
        max(
            consecutive_rate_limits - 1,
            0
        ),
        len(RATE_LIMIT_COOLDOWNS) - 1
    )

    base_cooldown = (
        RATE_LIMIT_COOLDOWNS[index]
    )

    jitter = random.randint(
        RATE_LIMIT_JITTER_MIN_SECONDS,
        RATE_LIMIT_JITTER_MAX_SECONDS
    )

    return base_cooldown + jitter


def get_post_success_delay(
    successful_images_since_break
):
    """
    Continuous mode:
    - không nghỉ chủ động sau ảnh thành công;
    - chỉ cooldown khi gặp Too many requests.

    Vẫn trả tuple để giữ nguyên giao diện cũ.
    """

    return 0, False


# ============================================================
# CHATGPT BROWSER
# ============================================================

def ensure_sidebar_open(
    page,
    quick_timeout=3000
):
    """
    Đảm bảo sidebar dọc của ChatGPT đang ở trạng thái MỞ.

    HIỂU ĐÚNG CẤU TRÚC (quan trọng, tránh sửa sai lần nữa):

        <div id="stage-slideover-sidebar" data-state="closed">
            <nav id="stage-sidebar-tiny-bar" ...>
                <button aria-label="Open sidebar" ...>
            </nav>
            <div class="... opacity-0 ..." inert>
                ...toàn bộ sidebar thật: search, project
                "Mỹ phẩm", nút "Close sidebar"...
            </div>
        </div>

    CẢ 2 trạng thái (thanh gọn + sidebar đầy đủ) đều LUÔN TỒN
    TẠI SẴN trong DOM cùng lúc. Khi đóng, phần sidebar đầy đủ
    có thuộc tính "inert" - thuộc tính này khiến trình duyệt
    loại bỏ TOÀN BỘ nhánh đó khỏi accessibility tree, nên
    page.get_by_role(...) sẽ KHÔNG BAO GIỜ tìm thấy project dù
    bấm đúng nút hay không, chừng nào "inert" còn đó. Đây là
    lý do các cách dò tìm bằng get_by_role trước đây hay bị
    timeout khi sidebar đóng.

    Cờ trạng thái đáng tin cậy nhất là data-state="open"/"closed"
    trên chính #stage-slideover-sidebar - dùng cái này để check
    thay vì cố tìm project.

    Để mở: bấm nút "Open sidebar" (trong <nav id=
    "stage-sidebar-tiny-bar">, KHÔNG bị inert nên luôn bấm
    được). Bấm bằng cách gửi ĐẦY ĐỦ chuỗi sự kiện chuột thật
    qua JS (pointerdown -> mousedown -> pointerup -> mouseup
    -> click) vì nhiều component kiểu Radix UI lắng nghe
    pointerdown/pointerup, không chỉ mỗi "click" - gọi suông
    .click() có thể không đủ để kích hoạt.
    """

    def sidebar_is_open():
        try:
            return bool(
                page.evaluate(
                    """
                    () => {
                        const el = document.querySelector(
                            '#stage-slideover-sidebar'
                        );
                        return (
                            !!el
                            && el.getAttribute('data-state')
                                === 'open'
                        );
                    }
                    """
                )
            )
        except Exception:
            return False

    if sidebar_is_open():
        return

    print(
        "Sidebar dang dong (data-state != 'open'). Thu bam "
        "nut 'Open sidebar' bang chuoi su kien chuot day du "
        "qua JS..."
    )

    page.evaluate(
        """
        () => {
            const btn = document.querySelector(
                'button[aria-label="Open sidebar"]'
            );

            if (!btn) {
                return false;
            }

            const rect = btn.getBoundingClientRect();
            const x = rect.left + rect.width / 2;
            const y = rect.top + rect.height / 2;

            const opts = {
                bubbles: true,
                cancelable: true,
                view: window,
                clientX: x,
                clientY: y,
                pointerId: 1,
                isPrimary: true
            };

            const events = [
                new PointerEvent('pointerdown', opts),
                new MouseEvent('mousedown', opts),
                new PointerEvent('pointerup', opts),
                new MouseEvent('mouseup', opts),
                new MouseEvent('click', opts)
            ];

            events.forEach(
                (event) => btn.dispatchEvent(event)
            );

            return true;
        }
        """
    )

    page.wait_for_timeout(1000)

    if sidebar_is_open():
        print(
            "Da mo sidebar thanh cong."
        )
        return

    # Phương án dự phòng: gọi .click() DOM thuần, đơn giản
    # hơn chuỗi sự kiện ở trên, phòng trường hợp chuỗi sự
    # kiện đầy đủ lại vô tình không khớp handler thực tế.
    print(
        "Chuoi su kien chuot chua mo duoc sidebar. Thu goi "
        ".click() DOM thuan..."
    )

    page.evaluate(
        """
        () => {
            const btn = document.querySelector(
                'button[aria-label="Open sidebar"]'
            );

            if (btn) {
                btn.click();
            }
        }
        """
    )

    page.wait_for_timeout(1000)

    if sidebar_is_open():
        print(
            "Da mo sidebar thanh cong (qua .click() DOM "
            "thuan)."
        )
        return

    print(
        "Van chua mo duoc sidebar sau khi thu ca 2 cach. "
        "De open_project() tu bao loi ro rang neu van khong "
        "tim thay project."
    )


def open_project(
    page,
    project_name=PROJECT_NAME,
    timeout=30000
):
    """
    Bấm vào project trong sidebar theo TÊN hiển thị, không theo
    mã DOM (data-sidebar-item, aria-controls...) vì các mã đó
    lặp lại giống nhau ở mọi project, không phân biệt được.

    Cách làm: dùng "accessible name" của nút (role=button).
    Với đoạn HTML sidebar dạng:

        <div role="button" data-sidebar-item="true" ...>
            ...icon svg...
            <span data-marquee-text="true">
                ...
                <span class="_NCija_content">Mỹ phẩm</span>
            </span>
        </div>

    accessible name của nút chính là text "Mỹ phẩm" (icon svg
    không có text nên không ảnh hưởng). Cách này không phụ
    thuộc class CSS (kiểu _NCija_content) là những class có
    thể đổi bất kỳ lúc nào.

    exact=True để tránh bấm nhầm project có tên gần giống,
    ví dụ "Mỹ phẩm" và "Mỹ phẩm 2".
    """

    print(
        "Opening project in sidebar:",
        project_name
    )

    ensure_sidebar_open(page)

    project_button = page.get_by_role(
        "button",
        name=project_name,
        exact=True
    )

    try:
        project_button.first.wait_for(
            state="visible",
            timeout=timeout
        )
    except Exception as error:
        print(
            "Could not find project button "
            f"'{project_name}' in sidebar:",
            error
        )
        raise

    # Nếu có nhiều phần tử trùng accessible name (ví dụ project
    # xuất hiện cả ở danh sách ghim và danh sách gần đây), luôn
    # lấy phần tử đầu tiên đang hiển thị.
    project_button.first.scroll_into_view_if_needed(
        timeout=timeout
    )

    project_button.first.click(
        timeout=timeout
    )

    page.wait_for_timeout(2000)

    print(
        "Project opened:",
        project_name
    )


def open_project_home(
    page,
    project_name=PROJECT_NAME,
    timeout=30000
):
    """
    Bấm nút "Open project home" (icon cây bút, data-trailing-button).

    QUAN TRỌNG: nút này KHÔNG chỉ có 1 cái trên trang. Mỗi dòng
    project trong sidebar đều có nút riêng của nó (chỉ ẩn bằng
    CSS lúc hover, DOM vẫn luôn tồn tại và vẫn "visible" theo
    Playwright). Nếu tìm get_by_role("button", name="Open
    project home") trên toàn page, Playwright sẽ luôn lấy nút
    của project ĐẦU TIÊN trong danh sách, không phải project
    mình vừa mở.

    Thực tế nút "Open project home" KHÔNG nằm bên trong div
    role="button" của dòng project (đã thử và bị timeout), mà
    là một phần tử "anh em" (sibling) nằm ở một thẻ cha bao
    ngoài nào đó mà mình không biết trước độ sâu chính xác.

    Thay vì đoán tiếp cấu trúc HTML (dễ sai lần nữa mỗi khi
    ChatGPT đổi giao diện), hàm này để TRÌNH DUYỆT tự leo lên
    cây DOM (bằng JS) từ dòng project, tại mỗi cấp cha kiểm
    tra xem trong đó có nút "Open project home" hay không, và
    dừng lại ngay khi tìm thấy nút GẦN NHẤT. Nhờ dừng ở cấp
    gần nhất, nút tìm được luôn thuộc về đúng dòng "Mỹ phẩm",
    không lẫn sang project khác nằm xa hơn trong danh sách.
    """

    print(
        "Clicking 'Open project home' button "
        f"for project: {project_name}"
    )

    project_row = page.get_by_role(
        "button",
        name=project_name,
        exact=True
    ).first

    try:
        project_row.wait_for(
            state="visible",
            timeout=timeout
        )
    except Exception as error:
        print(
            "Could not find project row "
            f"'{project_name}' to scope search:",
            error
        )
        raise

    # Hover trước để CSS/JS của ChatGPT kích hoạt trạng thái
    # hover thật sự trên đúng dòng này (một số UI cần hover
    # thật để bật pointer-events hoặc render nút).
    project_row.hover(
        timeout=timeout
    )

    row_handle = project_row.element_handle(
        timeout=timeout
    )

    if row_handle is None:
        raise RuntimeError(
            f"Could not get element handle for project row "
            f"'{project_name}'"
        )

    # Leo dần lên các thẻ cha (tối đa MAX_CLIMB_LEVELS lần),
    # tại mỗi cấp tìm nút "Open project home" nằm trong đó.
    # Dừng ngay khi tìm thấy -> đó là nút gần dòng project
    # nhất, tránh vớ nhầm nút của project khác ở xa hơn.
    button_handle = page.evaluate_handle(
        """
        (row) => {
            const MAX_CLIMB_LEVELS = 8;
            let el = row;
            for (
                let level = 0;
                level < MAX_CLIMB_LEVELS && el;
                level++
            ) {
                const btn = el.querySelector(
                    'button[aria-label="Open project home"]'
                );
                if (btn) {
                    return btn;
                }
                el = el.parentElement;
            }
            return null;
        }
        """,
        row_handle
    )

    project_home_button = (
        button_handle.as_element()
    )

    if project_home_button is None:
        print(
            "Could not find 'Open project home' button near "
            f"row '{project_name}' by climbing up to 8 parent "
            "levels. Gui minh HTML day du (khong bi cat) cua "
            "ca khoi project trong sidebar de sua tiep."
        )
        raise RuntimeError(
            "Open project home button not found near "
            f"project row '{project_name}'"
        )

    project_home_button.scroll_into_view_if_needed(
        timeout=timeout
    )

    project_home_button.click(
        timeout=timeout
    )

    page.wait_for_timeout(2000)

    print(
        "Project home opened."
    )


def open_chatgpt(playwright):
    browser = (
        playwright.chromium
        .launch_persistent_context(
            user_data_dir=CHATGPT_PROFILE_DIR,
            headless=False,
            accept_downloads=True,
            args=[
                "--window-size=1600,1000",
                "--window-position=0,0",
            ]
        )
    )

    # QUAN TRỌNG: mọi bước sau khi đã launch browser đều được
    # bọc trong try/except. Nếu bất kỳ bước nào bên dưới raise
    # lỗi (vd Too many requests), biến "browser" ở đây CHỈ tồn
    # tại cục bộ trong hàm này - nếu để lỗi bay thẳng ra ngoài
    # mà không tự đóng, browser đang gọi sẽ KHÔNG được caller
    # đóng (vì lệnh gán "browser, page = open_chatgpt(...)" ở
    # nơi gọi không bao giờ hoàn tất do exception), dẫn tới rò
    # rỉ tiến trình Chrome chạy ngầm mãi không đóng được.
    try:
        if browser.pages:
            page = browser.pages[0]
        else:
            page = browser.new_page()

        page.goto(
            CHATGPT_URL,
            wait_until="domcontentloaded",
            timeout=120000
        )

        print(
            "Waiting ChatGPT load..."
        )

        time.sleep(8)

        # QUAN TRỌNG: check "Too many requests" NGAY ở đây,
        # trước khi làm bất kỳ thao tác nào khác (xác minh, mở
        # sidebar, mở project...). Trước đây hàm này không
        # check gì cả cho tới tận các bước sau trong vòng lặp
        # job chính - nếu bảng "Too many requests" hiện ra
        # ngay lúc mới vào ChatGPT, code sẽ không phát hiện
        # được mà cứ cố click linh tinh vào sidebar/project
        # trong khi bị modal chặn, dẫn tới các lỗi khó hiểu
        # khác thay vì báo đúng nguyên nhân thật.
        raise_if_too_many_requests(
            page,
            "right after opening ChatGPT (before "
            "verification/project navigation)"
        )

        handle_human_verification_checkbox(
            page
        )

        open_project(
            page,
            project_name=PROJECT_NAME
        )

        open_project_home(
            page,
            project_name=PROJECT_NAME
        )
    except Exception:
        print(
            "Loi trong luc mo ChatGPT - dong browser vua "
            "launch de tranh ro ri tien trinh Chrome truoc "
            "khi bao loi ra ngoai..."
        )

        close_browser(
            browser
        )

        raise

    return browser, page

def reload_chatgpt_after_image(page):
    """
    Reload trang sau khi đã tạo và tải xong một ảnh.

    Hàm không raise lỗi để tránh trường hợp ảnh đã tải xong
    nhưng job lại bị chuyển ngược thành pending/failed chỉ vì
    thao tác reload gặp lỗi.
    """

    print(
        "Reloading ChatGPT page "
        "before next image..."
    )

    try:
        page.reload(
            wait_until="domcontentloaded",
            timeout=120000
        )

        print(
            "Waiting ChatGPT reload..."
        )

        time.sleep(8)

        handle_human_verification_checkbox(
            page
        )

        print(
            "ChatGPT page reloaded."
        )

        return True

    except Exception as reload_error:
        print(
            "Could not reload ChatGPT page:",
            reload_error
        )

        return False


def upload_input_files(
    page,
    input_paths
):
    """
    Upload được cả 1 ảnh hoặc 2 ảnh.

    FIX giao diện ChatGPT mới:
    - không phụ thuộc hoàn toàn vào event filechooser;
    - ưu tiên set_input_files trực tiếp vào input[type=file];
    - nếu input chưa tồn tại thì mở menu + và thử
      "Add photos & files";
    - có nhiều selector fallback;
    - retry một lần nếu menu/input chưa sẵn sàng;
    - lưu screenshot debug nếu upload vẫn thất bại.

    Không dùng pyautogui hoặc pyperclip.
    """

    raise_if_too_many_requests(
        page,
        "before uploading input images"
    )

    absolute_paths = [
        os.path.abspath(path)
        for path in input_paths
    ]

    for path in absolute_paths:
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"Upload input not found: {path}"
            )

    def try_direct_file_input():
        file_inputs = page.locator(
            "input[type='file']"
        )

        try:
            count = file_inputs.count()
        except Exception:
            count = 0

        if count <= 0:
            return False

        for index in range(
            count - 1,
            -1,
            -1
        ):
            try:
                file_input = file_inputs.nth(
                    index
                )

                file_input.set_input_files(
                    absolute_paths,
                    timeout=30000
                )

                print(
                    "Uploaded through direct file input:",
                    f"input index {index}"
                )

                return True

            except Exception as input_error:
                print(
                    "Direct file input skipped:",
                    f"index {index} | {input_error}"
                )

        return False

    def open_plus_menu():
        plus_button = page.locator(
            'button[data-testid="composer-plus-btn"]'
        ).first

        plus_button.wait_for(
            state="visible",
            timeout=30000
        )

        plus_button.click(
            force=True
        )

        print(
            "Clicked plus button"
        )

        time.sleep(1)

    def get_add_files_button():
        candidates = [
            page.get_by_role(
                "menuitem",
                name=re.compile(
                    r"Add photos\s*&\s*files",
                    re.IGNORECASE
                )
            ).first,

            page.get_by_role(
                "button",
                name=re.compile(
                    r"Add photos\s*&\s*files",
                    re.IGNORECASE
                )
            ).first,

            page.get_by_text(
                re.compile(
                    r"^\s*Add photos\s*&\s*files\s*$",
                    re.IGNORECASE
                )
            ).first,

            page.get_by_text(
                re.compile(
                    r"^\s*Thêm ảnh.*tệp\s*$",
                    re.IGNORECASE
                )
            ).first,
        ]

        for candidate in candidates:
            try:
                if (
                    candidate.count() > 0
                    and candidate.is_visible()
                ):
                    return candidate
            except Exception:
                continue

        return None

    upload_completed = False
    last_error = None

    if try_direct_file_input():
        upload_completed = True

    if not upload_completed:
        try:
            open_plus_menu()

            if try_direct_file_input():
                upload_completed = True

        except Exception as error:
            last_error = error

            print(
                "Could not use direct input after opening +:",
                error
            )

    if not upload_completed:
        for attempt in range(2):
            try:
                add_files_button = (
                    get_add_files_button()
                )

                if add_files_button is None:
                    open_plus_menu()
                    time.sleep(1)

                    add_files_button = (
                        get_add_files_button()
                    )

                if add_files_button is None:
                    raise RuntimeError(
                        "Add photos & files button "
                        "was not found or visible."
                    )

                print(
                    "Found Add photos & files button"
                )

                with page.expect_file_chooser(
                    timeout=15000
                ) as file_chooser_info:
                    add_files_button.click(
                        force=True
                    )

                file_chooser = (
                    file_chooser_info.value
                )

                file_chooser.set_files(
                    absolute_paths
                )

                print(
                    "Uploaded through file chooser"
                )

                upload_completed = True
                break

            except Exception as error:
                last_error = error

                print(
                    "Upload via Add photos & files failed:",
                    f"attempt {attempt + 1}/2 | {error}"
                )

                try:
                    if try_direct_file_input():
                        upload_completed = True
                        break
                except Exception:
                    pass

                if attempt == 0:
                    try:
                        page.keyboard.press(
                            "Escape"
                        )
                    except Exception:
                        pass

                    time.sleep(1)

    if not upload_completed:
        debug_path = os.path.join(
            DEBUG_DIR,
            "image_worker_add_photos_files_failed.png"
        )

        try:
            page.screenshot(
                path=debug_path,
                full_page=True
            )

            print(
                "Upload debug screenshot:",
                debug_path
            )
        except Exception as screenshot_error:
            print(
                "Could not save upload debug screenshot:",
                screenshot_error
            )

        raise RuntimeError(
            "Could not upload input images. "
            "Neither direct input[type=file] nor "
            "Add photos & files filechooser worked. "
            f"Last error: {last_error}"
        )

    print(
        f"Uploaded {len(absolute_paths)} input file(s)"
    )

    time.sleep(8)

    raise_if_too_many_requests(
        page,
        "after uploading input images"
    )


def fill_prompt(
    page,
    prompt
):
    raise_if_too_many_requests(
        page,
        "before filling prompt"
    )

    prompt_box = page.locator(
        "#prompt-textarea"
    )

    prompt_box.wait_for(
        state="visible",
        timeout=30000
    )

    prompt_box.click(
        force=True
    )

    prompt_box.fill(
        prompt
    )

    print(
        "Filled prompt"
    )

    time.sleep(2)

    raise_if_too_many_requests(
        page,
        "after filling prompt"
    )


def wait_for_upload_ready(page):
    """
    Đợi file ảnh input upload hoàn tất trước khi bấm Send.

    Dùng chính trạng thái của nút Send:
    - nút phải visible
    - nút phải enabled
    - không có aria-disabled=true
    - trạng thái phải ổn định liên tục vài giây

    Không thay đổi selector Send hiện tại.
    """

    print(
        "Waiting input image upload complete..."
    )

    send_button = page.locator(
        'button[data-testid="send-button"]'
    )

    send_button.wait_for(
        state="visible",
        timeout=MAX_UPLOAD_WAIT * 1000
    )

    start_time = time.time()
    ready_since = None

    while True:
        handle_human_verification_checkbox(
            page
        )

        raise_if_too_many_requests(
            page,
            "while waiting for input upload"
        )

        try:
            is_enabled = (
                send_button.is_enabled()
            )

            aria_disabled = (
                send_button.get_attribute(
                    "aria-disabled"
                )
            )

            disabled_attribute = (
                send_button.get_attribute(
                    "disabled"
                )
            )

            is_ready = (
                is_enabled
                and aria_disabled != "true"
                and disabled_attribute is None
            )

        except Exception:
            is_ready = False

        if is_ready:
            if ready_since is None:
                ready_since = time.time()

                print(
                    "Send button enabled. "
                    "Checking upload stability..."
                )

            ready_duration = (
                time.time()
                - ready_since
            )

            if (
                ready_duration
                >= UPLOAD_READY_STABLE_SECONDS
            ):
                print(
                    "Input image upload completed. "
                    "Send button is ready."
                )

                return

        else:
            ready_since = None

            print(
                "Input image is still uploading..."
            )

        elapsed = (
            time.time()
            - start_time
        )

        if elapsed > MAX_UPLOAD_WAIT:
            raise TimeoutError(
                "Timeout waiting for input image "
                f"upload > {MAX_UPLOAD_WAIT} seconds"
            )

        time.sleep(2)

def wait_for_generated_image(
    page,
    before_count,
    before_assistant_count
):
    print(
        "Waiting generated image..."
    )

    start_render_time = time.time()

    while True:
        handle_human_verification_checkbox(
            page
        )

        raise_if_too_many_requests(
            page,
            "while waiting for generated image"
        )

        raise_if_image_generation_limit(
            page,
            before_assistant_count,
            "while waiting for generated image"
        )

        raise_if_content_policy_violation(
            page,
            before_assistant_count,
            "while waiting for generated image"
        )

        current_count = page.locator(
            'img[alt^="Generated image"]'
        ).count()

        print(
            "Generated image count:",
            current_count
        )

        if current_count > before_count:
            return

        elapsed = (
            time.time()
            - start_render_time
        )

        if elapsed > MAX_RENDER_TIME:
            raise TimeoutError(
                f"Render timeout > "
                f"{MAX_RENDER_TIME} seconds"
            )

        time.sleep(RENDER_POLL_INTERVAL_SECONDS)


def normalize_downloaded_output_to_png(
    downloaded_path
):
    """
    Bảo đảm output có nội dung PNG thật.

    download.save_as() chỉ đổi tên file, không chuyển đổi
    định dạng. Vì vậy một file WEBP/JPEG có thể bị lưu với
    đuôi .png và gây lỗi khi dùng làm input cho frame sau.

    Hàm này:
    - đọc định dạng thật bằng Pillow;
    - sửa chiều EXIF;
    - lấy frame đầu nếu ảnh động;
    - chuyển về RGB/RGBA;
    - lưu lại atomically thành PNG thật;
    - kiểm tra lại định dạng cuối.
    """

    if not os.path.isfile(downloaded_path):
        raise FileNotFoundError(
            "Không tìm thấy ảnh vừa tải: "
            f"{downloaded_path}"
        )

    temporary_path = (
        downloaded_path
        + ".real_png.temporary"
    )

    detected_format = None

    try:
        with Image.open(
            downloaded_path
        ) as image:
            detected_format = (
                image.format or "UNKNOWN"
            )

            if getattr(
                image,
                "is_animated",
                False
            ):
                image.seek(0)

            image = ImageOps.exif_transpose(
                image
            )

            if image_has_transparency(
                image
            ):
                normalized_image = image.convert(
                    "RGBA"
                )
            else:
                normalized_image = image.convert(
                    "RGB"
                )

            normalized_image.save(
                temporary_path,
                format="PNG",
                optimize=True
            )

            normalized_image.close()

        os.replace(
            temporary_path,
            downloaded_path
        )

        with Image.open(
            downloaded_path
        ) as verified_image:
            if verified_image.format != "PNG":
                raise ValueError(
                    "Output sau chuẩn hóa không phải PNG."
                )

            width, height = (
                verified_image.size
            )

        print(
            "Normalized downloaded image:"
        )
        print(
            "  Detected source format:",
            detected_format
        )
        print(
            "  Final format: PNG"
        )
        print(
            "  Final size:",
            f"{width}x{height}"
        )

    except Exception:
        if os.path.exists(
            temporary_path
        ):
            try:
                os.remove(
                    temporary_path
                )
            except OSError:
                pass

        raise


def save_latest_generated_image(
    page,
    output_path
):
    """
    Mở ảnh generated mới nhất và tải bằng nút Save.

    Hàm chỉ return sau khi download.save_as() hoàn tất.
    Vì vậy main chỉ được restart browser sau khi file đã
    được ghi xong hoàn toàn.
    """

    raise_if_too_many_requests(
        page,
        "before saving generated image"
    )

    if page is None or page.is_closed():
        raise RuntimeError(
            "ChatGPT page is already closed before download."
        )

    generated_image = page.locator(
        'img[alt^="Generated image"]'
    ).last

    generated_image.wait_for(
        state="visible",
        timeout=60000
    )

    generated_image.scroll_into_view_if_needed()

    time.sleep(2)

    generated_image.click(
        force=True
    )

    print(
        "Clicked generated image"
    )

    # Chờ fullscreen/modal mở ổn định.
    time.sleep(3)

    if page.is_closed():
        raise RuntimeError(
            "ChatGPT page closed after opening generated image."
        )

    os.makedirs(
        os.path.dirname(output_path),
        exist_ok=True
    )

    # HTML hiện tại:
    # <button aria-label="Save" ...>
    save_button = page.locator(
        'button[aria-label="Save"]'
    ).last

    save_button.wait_for(
        state="visible",
        timeout=60000
    )

    enable_start = time.time()

    while not save_button.is_enabled():
        if (
            time.time() - enable_start
            > 30
        ):
            raise TimeoutError(
                "Save button remained disabled."
            )

        time.sleep(0.5)

    print(
        "Save button ready."
    )

    if page.is_closed():
        raise RuntimeError(
            "ChatGPT page closed before clicking Save."
        )

    # expect_download phải bao đúng thao tác click nút Save.
    print(
        "About to click Save and wait for download event..."
    )

    with page.expect_download(
        timeout=180000
    ) as download_info:
        save_button.click(
            force=True
        )

    print(
        "Clicked Save."
    )

    download = download_info.value

    # Giữ context sống thêm một nhịp sau khi event download xuất hiện.
    time.sleep(2)

    if page.is_closed():
        raise RuntimeError(
            "ChatGPT page/context closed before download.save_as()."
        )

    # save_as() phải hoàn tất TRƯỚC khi browser được restart.
    download.save_as(
        output_path
    )

    print(
        "Download.save_as completed."
    )

    if not os.path.isfile(output_path):
        raise FileNotFoundError(
            "Download completed but output file "
            f"was not found: {output_path}"
        )

    if os.path.getsize(output_path) <= 0:
        raise ValueError(
            "Downloaded image file is empty: "
            f"{output_path}"
        )

    # Bắt buộc output phải là PNG thật.
    normalize_downloaded_output_to_png(
        output_path
    )

    print(
        "Saved image:",
        output_path
    )

    # Chỉ đóng fullscreen sau khi file đã save xong.
    if not page.is_closed():
        close_button = page.locator(
            'button[aria-label="Close fullscreen view"]'
        ).first

        try:
            if (
                close_button.count() > 0
                and close_button.is_visible()
            ):
                close_button.click(
                    force=True
                )

                print(
                    "Closed fullscreen view"
                )
        except Exception as close_error:
            print(
                "Could not close fullscreen view:",
                close_error
            )

    time.sleep(2)


def safe_screenshot(
    page,
    job_id
):
    if page is None:
        return

    try:
        if page.is_closed():
            return

        screenshot_path = os.path.join(
            DEBUG_DIR,
            (
                "image_worker_"
                f"{sanitize_filename(job_id)}.png"
            )
        )

        page.screenshot(
            path=screenshot_path,
            full_page=True
        )

        print(
            "Debug screenshot:",
            screenshot_path
        )

    except Exception as screenshot_error:
        print(
            "Could not save debug screenshot:",
            screenshot_error
        )


def close_browser(browser):
    """
    Đóng persistent browser context hiện tại.

    launch_persistent_context() trả về BrowserContext,
    nên browser.close() sẽ đóng toàn bộ cửa sổ Chrome
    thuộc session đó và giải phóng profile.
    """

    if browser is None:
        return True

    try:
        print(
            "Closing current Chrome browser..."
        )

        browser.close()

        print(
            "Current Chrome browser closed."
        )

        return True

    except Exception as close_error:
        print(
            "Could not close browser:",
            close_error
        )

        return False


# ============================================================
# MAIN
# ============================================================

def main():
    # Kiểm tra queue trước khi mở Chrome.
    rows = load_queue()

    first_pending_job = get_next_pending_job(
        rows
    )

    if not first_pending_job:
        print("=" * 60)
        print(
            "No runnable pending image jobs left."
        )
        return

    with sync_playwright() as playwright:
        current_product_key = None

        browser = None
        page = None

        consecutive_rate_limits = 0
        successful_images_since_break = 0

        while True:
            rows = load_queue()

            job = get_next_pending_job(
                rows
            )

            if not job:
                print("=" * 60)
                print(
                    "No runnable pending image jobs left."
                )
                break

            job_id = job["job_id"]
            category = job["category"]
            product_id = job["product_id"]
            step = job["step"]

            prompt_file = job["prompt_file"]
            input_paths = job["input_paths"]
            output_path = job["output_path"]

            # Dùng cả category và product_id.
            #
            # Điều này tránh trường hợp các category có
            # product_id giống nhau bị hiểu nhầm là cùng sản phẩm.
            #
            # Ví dụ:
            # lipstick/LP001
            # sandal/SDL001
            # keychain/KC001
            # phone_case/PC001
            # mask/MSK001
            channel_id = (
                job.get("channel_id") or "0"
            ).strip()

            # KHÔNG đưa channel_id vào product_key.
            #
            # Nhiều channel (CH1, CH2, CH3...) có thể cùng
            # chung 1 product_id (VD: KC059). Các channel này
            # vẫn được coi là cùng 1 "sản phẩm" và phải dùng
            # chung 1 session/browser cho tới khi TẤT CẢ job
            # của mọi channel thuộc product_id đó đều done.
            #
            # Chỉ khi product_id (hoặc category) đổi thì mới
            # coi là sang sản phẩm khác và mở session mới.
            product_key = (
                category,
                product_id
            )

            if (
                product_key
                != current_product_key
            ):
                if browser is not None:
                    print(
                        "Closing old browser..."
                    )

                    close_browser(
                        browser
                    )

                    browser = None
                    page = None

                    time.sleep(10)

                print(
                    "Opening new ChatGPT session for",
                    f"{category}/{product_id}"
                )

                try:
                    browser, page = open_chatgpt(
                        playwright
                    )
                except TooManyRequestsError as error:
                    # Bảng "Too many requests" có thể hiện ra
                    # NGAY lúc vừa vào ChatGPT, trước khi kịp
                    # đụng tới bất kỳ job nào. Xử lý y hệt
                    # cách xử lý TooManyRequestsError ở khối
                    # try chính bên dưới: cooldown tăng dần,
                    # đóng browser (nếu có), KHÔNG đánh dấu
                    # job vì job vẫn đang "pending" như cũ,
                    # vòng lặp while True sẽ tự lấy lại job
                    # này (hoặc job khác) sau khi cooldown.
                    error_text = str(error)

                    consecutive_rate_limits += 1

                    cooldown_seconds = (
                        get_rate_limit_cooldown(
                            consecutive_rate_limits
                        )
                    )

                    print("=" * 60)
                    print(
                        "RATE LIMITED NGAY LUC MOI VAO "
                        "CHATGPT (truoc khi cham job)"
                    )
                    print(
                        "Error:",
                        error_text
                    )
                    print(
                        "Consecutive rate limits:",
                        consecutive_rate_limits
                    )
                    print(
                        "Cooldown:",
                        f"{cooldown_seconds} seconds"
                    )
                    print("=" * 60)

                    if browser is not None:
                        print(
                            "Closing browser during "
                            "rate-limit cooldown"
                        )

                        close_browser(
                            browser
                        )

                        browser = None
                        page = None
                        current_product_key = None

                    time.sleep(
                        cooldown_seconds
                    )

                    continue

                current_product_key = (
                    product_key
                )

            try:
                attempts = int(
                    job.get("attempts") or 0
                )
            except ValueError:
                attempts = 0

            prompt = read_text(
                prompt_file
            )

            print("=" * 60)
            print(
                "Running image job:",
                job_id
            )

            print(
                "Category:",
                category
            )

            print(
                "Product:",
                product_id
            )

            print(
                "Channel:",
                channel_id
            )

            print(
                "Step:",
                step
            )

            print(
                "Step order:",
                parse_step_order(job)
            )

            for index, input_path in enumerate(
                input_paths,
                start=1
            ):
                print(
                    f"Input {index}:",
                    input_path
                )

            print(
                "Prompt:",
                prompt_file
            )

            print(
                "Output:",
                output_path
            )

            update_job(
                job_id,
                status="running",
                error=""
            )

            try:
                # Kiểm tra và chuẩn hóa ảnh trước khi thao tác
                # với composer. Nếu bất kỳ input frame/background
                # bị lỗi hoặc quá lớn, worker sẽ báo ngay tại đây
                # thay vì upload file gây đơ trang ChatGPT.
                upload_paths = prepare_job_upload_paths(
                    input_paths
                )

                print(
                    "Upload files prepared:",
                    len(upload_paths)
                )

                for index, upload_path in enumerate(
                    upload_paths,
                    start=1
                ):
                    print(
                        f"Prepared input {index}:",
                        upload_path
                    )

                before_count = page.locator(
                    'img[alt^="Generated image"]'
                ).count()

                assistant_count_before_send = (
                    page.locator(
                        "div[data-message-author-role="
                        "'assistant']"
                    ).count()
                )

                print(
                    "Assistant messages before Send:",
                    assistant_count_before_send
                )

                upload_input_files(
                    page,
                    upload_paths
                )

                fill_prompt(
                    page,
                    prompt
                )

                # Đợi ảnh input upload và load hoàn tất
                # rồi mới được bấm nút Send.
                wait_for_upload_ready(
                    page
                )

                raise_if_too_many_requests(
                    page,
                    "immediately before Send"
                )

                page.locator(
                    'button[data-testid="send-button"]'
                ).click(
                    force=True
                )

                print(
                    "Sent prompt"
                )

                time.sleep(2)

                raise_if_too_many_requests(
                    page,
                    "immediately after Send"
                )

                raise_if_image_generation_limit(
                    page,
                    assistant_count_before_send,
                    "immediately after Send"
                )

                wait_for_generated_image(
                    page,
                    before_count,
                    assistant_count_before_send
                )

                # Chờ ảnh tải và nút Save ổn định.
                time.sleep(12)

                # Chỉ sau khi hàm này return mới được restart browser.
                save_latest_generated_image(
                    page,
                    output_path
                )

                print(
                    "Download fully saved. "
                    "Safe to update job and restart browser."
                )

                update_job(
                    job_id,
                    status="done",
                    attempts=str(
                        attempts + 1
                    ),
                    error=""
                )

                print(
                    "Image job done:",
                    job_id
                )

                consecutive_rate_limits = 0
                successful_images_since_break += 1

                rows_after_update = load_queue()

                product_finished = (
                    is_product_finished(
                        rows_after_update,
                        category,
                        product_id
                    )
                )

                if product_finished:
                    print(
                        "Finished product:",
                        f"{category}/{product_id}"
                    )

                # Sau MỖI ảnh thành công, đóng browser ngay.
                # Áp dụng cho tất cả category.
                if RESTART_AFTER_EACH_IMAGE:
                    print(
                        "Image completed. "
                        "Restarting browser before next image:",
                        job_id
                    )

                    close_browser(
                        browser
                    )

                    # Reset bắt buộc để vòng lặp tiếp theo
                    # luôn mở browser mới, kể cả cùng product.
                    browser = None
                    page = None
                    current_product_key = None

                    # Chờ thêm giữa các ảnh thành công theo
                    # DELAY_AFTER_SUCCESS_SECONDS trước khi
                    # sang job kế tiếp.
                    if DELAY_AFTER_SUCCESS_SECONDS > 0:
                        print(
                            "Waiting",
                            format_wait_duration(
                                DELAY_AFTER_SUCCESS_SECONDS
                            ),
                            "before next image."
                        )

                        time.sleep(
                            DELAY_AFTER_SUCCESS_SECONDS
                        )
                    else:
                        print(
                            "Continuous mode enabled. "
                            "Proceeding to the next image immediately."
                        )

                elif (
                        product_finished
                        and RESTART_AFTER_PRODUCT
                        and browser is not None
                ):
                    # Fallback cũ nếu tắt restart mỗi ảnh.
                    print(
                        "Restart browser for next product"
                    )

                    close_browser(
                        browser
                    )

                    browser = None
                    page = None
                    current_product_key = None

                    if DELAY_AFTER_SUCCESS_SECONDS > 0:
                        print(
                            "Waiting",
                            format_wait_duration(
                                DELAY_AFTER_SUCCESS_SECONDS
                            ),
                            "before next image."
                        )

                        time.sleep(
                            DELAY_AFTER_SUCCESS_SECONDS
                        )
                    else:
                        print(
                            "Continuous mode enabled. "
                            "Proceeding to the next image immediately."
                        )

                else:
                    # Sản phẩm chưa xong và không bật restart
                    # mỗi ảnh: KHÔNG đóng browser, vẫn giữ
                    # nguyên profile/session hiện tại.
                    #
                    # Tuy nhiên vẫn cần reload lại TAB (F5) để
                    # làm sạch DOM composer trước khi upload ảnh
                    # cho job tiếp theo. Nếu không reload, các
                    # phần tử cũ (input[type=file] ẩn, prompt box
                    # cũ...) từ ảnh trước có thể còn sót lại trong
                    # DOM và làm sai locator ở ảnh sau, khiến
                    # #prompt-textarea không "editable" và
                    # fill_prompt() bị timeout.
                    #
                    # Reload chỉ F5 lại trang, không mở browser
                    # mới, không đổi profile/cookie, nên vẫn coi
                    # là cùng 1 session như bạn yêu cầu.
                    print(
                        "Product not finished yet. "
                        "Reloading tab (same session) "
                        "before next image."
                    )

                    reload_success = (
                        reload_chatgpt_after_image(
                            page
                        )
                    )

                    if (
                            not reload_success
                            and browser is not None
                    ):
                        print(
                            "Closing browser because "
                            "page reload failed"
                        )

                        close_browser(
                            browser
                        )

                        browser = None
                        page = None
                        current_product_key = None

                        time.sleep(5)

            except ImageGenerationLimitError as error:
                error_text = str(error)

                wait_seconds = max(
                    1,
                    int(error.wait_seconds)
                )

                successful_images_since_break = 0

                print("=" * 60)
                print(
                    "IMAGE WORKER PLUS LIMIT REACHED"
                )
                print("Job:", job_id)
                print(
                    "Reset description:",
                    error.reset_description
                    or "not parsed"
                )
                print(
                    "Worker will wait:",
                    format_wait_duration(
                        wait_seconds
                    )
                )
                print("=" * 60)

                # Hạn mức Plus không phải lỗi của job.
                # Không tăng attempts, giữ job pending.
                update_job(
                    job_id,
                    status="pending",
                    attempts=str(attempts),
                    error=(
                        error_text
                        + " | reset="
                        + (
                            error.reset_description
                            or "unknown"
                        )
                        + " | wait="
                        + str(wait_seconds)
                        + "s"
                    )
                )

                safe_screenshot(
                    page,
                    job_id
                )

                if browser is not None:
                    print(
                        "Closing browser during Plus "
                        "image-limit wait"
                    )

                    close_browser(browser)
                    browser = None
                    page = None
                    current_product_key = None

                print(
                    "No image-generation request will be "
                    "sent until the announced reset time."
                )

                time.sleep(wait_seconds)

            except TooManyRequestsError as error:
                error_text = str(error)

                consecutive_rate_limits += 1
                successful_images_since_break = 0

                cooldown_seconds = (
                    get_rate_limit_cooldown(
                        consecutive_rate_limits
                    )
                )

                print("=" * 60)
                print(
                    "IMAGE WORKER RATE LIMITED"
                )
                print(
                    "Job:",
                    job_id
                )
                print(
                    "Consecutive rate limits:",
                    consecutive_rate_limits
                )
                print(
                    "Cooldown:",
                    f"{cooldown_seconds} seconds"
                )
                print("=" * 60)

                # Rate limit không phải lỗi nội dung của job.
                # Giữ nguyên attempts và đưa job về pending.
                update_job(
                    job_id,
                    status="pending",
                    attempts=str(attempts),
                    error=(
                        error_text
                        + " | cooldown="
                        + str(cooldown_seconds)
                        + "s"
                    )
                )

                safe_screenshot(
                    page,
                    job_id
                )

                if browser is not None:
                    print(
                        "Closing browser during rate-limit cooldown"
                    )

                    close_browser(
                        browser
                    )

                    browser = None
                    page = None
                    current_product_key = None

                print(
                    "No new ChatGPT requests will be sent "
                    "during cooldown."
                )

                time.sleep(
                    cooldown_seconds
                )

            except ContentPolicyViolationError as error:
                error_text = str(error)

                print("=" * 60)
                print(
                    "CONTENT POLICY / GUARDRAILS VIOLATION"
                )
                print("Job:", job_id)
                print("Error:", error_text)
                print(
                    "Marking job as FAILED immediately "
                    "(no retry) and moving to next job."
                )
                print("=" * 60)

                # Lỗi này gắn liền với NỘI DUNG của job (ảnh
                # input/prompt bị coi là giống bên thứ ba),
                # không phải lỗi tạm thời -> đánh failed ngay,
                # không tăng dần theo MAX_ATTEMPTS như lỗi
                # thông thường, không cooldown.
                update_job(
                    job_id,
                    status="failed",
                    attempts=str(MAX_ATTEMPTS),
                    error=error_text
                )

                safe_screenshot(
                    page,
                    job_id
                )

                # Không dùng reload tab (cùng conversation)
                # nữa - đóng hẳn browser và mở phiên MỚI
                # trước khi làm job tiếp theo, giống hệt cách
                # các job khác chuyển sang product_key mới
                # (xem đoạn "Closing old browser..." /
                # open_chatgpt() ở phần đầu vòng lặp). Tránh
                # việc dùng tiếp cùng 1 conversation sau khi
                # đã bị từ chối vì guardrails.
                if browser is not None:
                    print(
                        "Dong browser va mo phien MOI "
                        "(khong dung tiep conversation cu) "
                        "sau khi bi tu choi vi guardrails..."
                    )

                    close_browser(
                        browser
                    )

                    browser = None
                    page = None
                    current_product_key = None

                    time.sleep(10)

            except Exception as error:
                error_text = str(error)

                print(
                    "Image job failed:",
                    job_id
                )

                print(
                    "Error:",
                    error_text
                )

                attempts += 1

                if attempts >= MAX_ATTEMPTS:
                    status = "failed"
                else:
                    status = "pending"

                update_job(
                    job_id,
                    status=status,
                    attempts=str(attempts),
                    error=error_text
                )

                safe_screenshot(
                    page,
                    job_id
                )

                if browser is not None:
                    print(
                        "Closing browser after failure"
                    )

                    close_browser(
                        browser
                    )

                    browser = None
                    page = None
                    current_product_key = None

                time.sleep(5)

        print("=" * 60)
        print(
            "Image batch finished."
        )

        if browser is not None:
            close_browser(
                browser
            )


if __name__ == "__main__":
    main()