import csv
import json
import os
import re
import time
from datetime import datetime, timedelta

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

VIVIBE_HOME_URL = "https://www.vivibe.app"

VIVIBE_PROFILE_DIRS = [
    "C:/vivibe_auto_profile_01",
    "C:/vivibe_auto_profile_02",
    "C:/vivibe_auto_profile_03",
    "C:/vivibe_auto_profile_04",
    "C:/vivibe_auto_profile_05",
    "C:/vivibe_auto_profile_06",
    "C:/vivibe_auto_profile_07",
    "C:/vivibe_auto_profile_08",
    "C:/vivibe_auto_profile_09",
    "C:/vivibe_auto_profile_10",
]

PROFILE_STATE_FILE = os.path.join(
    BASE_DIR,
    "queue",
    "vivibe_profile_states.txt"
)

PROFILE_STATE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


QUEUE_FILE = os.path.join(
    BASE_DIR,
    "queue",
    "voice_queue.csv"
)

MAX_WAIT_AUDIO_SECONDS = 180

RATE_LIMIT_CHECK_SECONDS = 8
RATE_LIMIT_POLL_SECONDS = 0.25
RATE_LIMIT_TEXT = (
    "Bạn đã sử dụng hết 8 lượt xuất audio trong giờ qua"
)

ENABLED_CATEGORIES = [
    "snack",
    "keychain",
    "phone_case",
]


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
# VIVIBE NEW UI SELECTORS
# ============================================================

WORKSPACE_BUTTON_SELECTOR = (
    "button[type='button']"
    "[data-variant='primary']"
    "[data-size='lg']"
    "[aria-label='Vào workspace']"
)

GOOGLE_CONTINUE_BUTTON_SELECTOR = (
    "button[type='button']"
    "[data-variant='primary']"
    "[data-size='lg']"
)

TEXTAREA_SELECTOR = (
    "textarea[placeholder="
    "'Nhập nội dung cần chuyển thành giọng nói…']"
)

CREATE_AUDIO_BUTTON_SELECTOR = (
    "button.cta-btn"
)

DOWNLOAD_BUTTON_SELECTOR = (
    "button[type='button']"
    "[data-variant='ghost']"
    "[data-size='sm']"
    "[aria-label='Tải WAV']"
)

PROCESSING_TEXTS = [
    "Đang tạo…",
    "Đang tạo...",
]

DOWNLOAD_READY_STABLE_SECONDS = 3


# ============================================================
# PATH HANDLING
# ============================================================

def abs_path(path):
    """
    Hỗ trợ cả đường dẫn tương đối và tuyệt đối.

    Queue mới có cấu trúc:

    products/lipstick/LP001/output/scripts/LP001.txt
    products/lipstick/LP001/output/audio/LP001.mp3

    products/sandal/SDL001/output/scripts/SDL001.txt
    products/sandal/SDL001/output/audio/SDL001.mp3

    products/keychain/KC001/output/scripts/KC001.txt
    products/keychain/KC001/output/audio/KC001.mp3

    products/phone_case/PC001/output/scripts/PC001.txt
    products/phone_case/PC001/output/audio/PC001.mp3

    products/mask/MSK001/output/scripts/MSK001.txt
    products/mask/MSK001/output/audio/MSK001.mp3
    """

    if not path:
        return ""

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
# QUEUE HANDLING
# ============================================================

def load_queue():
    with open(
        QUEUE_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        return list(
            csv.DictReader(f)
        )


def save_queue(rows):
    with open(
        QUEUE_FILE,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=FIELDNAMES,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(rows)


def update_job(
    rows,
    index,
    status,
    error=""
):
    rows[index]["status"] = status
    rows[index]["error"] = error

    save_queue(
        rows
    )


def get_next_job(rows):
    for index, row in enumerate(rows):
        if (
            row.get("status", "")
            .strip()
            .lower()
            == "pending"
        ):
            return index, row

    return None, None


# ============================================================
# SCRIPT AND OUTPUT
# ============================================================

def read_script(script_path):
    path = abs_path(
        script_path
    )

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Script file not found: {path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8-sig"
    ) as f:
        return f.read().strip()


def ensure_output_dir(
    output_audio_path
):
    path = abs_path(
        output_audio_path
    )

    if not path:
        raise ValueError(
            "Missing output_audio_path"
        )

    os.makedirs(
        os.path.dirname(path),
        exist_ok=True
    )

    return path


# ============================================================
# OPTIONAL LOGIN FLOW
# ============================================================

def find_visible_button(page, text, timeout_ms=5000):
    """
    Tìm button visible theo text trong khoảng timeout ngắn.
    Không thấy thì trả về None.
    """
    deadline = time.time() + (timeout_ms / 1000)

    while time.time() < deadline:
        candidate = (
            page.locator("button")
            .filter(has_text=text)
            .first
        )

        try:
            if (
                candidate.count() > 0
                and candidate.is_visible()
            ):
                return candidate
        except Exception:
            pass

        time.sleep(0.25)

    return None


def find_visible_button(page, text, timeout_ms=5000):
    """
    Tìm button visible theo text trong khoảng timeout ngắn.
    Không thấy thì trả về None.
    """
    deadline = time.time() + (timeout_ms / 1000)

    while time.time() < deadline:
        candidate = (
            page.locator("button")
            .filter(has_text=text)
            .first
        )

        try:
            if (
                candidate.count() > 0
                and candidate.is_visible()
            ):
                return candidate
        except Exception:
            pass

        time.sleep(0.25)

    return None


def handle_optional_login(page):
    """
    Kiểm tra độc lập 3 nút theo thứ tự:
    1. Đăng nhập
    2. Tiếp tục với Google
    3. Workspace

    Mỗi nút:
    - có thì bấm
    - không có thì skip
    - KHÔNG tự page.goto() sang project URL chung

    Sau khi Workspace mở đúng editor, giữ nguyên page hiện tại.
    """

    steps = [
        ("Đăng nhập", 2),
        ("Tiếp tục với Google", 8),
        ("Workspace", 5),
    ]

    for button_text, wait_after in steps:
        # Nếu đã vào editor thì không bấm thêm gì nữa.
        if textarea_is_visible(page):
            print(
                "Voice textarea already visible. "
                "Stop optional login checks."
            )
            break

        button = find_visible_button(
            page,
            button_text,
            timeout_ms=5000
        )

        if button is None:
            print(
                f"{button_text} button not found. Skip."
            )
            continue

        print(
            f"Detected {button_text} button."
        )

        button.click(
            force=True
        )

        print(
            f"Clicked {button_text}."
        )

        time.sleep(
            wait_after
        )

        try:
            page.wait_for_load_state(
                "domcontentloaded",
                timeout=30000
            )
        except Exception:
            pass

    print(
        "Optional login flow completed."
    )

    return textarea_is_visible(page)


class VivibeHourlyLimitError(Exception):
    def __init__(self, message, wait_minutes=None):
        super().__init__(message)
        self.wait_minutes = wait_minutes


def extract_wait_minutes(text):
    match = re.search(
        r"đợi\s+(\d+)\s+phút",
        str(text),
        re.IGNORECASE
    )

    if not match:
        return None

    try:
        return int(match.group(1))
    except ValueError:
        return None


def get_hourly_limit_toast_text(page):
    """
    Tìm toast giới hạn 8 audio / giờ đang visible.
    Không phụ thuộc data-toast-id vì ID có thể thay đổi.
    """
    candidates = [
        page.locator("[role='alert']").filter(
            has_text=RATE_LIMIT_TEXT
        ),
        page.get_by_text(
            RATE_LIMIT_TEXT,
            exact=False
        ),
    ]

    for locator in candidates:
        try:
            count = locator.count()
        except Exception:
            continue

        for index in range(count):
            item = locator.nth(index)

            try:
                if not item.is_visible():
                    continue

                text = (item.inner_text() or "").strip()

                if RATE_LIMIT_TEXT in text:
                    return text

            except Exception:
                continue

    return None


def check_hourly_limit_after_create(page):
    """
    Toast chỉ hiện vài giây sau khi bấm Tạo âm thanh,
    nên poll nhanh ngay sau click.
    """
    print("Checking Vivibe hourly limit toast...")

    start_time = time.time()

    while (
        time.time() - start_time
        < RATE_LIMIT_CHECK_SECONDS
    ):
        toast_text = get_hourly_limit_toast_text(page)

        if toast_text:
            wait_minutes = extract_wait_minutes(
                toast_text
            )

            print("Detected Vivibe hourly audio limit:")
            print(
                toast_text.replace(
                    "\n",
                    " | "
                )
            )

            raise VivibeHourlyLimitError(
                toast_text,
                wait_minutes=wait_minutes
            )

        time.sleep(
            RATE_LIMIT_POLL_SECONDS
        )

    print("No hourly limit toast detected.")


def is_processing_visible(page):
    """
    True khi Vivibe vẫn đang hiển thị Đang tạo…
    """

    for processing_text in PROCESSING_TEXTS:
        locator = page.get_by_text(
            processing_text,
            exact=True
        )

        for index in range(
            locator.count()
        ):
            try:
                if locator.nth(index).is_visible():
                    return True
            except Exception:
                continue

    return False


def get_download_buttons(page):
    return page.locator(
        DOWNLOAD_BUTTON_SELECTOR
    )


def get_create_audio_button(page):
    """
    Vivibe UI mới:
    button.cta-btn + text Tạo âm thanh
    """

    button = (
        page.locator(
            CREATE_AUDIO_BUTTON_SELECTOR
        )
        .filter(
            has_text="Tạo âm thanh"
        )
        .first
    )

    if button.count() == 0:
        button = (
            page.locator("button")
            .filter(
                has_text="Tạo âm thanh"
            )
            .first
        )

    return button


def mark_old_download_buttons(page):
    """
    Đánh dấu các nút Tải WAV đã tồn tại trước khi tạo voice mới.
    """

    buttons = get_download_buttons(
        page
    )

    old_count = buttons.count()

    if old_count > 0:
        buttons.evaluate_all(
            """
            (elements) => {
                elements.forEach((element) => {
                    element.setAttribute(
                        'data-voice-worker-old-download',
                        'true'
                    );
                });
            }
            """
        )

    print(
        "Old Tải WAV buttons:",
        old_count
    )

    return old_count


def get_visible_enabled_download_buttons(page):
    """
    Trả về các nút Tải WAV đang visible và enabled
    theo đúng thứ tự hiển thị trên Vivibe.

    Vivibe hiện xếp voice mới nhất ở trên cùng,
    nên phần tử index 0 là voice mới nhất.
    """

    buttons = get_download_buttons(
        page
    )

    available_buttons = []

    for index in range(
        buttons.count()
    ):
        button = buttons.nth(
            index
        )

        try:
            is_visible = (
                button.is_visible()
            )

            is_enabled = (
                button.is_enabled()
            )

            aria_disabled = (
                button.get_attribute(
                    "aria-disabled"
                )
            )

            disabled_attr = (
                button.get_attribute(
                    "disabled"
                )
            )

            if (
                is_visible
                and is_enabled
                and aria_disabled != "true"
                and disabled_attr is None
            ):
                available_buttons.append(
                    button
                )

        except Exception:
            continue

    return available_buttons


def normalize_history_match_text(value):
    """
    Chuẩn hóa text để đối chiếu tiêu đề voice trong lịch sử.

    Bỏ khoảng trắng và dấu câu nhưng vẫn giữ chữ tiếng Việt.
    """

    return "".join(
        character.lower()
        for character in str(value)
        if character.isalnum()
    )


def get_download_button_row_text(
    download_button
):
    """
    Lấy nội dung của đúng hàng lịch sử chứa nút Tải WAV.

    Đi từ nút tải lên các ancestor và dừng trước khi gặp
    container chứa nhiều hơn một nút Tải WAV.
    """

    return download_button.evaluate(
        """
        (element) => {
            let node = element;
            let candidateText = "";

            for (let depth = 0; node && depth < 12; depth++) {
                const downloadCount = (
                    node.querySelectorAll(
                        'button[aria-label="Tải WAV"]'
                    ).length
                );

                const text = (
                    node.innerText || ""
                ).trim();

                if (
                    downloadCount === 1
                    && text.length > candidateText.length
                ) {
                    candidateText = text;
                }

                if (downloadCount > 1) {
                    break;
                }

                node = node.parentElement;
            }

            return candidateText;
        }
        """
    )


def history_row_matches_script(
    download_button,
    script_text
):
    """
    Kiểm tra hàng voice mới nhất có bắt đầu bằng đúng script
    của job hiện tại hay không.

    Vivibe thường rút gọn tiêu đề bằng dấu ba chấm,
    nên chỉ đối chiếu phần đầu của script.
    """

    row_text = get_download_button_row_text(
        download_button
    )

    normalized_script = (
        normalize_history_match_text(
            script_text
        )
    )

    normalized_row = (
        normalize_history_match_text(
            row_text
        )
    )

    # 16 ký tự đã đủ phân biệt các script liên tiếp,
    # nhưng vẫn ngắn hơn phần tiêu đề Vivibe hiển thị.
    match_prefix = normalized_script[:16]

    print(
        "Newest history row:",
        row_text.replace(
            "\n",
            " | "
        )[:200]
    )

    if not match_prefix:
        return False

    return match_prefix in normalized_row


def wait_for_new_download_button(
    page,
    old_download_count,
    script_text
):
    """
    Chờ voice mới hoàn tất và trả về đúng nút Tải WAV mới nhất.

    Logic giữ nguyên tinh thần file cũ:
    - ưu tiên theo dõi trạng thái Đang tạo…
    - chọn nút Tải WAV visible + enabled ĐẦU TIÊN
    - xác nhận hàng đầu tiên khớp script hiện tại
    - chờ ổn định vài giây trước khi tải

    Khác biệt cần thiết cho pipeline mới:
    Sau khi bấm Tạo âm thanh, worker có bước kiểm tra toast
    hourly-limit trong vài giây. Trong khoảng đó, trạng thái
    "Đang tạo…" có thể đã xuất hiện rồi biến mất.

    Vì vậy KHÔNG bắt buộc processing_seen phải True nếu:
    1. Hàng đầu tiên khớp script hiện tại; và
    2. Có dấu hiệu voice mới đã xuất hiện:
       - số nút Tải WAV tăng so với trước, hoặc
       - hàng đầu tiên khớp script hiện tại sau thời gian chờ.
    """

    print(
        "Waiting for newly generated audio..."
    )

    start_time = time.time()

    processing_seen = False
    processing_finished = False
    ready_since = None

    while True:
        elapsed = (
            time.time()
            - start_time
        )

        if elapsed > MAX_WAIT_AUDIO_SECONDS:
            raise TimeoutError(
                "Timeout waiting for the newest "
                "Vivibe audio row"
            )

        processing_visible = (
            is_processing_visible(
                page
            )
        )

        if processing_visible:
            if not processing_seen:
                print(
                    "Detected Đang tạo…"
                )

            processing_seen = True
            processing_finished = False
            ready_since = None

            print(
                "Vivibe is still showing Đang tạo…"
            )

            time.sleep(2)
            continue

        if processing_seen:
            if not processing_finished:
                print(
                    "Đang tạo… disappeared."
                )

            processing_finished = True

        download_buttons = (
            get_download_buttons(
                page
            )
        )

        current_count = (
            download_buttons.count()
        )

        print(
            "Tải WAV buttons:",
            current_count,
            "| Old count:",
            old_download_count,
            "| Processing seen:",
            processing_seen
        )

        available_buttons = (
            get_visible_enabled_download_buttons(
                page
            )
        )

        if not available_buttons:
            ready_since = None

            print(
                "No visible enabled Tải WAV button yet."
            )

            time.sleep(2)
            continue

        newest_download_button = (
            available_buttons[0]
        )

        matches_current_script = (
            history_row_matches_script(
                newest_download_button,
                script_text
            )
        )

        if not matches_current_script:
            ready_since = None

            print(
                "Top history row does not match "
                "the current script yet. Waiting..."
            )

            time.sleep(2)
            continue

        # ----------------------------------------------------
        # CASE 1: đã nhìn thấy Đang tạo…
        # ----------------------------------------------------
        if processing_seen:
            if not processing_finished:
                ready_since = None
                time.sleep(1)
                continue

        # ----------------------------------------------------
        # CASE 2: không nhìn thấy Đang tạo…
        # ----------------------------------------------------
        else:
            # Rate-limit check có thể đã làm worker bỏ lỡ
            # trạng thái Đang tạo… rất ngắn.
            #
            # Nếu số nút tăng, đây là bằng chứng mạnh rằng
            # voice mới đã được thêm.
            #
            # Nếu count không tăng (Vivibe có thể recycle DOM),
            # vẫn cho phép hàng đầu tiên khớp script hiện tại
            # đi qua bước stability check.
            if current_count > old_download_count:
                print(
                    "New Tải WAV button count detected "
                    "without seeing Đang tạo…"
                )
            else:
                print(
                    "Processing state was missed, but "
                    "the newest history row matches "
                    "the current script."
                )

        if ready_since is None:
            ready_since = time.time()

            print(
                "Newest matching Tải WAV button detected. "
                "Checking stability..."
            )

            time.sleep(1)
            continue

        if (
            time.time()
            - ready_since
            < DOWNLOAD_READY_STABLE_SECONDS
        ):
            time.sleep(1)
            continue

        # Kiểm tra cuối trước khi download.
        if is_processing_visible(
            page
        ):
            processing_seen = True
            processing_finished = False
            ready_since = None

            time.sleep(1)
            continue

        available_buttons = (
            get_visible_enabled_download_buttons(
                page
            )
        )

        if not available_buttons:
            ready_since = None
            time.sleep(1)
            continue

        newest_download_button = (
            available_buttons[0]
        )

        if not history_row_matches_script(
            newest_download_button,
            script_text
        ):
            ready_since = None
            time.sleep(1)
            continue

        print(
            "Using the FIRST visible enabled "
            "Tải WAV button for the newest voice."
        )

        return newest_download_button


# ============================================================
# RUN ONE VOICE JOB
# ============================================================

def run_voice_job(
    page,
    job,
    profile_states,
    profile_index
):
    category = (
        job.get("category")
        or ""
    ).strip()

    product_id = (
        job["product_id"]
    )

    if not category:
        raise ValueError(
            f"Missing category for product: "
            f"{product_id}"
        )

    if category not in ENABLED_CATEGORIES:
        raise ValueError(
            f"Unsupported voice category: "
            f"{category}"
        )

    script_text = read_script(
        job["script_path"]
    )

    if not script_text:
        raise ValueError(
            f"Script is empty: "
            f"{job['script_path']}"
        )

    output_audio_abs = ensure_output_dir(
        job["output_audio_path"]
    )

    if os.path.exists(
        output_audio_abs
    ):
        print(
            "Audio already exists, skip:",
            output_audio_abs
        )

        return

    print("=" * 60)
    print(
        f"VOICE JOB: "
        f"{category}/{product_id}"
    )
    print("=" * 60)

    saved_project_url = (
        get_profile_project_url(
            profile_states,
            profile_index
        )
    )

    # Ưu tiên URL project riêng đã lưu cho profile này.
    if saved_project_url:
        print(
            "Opening saved project URL:",
            saved_project_url
        )

        page.goto(
            saved_project_url,
            wait_until="domcontentloaded",
            timeout=120000
        )

        time.sleep(5)

        if textarea_is_visible(page):
            print(
                "Saved project URL opened successfully."
            )
        else:
            print(
                "Saved project URL did not open voice editor. "
                "Fallback to Vivibe homepage."
            )

            page.goto(
                VIVIBE_HOME_URL,
                wait_until="domcontentloaded",
                timeout=120000
            )

            time.sleep(5)

            handle_optional_login(
                page
            )

    else:
        # Profile chưa có project URL:
        # vào homepage rồi kiểm tra tuần tự 3 nút.
        print(
            "No saved project URL for this profile. "
            "Opening Vivibe homepage."
        )

        page.goto(
            VIVIBE_HOME_URL,
            wait_until="domcontentloaded",
            timeout=120000
        )

        time.sleep(5)

        handle_optional_login(
            page
        )

    # Nếu đã vào được editor, lưu URL RIÊNG của profile hiện tại.
    if textarea_is_visible(page):
        profile_states = load_profile_states()

        save_profile_project_url(
            profile_states,
            profile_index,
            page.url
        )

    else:
        # Thử lại flow 3 nút một lần trên page hiện tại,
        # nhưng vẫn không điều hướng sang project URL chung.
        handle_optional_login(
            page
        )

        if textarea_is_visible(page):
            profile_states = load_profile_states()

            save_profile_project_url(
                profile_states,
                profile_index,
                page.url
            )

    textarea = page.locator(
        TEXTAREA_SELECTOR
    ).first

    textarea.wait_for(
        state="visible",
        timeout=60000
    )

    textarea.click(
        force=True
    )

    textarea.fill("")
    textarea.fill(
        script_text
    )

    print(
        "Script filled."
    )

    time.sleep(1)

    # Ghi nhận voice cũ trước khi tạo voice mới.
    old_download_count = (
        mark_old_download_buttons(
            page
        )
    )

    create_audio_button = (
        get_create_audio_button(
            page
        )
    )

    create_audio_button.wait_for(
        state="visible",
        timeout=30000
    )

    enable_start = time.time()

    while not create_audio_button.is_enabled():
        if (
            time.time() - enable_start
            > 30
        ):
            raise TimeoutError(
                "Tạo âm thanh button remained disabled."
            )

        time.sleep(1)

    create_audio_button.click(
        force=True
    )

    print(
        "Clicked Tạo âm thanh."
    )

    # Bắt toast quota ngay lập tức trước khi nó biến mất.
    check_hourly_limit_after_create(
        page
    )

    download_button = (
        wait_for_new_download_button(
            page,
            old_download_count,
            script_text
        )
    )

    # Kiểm tra cuối cùng: tuyệt đối không tải khi còn Đang tạo…
    if is_processing_visible(page):
        raise RuntimeError(
            "Vivibe still shows Đang tạo…; "
            "download cancelled."
        )

    print(
        "New Tải WAV button is ready."
    )

    download_button.scroll_into_view_if_needed()

    time.sleep(1)

    # Kiểm tra lần cuối: tuyệt đối không tải khi
    # Vivibe vẫn còn trạng thái Đang tạo…
    if is_processing_visible(
        page
    ):
        raise RuntimeError(
            "Vivibe still shows Đang tạo…; "
            "download was cancelled."
        )

    with page.expect_download(
        timeout=60000
    ) as download_info:
        download_button.click(
            force=True
        )

    download = download_info.value

    download.save_as(
        output_audio_abs
    )

    if not os.path.isfile(
        output_audio_abs
    ):
        raise FileNotFoundError(
            "Vivibe download completed but output "
            f"was not found: {output_audio_abs}"
        )

    if os.path.getsize(
        output_audio_abs
    ) <= 0:
        raise ValueError(
            f"Downloaded audio is empty: "
            f"{output_audio_abs}"
        )

    print(
        f"Saved new audio: "
        f"{output_audio_abs}"
    )


# ============================================================
# MAIN
# ============================================================

# ============================================================
# PROFILE STATE
# ============================================================

def profile_name_from_index(index):
    return f"profile_{index + 1:02d}"


def default_profile_states():
    states = {}

    for index, profile_dir in enumerate(
        VIVIBE_PROFILE_DIRS
    ):
        states[
            profile_name_from_index(index)
        ] = {
            "status": "available",
            "retry_after": "",
            "profile_dir": profile_dir,
            "project_url": "",
        }

    return states


def save_profile_states(states):
    os.makedirs(
        os.path.dirname(
            PROFILE_STATE_FILE
        ),
        exist_ok=True
    )

    with open(
        PROFILE_STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            states,
            f,
            ensure_ascii=False,
            indent=2
        )


def load_profile_states():
    defaults = default_profile_states()

    if not os.path.exists(
        PROFILE_STATE_FILE
    ):
        save_profile_states(
            defaults
        )
        return defaults

    try:
        with open(
            PROFILE_STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            states = json.load(f)

        if not isinstance(states, dict):
            raise ValueError(
                "Invalid profile state format"
            )

    except Exception as error:
        print(
            "Profile state file unreadable. Resetting:",
            error
        )
        save_profile_states(
            defaults
        )
        return defaults

    changed = False

    for profile_name, default_state in defaults.items():
        if profile_name not in states:
            states[
                profile_name
            ] = default_state
            changed = True
        else:
            states[
                profile_name
            ]["profile_dir"] = (
                default_state[
                    "profile_dir"
                ]
            )

            if "project_url" not in states[
                profile_name
            ]:
                states[
                    profile_name
                ]["project_url"] = ""
                changed = True

    if changed:
        save_profile_states(
            states
        )

    return states


def parse_retry_after(value):
    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            PROFILE_STATE_TIME_FORMAT
        )
    except Exception:
        return None


def refresh_expired_profile_states(states):
    now = datetime.now()
    changed = False

    for profile_name, state in states.items():
        status = (
            state.get("status")
            or "available"
        ).strip().lower()

        if status != "limited":
            continue

        retry_after = parse_retry_after(
            state.get("retry_after")
        )

        if (
            retry_after is not None
            and retry_after <= now
        ):
            state["status"] = "available"
            state["retry_after"] = ""
            changed = True

            print(
                f"{profile_name} cooldown expired "
                "-> available"
            )

    if changed:
        save_profile_states(
            states
        )

    return states


def choose_available_profile(
    states,
    preferred_start_index=0
):
    states = refresh_expired_profile_states(
        states
    )

    total = len(
        VIVIBE_PROFILE_DIRS
    )

    for offset in range(total):
        index = (
            preferred_start_index
            + offset
        ) % total

        profile_name = (
            profile_name_from_index(
                index
            )
        )

        state = states.get(
            profile_name,
            {}
        )

        status = (
            state.get("status")
            or "available"
        ).strip().lower()

        if status == "available":
            return (
                index,
                profile_name,
                VIVIBE_PROFILE_DIRS[
                    index
                ],
            )

    return None, None, None


def mark_profile_limited(
    states,
    profile_index,
    wait_minutes
):
    profile_name = profile_name_from_index(
        profile_index
    )

    cooldown_minutes = (
        wait_minutes
        if wait_minutes is not None
        else 60
    )

    retry_after = (
        datetime.now()
        + timedelta(
            minutes=cooldown_minutes
        )
    )

    state = states.setdefault(
        profile_name,
        {}
    )

    state["status"] = "limited"
    state["retry_after"] = (
        retry_after.strftime(
            PROFILE_STATE_TIME_FORMAT
        )
    )
    state["profile_dir"] = (
        VIVIBE_PROFILE_DIRS[
            profile_index
        ]
    )

    save_profile_states(
        states
    )

    print(
        f"{profile_name} -> LIMITED until "
        f"{state['retry_after']}"
    )


def mark_profile_available(
    states,
    profile_index
):
    profile_name = profile_name_from_index(
        profile_index
    )

    state = states.setdefault(
        profile_name,
        {}
    )

    state["status"] = "available"
    state["retry_after"] = ""
    state["profile_dir"] = (
        VIVIBE_PROFILE_DIRS[
            profile_index
        ]
    )

    save_profile_states(
        states
    )


def get_earliest_retry_after(states):
    retry_times = []

    for state in states.values():
        if (
            str(
                state.get(
                    "status",
                    ""
                )
            ).lower()
            != "limited"
        ):
            continue

        retry_after = parse_retry_after(
            state.get("retry_after")
        )

        if retry_after is not None:
            retry_times.append(
                retry_after
            )

    if not retry_times:
        return None

    return min(retry_times)



def get_profile_project_url(
    states,
    profile_index
):
    profile_name = profile_name_from_index(
        profile_index
    )

    return (
        states.get(
            profile_name,
            {}
        ).get(
            "project_url",
            ""
        )
        or ""
    ).strip()


def save_profile_project_url(
    states,
    profile_index,
    project_url
):
    project_url = (
        project_url
        or ""
    ).strip()

    if not project_url:
        return

    profile_name = profile_name_from_index(
        profile_index
    )

    state = states.setdefault(
        profile_name,
        {}
    )

    state["project_url"] = project_url
    state["profile_dir"] = (
        VIVIBE_PROFILE_DIRS[
            profile_index
        ]
    )

    save_profile_states(
        states
    )

    print(
        f"Saved project URL for "
        f"{profile_name}: {project_url}"
    )


def textarea_is_visible(page):
    try:
        textarea = page.locator(
            TEXTAREA_SELECTOR
        ).first

        return (
            textarea.count() > 0
            and textarea.is_visible()
        )
    except Exception:
        return False


def main():
    if not os.path.exists(
        QUEUE_FILE
    ):
        print(
            f"Queue file not found: "
            f"{QUEUE_FILE}"
        )
        return

    if not VIVIBE_PROFILE_DIRS:
        print(
            "No Vivibe browser profiles configured."
        )
        return

    profile_states = load_profile_states()
    preferred_profile_index = 0

    while True:
        rows = load_queue()

        job_index, job = get_next_job(
            rows
        )

        if job is None:
            print("=" * 60)
            print(
                "NO PENDING VOICE JOB LEFT"
            )
            print("=" * 60)
            break

        profile_states = load_profile_states()

        (
            current_profile_index,
            current_profile_name,
            profile_dir,
        ) = choose_available_profile(
            profile_states,
            preferred_start_index=(
                preferred_profile_index
            )
        )

        if current_profile_index is None:
            earliest_retry = (
                get_earliest_retry_after(
                    profile_states
                )
            )

            print("=" * 60)
            print(
                "NO VIVIBE PROFILE AVAILABLE"
            )

            if earliest_retry is not None:
                print(
                    "Earliest profile available at:",
                    earliest_retry.strftime(
                        PROFILE_STATE_TIME_FORMAT
                    )
                )

            print(
                "Pending job is preserved. "
                "Run worker again when a profile "
                "cooldown expires."
            )
            print("=" * 60)
            break

        category = (
            job.get("category")
            or ""
        ).strip()

        product_id = (
            job["product_id"]
        )

        print("=" * 60)
        print(
            f"START VOICE JOB: "
            f"{category}/{product_id}"
        )
        print("=" * 60)
        print(
            "Vivibe profile:",
            current_profile_name
        )
        print(
            "Profile dir:",
            profile_dir
        )

        update_job(
            rows,
            job_index,
            "running",
            ""
        )

        context = None

        try:
            with sync_playwright() as p:
                context = (
                    p.chromium
                    .launch_persistent_context(
                        profile_dir,
                        headless=False,
                        accept_downloads=True,
                    )
                )

                page = (
                    context.pages[0]
                    if context.pages
                    else context.new_page()
                )

                profile_states = (
                    load_profile_states()
                )

                run_voice_job(
                    page,
                    job,
                    profile_states,
                    current_profile_index
                )

                context.close()
                context = None

            rows = load_queue()

            update_job(
                rows,
                job_index,
                "done",
                ""
            )

            profile_states = load_profile_states()

            mark_profile_available(
                profile_states,
                current_profile_index
            )

            preferred_profile_index = (
                current_profile_index
            )

            print(
                f"DONE VOICE: "
                f"{category}/{product_id}"
            )

        except VivibeHourlyLimitError as e:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass

            rows = load_queue()

            update_job(
                rows,
                job_index,
                "pending",
                ""
            )

            profile_states = load_profile_states()

            mark_profile_limited(
                profile_states,
                current_profile_index,
                e.wait_minutes
            )

            preferred_profile_index = (
                current_profile_index + 1
            ) % len(
                VIVIBE_PROFILE_DIRS
            )

            print("=" * 60)
            print(
                "VIVIBE HOURLY LIMIT REACHED"
            )
            print(
                f"Retry job: "
                f"{category}/{product_id}"
            )
            print(
                f"{current_profile_name} "
                "marked LIMITED."
            )

            if e.wait_minutes is not None:
                print(
                    "Vivibe reported wait:",
                    f"{e.wait_minutes} minutes"
                )

            print(
                "Selecting next available profile "
                "from saved state..."
            )
            print("=" * 60)

            time.sleep(2)
            continue

        except Exception as e:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass

            rows = load_queue()

            update_job(
                rows,
                job_index,
                "failed",
                str(e)
            )

            print("=" * 60)
            print(
                "VOICE JOB FAILED"
            )
            print(
                f"{category}/{product_id}"
            )
            print(e)
            print("=" * 60)

        time.sleep(3)

    print("=" * 60)
    print(
        "VOICE WORKER FINISHED"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()