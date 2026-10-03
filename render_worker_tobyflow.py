from datetime import datetime
from pathlib import Path
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
import csv
import os
import re
import shutil
import time


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FLOW_URL = "https://flow.google.com/"
TOBYFLOW_EXTENSION_ID = "iicjfgdnngmpfocfanpiammedafmomin"
TOBYFLOW_SIDEBAR_URL = (
    f"chrome-extension://{TOBYFLOW_EXTENSION_ID}/sidebar.html"
)

PRODUCTS_ROOT = os.path.join(BASE_DIR, "products")
PROMPTS_ROOT = os.path.join(BASE_DIR, "prompts", "video_generation")
QUEUE_FILE = os.path.join(BASE_DIR, "queue", "render_queue.csv")

FLOW_PROFILES = [
    r"C:\flow_auto_profile_01",
    r"C:\flow_auto_profile_02",
    r"C:\flow_auto_profile_03",
    r"C:\flow_auto_profile_04",
    r"C:\flow_auto_profile_05",
    r"C:\flow_auto_profile_06",
    r"C:\flow_auto_profile_07",
    #r"C:\flow_auto_profile_08",
    r"C:\flow_auto_profile_09",
    r"C:\flow_auto_profile_10",
    r"C:\flow_auto_profile_11",
    r"C:\flow_auto_profile_12",
]

BLOCKED_PROFILE_FILE = os.path.join(
    BASE_DIR,
    "flow_blocked_profiles.txt"
)

# Giữ lại cơ chế flow_profile_state.txt từ worker cũ.
# File lưu INDEX của profile sẽ được ưu tiên mở ở lần tiếp theo.
PROFILE_STATE_FILE = os.path.join(
    BASE_DIR,
    "flow_profile_state.txt"
)

# Theo logic TobyFlow người dùng cung cấp:
# 1 clip = 15 Flow credits.
CREDITS_PER_CLIP = 15

# Co the bat True khi can test launcher ma khong mo UI credit.
# Mac dinh False de worker check credit va tinh capacity nhu binh thuong.
SKIP_FLOW_CREDIT_CHECK = False
SKIP_CREDIT_CHECK_CAPACITY = 1

# Cho menu account/credit co thoi gian dong hoan toan truoc khi mo
# tab TobyFlow.
POST_CREDIT_CLOSE_WAIT_SECONDS = 2

# Cho TobyFlow xu ly prompt truoc khi mo picker upload anh.
PROMPT_SETTLE_SECONDS = 5

# TobyFlow được yêu cầu chọn 10s.
TOBYFLOW_VIDEO_DURATION = "10s"

# TobyFlow tu tai video vao thu muc output cua project nay.
# Worker chi quan sat, sau do rename/move ve output tiktok-auto.
DOWNLOAD_WATCH_DIR = os.path.join(
    os.path.expanduser("~"),
    "Downloads",
    "tobyflow_output",
    "tobyflow-01"
)

# Timeout chờ TobyFlow tạo + tự tải video.
TOBYFLOW_DOWNLOAD_TIMEOUT_SECONDS = 15 * 60
FLOW_BUSY_RETRY_WAIT_SECONDS = 60
FLOW_BUSY_MAX_RETRIES = 2

# File phải ngừng thay đổi size trong số giây này mới coi là tải xong.
DOWNLOAD_STABLE_SECONDS = 3

# Nghi sau job da tai xong neu van con job tiep theo trong profile.
BETWEEN_JOBS_SETTLE_SECONDS = 15

# Giu profile mo them mot luc sau video cuoi (het capacity) truoc
# khi dong browser va chuyen sang profile ke tiep.
FINAL_PROFILE_SETTLE_SECONDS = 30

# Khoảng nghỉ ngắn sau các bước UI để TobyFlow cập nhật DOM.
UI_SETTLE_SECONDS = 1.5
TOBYFLOW_UPLOAD_SETTLE_SECONDS = 2
TOBYFLOW_TAB_SWITCH_WAIT_SECONDS = 2


class FlowBusyDialogError(RuntimeError):
    """TobyFlow bao Google Flow dang ban khi gui job."""


# Nếu extension/UI thay đổi, bật screenshot debug.
DEBUG_DIR = os.path.join(BASE_DIR, "debug_tobyflow")
os.makedirs(DEBUG_DIR, exist_ok=True)


QUEUE_FIELDNAMES = [
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
# QUEUE
# ============================================================

def load_queue():
    with open(
        QUEUE_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        return list(csv.DictReader(f))


def save_queue(rows):
    with open(
        QUEUE_FILE,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=QUEUE_FIELDNAMES,
            extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def mark_job_status(rows, job_id, status, **kwargs):
    for row in rows:
        if row.get("job_id") == job_id:
            row["status"] = status
            row["updated_at"] = datetime.now().isoformat(
                timespec="seconds"
            )
            for key, value in kwargs.items():
                row[key] = value
            break
    return rows


def channel_sort_key(value):
    text = str(value or "").strip()
    match = re.search(r"\d+", text)
    if match:
        return (0, int(match.group(0)), text.lower())
    return (1, 10**9, text.lower())


def product_sort_key(value):
    text = str(value or "").strip()
    match = re.search(r"(\d+)$", text)
    if match:
        prefix = text[:match.start()].lower()
        return (prefix, int(match.group(1)), text.lower())
    return (text.lower(), 10**9, text.lower())


def get_pending_jobs(rows):
    """
    CHANNEL-FIRST:
        CH01 -> tất cả products/clips pending
        CH02 -> tất cả products/clips pending
        CH03 -> ...
    """
    jobs = [
        row for row in rows
        if (row.get("status") or "").strip().lower() == "pending"
    ]

    jobs.sort(
        key=lambda row: (
            channel_sort_key(row.get("channel")),
            (row.get("category") or "").strip().lower(),
            product_sort_key(row.get("product_id")),
            int(row.get("clip_index") or 1),
            row.get("job_id") or "",
        )
    )

    return jobs


# ============================================================
# PATH / PROMPT / PIPELINE VALIDATION
# ============================================================

def resolve_project_path(path):
    if not path:
        return ""

    path = str(path).strip().replace("/", os.sep)

    if os.path.isabs(path):
        return os.path.normpath(path)

    return os.path.normpath(
        os.path.join(BASE_DIR, path)
    )


def read_prompt(prompt_file):
    if not prompt_file:
        raise FileNotFoundError("Prompt file is empty.")

    if os.path.isabs(prompt_file):
        path = os.path.normpath(prompt_file)
    else:
        project_path = os.path.normpath(
            os.path.join(BASE_DIR, prompt_file)
        )
        old_prompt_path = os.path.normpath(
            os.path.join(PROMPTS_ROOT, prompt_file)
        )
        path = (
            project_path
            if os.path.exists(project_path)
            else old_prompt_path
        )

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Prompt not found: {path}"
        )

    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def validate_render_pair(
    category,
    clip_index,
    start_image,
    end_image
):
    normalized_category = str(
        category or ""
    ).strip().lower()

    if normalized_category not in {
        "keychain",
        "phone_case",
        "mask",
        "eyeglasses",
    }:
        return

    clip_index = int(clip_index)

    expected_by_category = {
        "keychain": {
            2: (
                "03_hand_holding.png",
                "04_hand_holding_next_frame.png",
            ),
        },
        "phone_case": {
            1: (
                "01_clip_01_first_frame.png",
                "02_clip_01_last_frame.png",
            ),
        },
        "mask": {
            1: (
                "01_side_view.png",
                "02_front_view.png",
            ),
        },
        "eyeglasses": {
            1: (
                "01_hand_holding.png",
                "02_closeup.png",
            ),
        },
    }

    expected_pair = expected_by_category[
        normalized_category
    ].get(clip_index)

    if expected_pair is None:
        raise ValueError(
            f"Invalid {normalized_category} "
            f"clip_index: {clip_index}"
        )

    got_pair = (
        os.path.basename(start_image),
        os.path.basename(end_image),
    )

    if got_pair != expected_pair:
        raise ValueError(
            f"{normalized_category} render pair mismatch. "
            f"Expected {expected_pair}, got {got_pair}"
        )


# ============================================================
# PROFILE STATE
# ============================================================

def get_blocked_profiles():
    if not os.path.exists(BLOCKED_PROFILE_FILE):
        return set()

    today = datetime.now().date().isoformat()
    blocked = set()

    with open(
        BLOCKED_PROFILE_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            if "|" in line:
                profile_dir, blocked_date = line.rsplit("|", 1)
                if blocked_date == today:
                    blocked.add(profile_dir)

    return blocked


def add_blocked_profile(profile_dir):
    if profile_dir in get_blocked_profiles():
        return

    today = datetime.now().date().isoformat()

    with open(
        BLOCKED_PROFILE_FILE,
        "a",
        encoding="utf-8"
    ) as f:
        f.write(f"{profile_dir}|{today}\n")


def get_profile_state_index():
    """
    Đọc flow_profile_state.txt.

    Giá trị là index 0-based trong FLOW_PROFILES.
    Ví dụ:
        0 -> FLOW_PROFILES[0]
        1 -> FLOW_PROFILES[1]

    Nếu file chưa tồn tại / sai dữ liệu -> bắt đầu từ index 0.
    """
    if not os.path.exists(PROFILE_STATE_FILE):
        return 0

    try:
        with open(
            PROFILE_STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            raw = f.read().strip()

        index = int(raw)

        if not FLOW_PROFILES:
            return 0

        return index % len(FLOW_PROFILES)

    except Exception:
        return 0


def save_profile_state_index(index):
    """
    Lưu profile index sẽ được ưu tiên ở lần chạy kế tiếp.
    """
    if not FLOW_PROFILES:
        return

    normalized = int(index) % len(FLOW_PROFILES)

    with open(
        PROFILE_STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(str(normalized))

    print(
        f"Saved flow profile state: index={normalized} | "
        f"next={FLOW_PROFILES[normalized]}"
    )


def get_profile_cycle_from_state():
    """
    Trả về profile theo vòng tròn, bắt đầu từ state hiện tại.

    Ví dụ state=2:
        profile[2] -> profile[3] -> ... -> profile[0] -> profile[1]

    Profile bị block trong ngày sẽ được bỏ qua.
    """
    if not FLOW_PROFILES:
        return []

    start_index = get_profile_state_index()
    blocked = get_blocked_profiles()

    ordered = []

    for offset in range(len(FLOW_PROFILES)):
        index = (
            start_index + offset
        ) % len(FLOW_PROFILES)

        profile = FLOW_PROFILES[index]

        if profile in blocked:
            continue

        ordered.append(
            (
                index,
                index + 1,
                profile,
            )
        )

    return ordered


def advance_profile_state(current_index):
    """
    Sau khi profile đã dùng xong capacity, hết credit,
    unusual activity hoặc session cần chuyển profile:
    state trỏ sang profile kế tiếp.
    """
    if not FLOW_PROFILES:
        return

    next_index = (
        int(current_index) + 1
    ) % len(FLOW_PROFILES)

    save_profile_state_index(next_index)


# ============================================================
# FLOW CREDIT CHECK
# Reuse logic từ worker cũ nhưng click trực tiếp bằng Playwright.
# ============================================================

def get_flow_credits(page):
    print("Checking Google Flow credits...")

    avatar_button = page.locator(
        'button:has(img[alt="User profile image"])'
    ).first

    try:
        avatar_button.wait_for(
            state="visible",
            timeout=15000
        )
    except Exception:
        avatar_button = page.locator(
            ".header-user-button"
        ).first

        try:
            avatar_button.wait_for(
                state="visible",
                timeout=5000
            )
        except Exception:
            avatar_button = page.locator(
                "button.sc-355d1ae3-7"
            ).first
            avatar_button.wait_for(
                state="visible",
                timeout=10000
            )

    avatar_button.click(force=True)
    page.wait_for_timeout(700)

    credit_locator = page.locator(
        'a[href*="flow_ai_credits_page"]'
    ).first

    credit_locator.wait_for(
        state="visible",
        timeout=15000
    )

    text = credit_locator.inner_text().strip()
    print(f"Credits text: {text}")

    match = re.search(
        r"([\d.,]+)\s+Google Flow credits",
        text,
        re.IGNORECASE
    )

    if not match:
        match = re.search(r"[\d.,]+", text)

    if not match:
        raise Exception(
            f"FLOW_CREDITS_NOT_FOUND: {text}"
        )

    credits_text = (
        match.group(1)
        if match.lastindex
        else match.group(0)
    )

    credits = int(
        re.sub(r"\D", "", credits_text)
    )

    # Khi menu credit dang mo, cu click dau vao launcher TobyFlow chi
    # dong menu; tab TobyFlow se duoc mo truc tiep bang URL sau buoc nay.
    launcher = page.locator("#tobyflow-ft-launcher").first
    launcher.wait_for(state="attached", timeout=30000)
    launcher.click(force=True)
    print("Clicked TobyFlow launcher once to dismiss credit menu.")
    credit_locator.wait_for(
        state="hidden",
        timeout=5000
    )

    return credits


# ============================================================
# TOBYFLOW UI
# ============================================================

def screenshot_debug(page, name):
    path = os.path.join(
        DEBUG_DIR,
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{name}.png"
    )
    try:
        page.screenshot(path=path, full_page=True)
        print(f"Debug screenshot: {path}")
    except Exception:
        pass


def click_visible(locator, name, timeout=15000):
    locator = locator.first
    locator.wait_for(
        state="visible",
        timeout=timeout
    )
    locator.scroll_into_view_if_needed()
    locator.click(force=True)
    print(f"Clicked: {name}")
    time.sleep(UI_SETTLE_SECONDS)


def focus_tobyflow_tab(page, after_action):
    """Doi Chrome tu Flow ve tab TobyFlow sau action cua extension."""
    page.wait_for_timeout(TOBYFLOW_TAB_SWITCH_WAIT_SECONDS * 1000)
    page.bring_to_front()
    print(f"Returned to TobyFlow tab after {after_action}.")


def open_tobyflow(browser):
    """Mo sidebar.html truc tiep thanh tab, khong bam Flow launcher."""
    tobyflow_page = None

    for candidate in browser.pages:
        if candidate.url.split("?", 1)[0] == TOBYFLOW_SIDEBAR_URL:
            tobyflow_page = candidate
            break

    if tobyflow_page is None:
        tobyflow_page = browser.new_page()

    tobyflow_page.goto(
        TOBYFLOW_SIDEBAR_URL,
        wait_until="domcontentloaded",
        timeout=30000
    )
    tobyflow_page.bring_to_front()

    tobyflow_page.locator("#promptsArea").first.wait_for(
        state="visible",
        timeout=30000
    )
    tobyflow_page.wait_for_timeout(UI_SETTLE_SECONDS * 1000)

    print(f"TobyFlow tab opened: {TOBYFLOW_SIDEBAR_URL}")
    return tobyflow_page


def create_tobyflow_project(page):
    """
    Tạo project TobyFlow mới 1 lần cho profile/session.
    Sau đó nhiều jobs dùng lại project này.
    """
    # #promptsArea co the hien truoc khi handler project cua app san sang.
    page.wait_for_function(
        """() => typeof window._showProjectSelectOverlay === 'function'
               && typeof window._createNewProject === 'function'""",
        timeout=30000
    )

    page.evaluate("() => window._showProjectSelectOverlay()")

    button = page.locator(
        "button.project-select-create-btn"
    ).first

    button.wait_for(state="visible", timeout=20000)
    page.wait_for_function(
        """() => {
            const button = document.querySelector('.project-select-create-btn');
            return button && !button.disabled;
        }""",
        timeout=30000
    )

    project_click_started = """() => {
        const overlay = document.querySelector('.project-select-overlay');
        const button = overlay?.querySelector('.project-select-create-btn');
        return !overlay || Boolean(
            button?.disabled ||
            button?.dataset.running === '1' ||
            overlay.querySelector('.project-select-create-error')
        );
    }"""

    try:
        button.click(force=True, timeout=10000)
    except Exception:
        # Neu Chrome doi sang Flow ngay khi click, handler co the da chay.
        # Chi fallback khi khong co bat ky dau hieu nao cua handler.
        if not page.evaluate(project_click_started):
            button.evaluate("element => element.click()")

    try:
        page.wait_for_function(project_click_started, timeout=2000)
    except PlaywrightTimeoutError:
        # Click dau khong kich hoat handler: thu DOM click mot lan.
        button.evaluate("element => element.click()")
        page.wait_for_function(project_click_started, timeout=5000)

    print("TobyFlow project-create click accepted.")

    page.wait_for_function(
        """() => !document.querySelector('.project-select-overlay') ||
            Boolean(document.querySelector('.project-select-create-error'))""",
        timeout=30000
    )

    focus_tobyflow_tab(page, "creating the project")

    error_box = page.locator(".project-select-create-error")
    if error_box.count() and error_box.is_visible():
        raise RuntimeError(
            "TobyFlow project creation failed: "
            f"{error_box.inner_text().strip()}"
        )

    page.locator(".project-select-overlay").wait_for(
        state="hidden",
        timeout=30000
    )

    page.locator(
        "#promptsArea"
    ).first.wait_for(
        state="visible",
        timeout=20000
    )

    print("TobyFlow project ready.")


def configure_tobyflow_video(page):
    """
    Chọn Video + duration 10s.
    Lam khi mo project lan dau va sau moi lan mo lai tab TobyFlow.
    """
    video_button = page.locator(
        'button.gen-type-btn[data-value="Video"]'
    ).first

    click_visible(
        video_button,
        "TobyFlow Video mode"
    )

    duration = page.locator(
        "#flowVideoDuration"
    ).first

    duration.wait_for(
        state="visible",
        timeout=15000
    )

    duration.select_option(
        value=TOBYFLOW_VIDEO_DURATION
    )
    page.wait_for_timeout(UI_SETTLE_SECONDS * 1000)

    selected = duration.input_value()

    if selected != TOBYFLOW_VIDEO_DURATION:
        raise Exception(
            "Cannot set TobyFlow duration to "
            f"{TOBYFLOW_VIDEO_DURATION}. "
            f"Current={selected}"
        )

    print(
        f"TobyFlow duration: "
        f"{TOBYFLOW_VIDEO_DURATION}"
    )


def set_tobyflow_prompt(page, prompt_text):
    textarea = page.locator(
        "#promptsArea"
    ).first

    textarea.wait_for(
        state="visible",
        timeout=15000
    )

    textarea.fill("")
    textarea.fill(prompt_text)

    actual = textarea.input_value().strip()

    if actual != prompt_text.strip():
        raise Exception(
            "TobyFlow prompt verification failed."
        )

    print(
        f"Prompt inserted: {len(actual)} chars"
    )
    page.wait_for_timeout(PROMPT_SETTLE_SECONDS * 1000)


def open_tobyflow_image_picker(page, pick_button_id, label):
    # Bam dung o Add nho cua Start/End, khong bam vung upload chung.
    click_visible(
        page.locator(f"#{pick_button_id}"),
        f"{label} - Add"
    )

    upload_tab = page.locator(
        'button.imgpicker-tab[data-tab="upload"]'
    ).first

    click_visible(
        upload_tab,
        "Image picker - Upload"
    )

    page.locator(
        "#imgpickerBrowseBtn"
    ).first.wait_for(
        state="visible",
        timeout=15000
    )


def upload_one_tobyflow_image(page, image_path, label):
    """
    QUAN TRỌNG:
    TobyFlow yêu cầu upload từng ảnh một.
    Không set 2 files cùng một lần.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(
            f"Missing {label}: {image_path}"
        )

    browse = page.locator(
        "#imgpickerBrowseBtn"
    ).first

    browse.wait_for(
        state="visible",
        timeout=15000
    )

    with page.expect_file_chooser(
        timeout=15000
    ) as chooser_info:
        browse.click(force=True)

    chooser = chooser_info.value
    chooser.set_files(image_path)

    print(
        f"Uploaded {label}: "
        f"{os.path.basename(image_path)}"
    )

    # Chờ count upload tăng / UI xử lý file.
    page.wait_for_timeout(TOBYFLOW_UPLOAD_SETTLE_SECONDS * 1000)


def upload_tobyflow_frames(
    page,
    start_image,
    end_image
):
    """
    Moi o Start/End co nut Add rieng va picker rieng.
    Upload, Confirm tung anh; khong can gan chuoi.
    """
    for label, pick_button_id, file_id, image_path in (
        ("Start", "genTabFrame1PickBtn", "genTabFrame1FileId", start_image),
        ("End", "genTabFrame2PickBtn", "genTabFrame2FileId", end_image),
    ):
        open_tobyflow_image_picker(page, pick_button_id, label)
        upload_one_tobyflow_image(page, image_path, label)

        click_visible(
            page.locator("#imgpickerConfirmBtn"),
            f"{label} - Confirm",
            timeout=20000
        )
        page.locator(".imgpicker-overlay").wait_for(
            state="hidden",
            timeout=30000
        )
        page.wait_for_function(
            "fileId => Boolean(document.getElementById(fileId)?.value)",
            arg=file_id,
            timeout=30000
        )
        print(f"{label} frame assigned: {file_id}")


def clear_tobyflow_frames(page):
    """Thu xoa anh cu; tab mo lai co the khong con nut Xoa."""
    clear_button = page.locator(
        'button[type="button"][data-frame-bulk="clear"]'
    ).first

    try:
        clear_button.wait_for(state="visible", timeout=2000)
    except PlaywrightTimeoutError:
        print("TobyFlow Xoa button not visible; skipping clear step.")
        return

    click_visible(
        clear_button,
        "TobyFlow - Xoa anh cu",
        timeout=5000
    )

    for pick_button_id in ("genTabFrame1PickBtn", "genTabFrame2PickBtn"):
        page.locator(f"#{pick_button_id}").wait_for(
            state="visible",
            timeout=20000
        )


def snapshot_downloads():
    """
    Snapshot mp4 trong cac folder output cua TobyFlow truoc khi bam Run.
    """
    folder = Path(DOWNLOAD_WATCH_DIR)
    folder.mkdir(parents=True, exist_ok=True)

    snapshot = {}

    for path in folder.glob("*.mp4"):
        try:
            stat = path.stat()
            snapshot[str(path.resolve())] = (
                stat.st_mtime_ns,
                stat.st_size,
            )
        except OSError:
            pass

    return snapshot


def find_new_mp4(before):
    folder = Path(DOWNLOAD_WATCH_DIR)

    candidates = []

    for path in folder.glob("*.mp4"):
        try:
            resolved = str(path.resolve())
            stat = path.stat()
        except OSError:
            continue

        old = before.get(resolved)

        if (
            old is None
            or stat.st_mtime_ns > old[0]
            or stat.st_size != old[1]
        ):
            candidates.append(
                (
                    stat.st_mtime_ns,
                    path,
                    stat.st_size,
                )
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True
    )

    return candidates[0][1]


def wait_for_tobyflow_download(
    before,
    page,
    flow_page=None,
    timeout_seconds=TOBYFLOW_DOWNLOAD_TIMEOUT_SECONDS
):
    """
    Chi quan sat file TobyFlow tu tai trong thu muc output mac dinh.

    File được coi hoàn tất khi:
      - có mp4 mới / mp4 vừa thay đổi;
      - không còn file .crdownload tương ứng;
      - size ổn định DOWNLOAD_STABLE_SECONDS.
    """
    print(
        "Waiting TobyFlow to generate and "
        "auto-download video..."
    )

    deadline = time.time() + timeout_seconds
    candidate = None
    last_candidate = None
    last_size = None
    stable_since = None

    while time.time() < deadline:
        if flow_page and close_flow_busy_dialog(page, flow_page):
            raise FlowBusyDialogError("Google Flow dang ban while waiting for video")

        candidate = find_new_mp4(before)

        if candidate is not None:
            try:
                size = candidate.stat().st_size
            except OSError:
                page.wait_for_timeout(1000)
                continue

            crdownloads = (
                Path(str(candidate) + ".crdownload"),
                candidate.with_suffix(".crdownload"),
            )

            if (
                candidate == last_candidate
                and size > 0
                and size == last_size
                and not any(path.exists() for path in crdownloads)
            ):
                if stable_since is None:
                    stable_since = time.time()

                if (
                    time.time() - stable_since
                    >= DOWNLOAD_STABLE_SECONDS
                ):
                    print(
                        f"TobyFlow download complete: "
                        f"{candidate}"
                    )
                    return str(candidate)
            else:
                last_candidate = candidate
                last_size = size
                stable_since = None

        page.wait_for_timeout(1000)

    raise TimeoutError(
        "TOBYFLOW_DOWNLOAD_TIMEOUT: "
        f"no completed mp4 in {DOWNLOAD_WATCH_DIR} "
        f"within {timeout_seconds}s"
    )


def move_downloaded_video(
    downloaded_path,
    save_path
):
    os.makedirs(
        os.path.dirname(save_path),
        exist_ok=True
    )

    if os.path.exists(save_path):
        raise FileExistsError(
            f"Final video already exists: {save_path}"
        )

    shutil.move(
        downloaded_path,
        save_path
    )

    if not os.path.exists(save_path):
        raise Exception(
            f"Video move failed: {save_path}"
        )

    print(f"Saved final video: {save_path}")


def close_flow_busy_dialog(tobyflow_page, flow_page, timeout_seconds=0):
    """Dong dung hop thoai Google Flow dang ban neu xuat hien."""
    deadline = time.time() + timeout_seconds

    while True:
        for candidate in (tobyflow_page, flow_page):
            if candidate.is_closed():
                continue
            dialog = candidate.locator(".cdialog-box").filter(
                has_text="Google Flow đang bận"
            ).first
            if dialog.is_visible():
                click_visible(
                    dialog.locator(
                        'button.cdialog-btn-secondary[data-idx="0"]'
                    ),
                    "Google Flow dang ban - Dong",
                    timeout=5000
                )
                dialog.wait_for(state="hidden", timeout=5000)
                return True

        if time.time() >= deadline:
            return False
        tobyflow_page.wait_for_timeout(500)


def start_tobyflow_generation(page, flow_page):
    """
    Bấm Tạo -> Chạy.
    """
    generate_button = page.locator(
        "#startBtn"
    ).first

    try:
        click_visible(
            generate_button,
            "TobyFlow - Tạo",
            timeout=20000
        )
    except PlaywrightTimeoutError as click_exc:
        if close_flow_busy_dialog(page, flow_page):
            raise FlowBusyDialogError("Google Flow dang ban after Tao") from click_exc
        raise

    focus_tobyflow_tab(page, "Generate")

    if close_flow_busy_dialog(page, flow_page, timeout_seconds=2):
        raise FlowBusyDialogError("Google Flow dang ban after Tao")

    run_button = page.locator(
        "#confirmRunSubmit"
    ).first

    try:
        click_visible(
            run_button,
            "TobyFlow - Chạy",
            timeout=20000
        )
    except PlaywrightTimeoutError as click_exc:
        if close_flow_busy_dialog(page, flow_page):
            raise FlowBusyDialogError("Google Flow dang ban after Chay") from click_exc
        raise

    if close_flow_busy_dialog(page, flow_page, timeout_seconds=2):
        raise FlowBusyDialogError("Google Flow dang ban after Chay")


def detect_unusual_activity(page):
    """
    Chỉ phát hiện để dừng/switch profile.
    Không có logic bypass hoặc né detection.
    """
    try:
        body_text = page.locator(
            "body"
        ).inner_text(
            timeout=3000
        ).lower()
    except Exception:
        return False

    return (
        "unusual activity" in body_text
        or "hoạt động bất thường" in body_text
    )


def render_job_with_tobyflow(
    page,
    flow_page,
    job,
    save_path,
    retry_flow_busy=False
):
    category = (
        job.get("category") or ""
    ).strip()

    product_id = (
        job.get("product_id") or ""
    ).strip()

    clip_index = int(
        job.get("clip_index") or 1
    )

    start_image = resolve_project_path(
        job.get("start_image") or ""
    )

    end_image = resolve_project_path(
        job.get("end_image") or ""
    )

    prompt_file = resolve_project_path(
        job.get("prompt_file") or ""
    )

    if not category:
        raise ValueError(
            f"Missing category: {job.get('job_id')}"
        )

    if not os.path.exists(start_image):
        raise FileNotFoundError(
            f"Missing start image: {start_image}"
        )

    if not os.path.exists(end_image):
        raise FileNotFoundError(
            f"Missing end image: {end_image}"
        )

    validate_render_pair(
        category=category,
        clip_index=clip_index,
        start_image=start_image,
        end_image=end_image
    )

    prompt_text = read_prompt(prompt_file)

    page.bring_to_front()

    print(
        f"TobyFlow job: {job.get('job_id')} | "
        f"{category}/{product_id} | "
        f"CH{job.get('channel')} | "
        f"clip {clip_index}"
    )

    # Moi job cap nhat prompt, roi gan anh truc tiep vao o Start/End.
    set_tobyflow_prompt(
        page,
        prompt_text
    )

    upload_tobyflow_frames(
        page,
        start_image,
        end_image
    )

    max_retries = FLOW_BUSY_MAX_RETRIES if retry_flow_busy else 0
    for retry_number in range(max_retries + 1):
        before_download = snapshot_downloads()
        page.bring_to_front()

        try:
            start_tobyflow_generation(page, flow_page)

            # Trong luc TobyFlow chay, neu co hop thoai Flow dang ban
            # thi dong va thu lai Tao -> Chay sau mot phut.
            downloaded = wait_for_tobyflow_download(
                before_download,
                page,
                flow_page
            )
            break
        except FlowBusyDialogError as busy_exc:
            if retry_number >= max_retries:
                raise RuntimeError(
                    f"FLOW_BUSY_RETRIES_EXHAUSTED: {busy_exc}"
                ) from busy_exc
            print(
                f"Google Flow busy. Waiting "
                f"{FLOW_BUSY_RETRY_WAIT_SECONDS}s before retry "
                f"{retry_number + 1}/{max_retries}..."
            )
            time.sleep(FLOW_BUSY_RETRY_WAIT_SECONDS)

    move_downloaded_video(downloaded, save_path)

    return save_path


# ============================================================
# OUTPUT
# ============================================================

def build_video_save_path(job):
    category = (
        job.get("category") or ""
    ).strip()

    product_id = (
        job.get("product_id") or ""
    ).strip()

    channel = (
        job.get("channel") or "01"
    ).strip()

    # Chỉ zfill phần số nếu channel là số.
    channel_match = re.search(r"\d+", channel)
    if channel_match:
        channel_label = channel_match.group(0).zfill(2)
    else:
        channel_label = channel

    clip_index = int(
        job.get("clip_index") or 1
    )

    video_output_dir = os.path.abspath(
        os.path.join(
            PRODUCTS_ROOT,
            category,
            product_id,
            "output",
            "videos"
        )
    )

    os.makedirs(
        video_output_dir,
        exist_ok=True
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    return os.path.join(
        video_output_dir,
        (
            f"{product_id}_"
            f"CH{channel_label}_"
            f"clip_{clip_index:02d}_"
            f"{timestamp}.mp4"
        )
    )


# ============================================================
# PROFILE SESSION
# ============================================================

def run_profile_session(
    playwright,
    profile_number,
    profile_dir
):
    """
    Một profile:
      1. Mở Flow.
      2. Check credits.
      3. capacity = credits // 15.
      4. Mở TobyFlow.
      5. Tạo TobyFlow project mới.
      6. Video + 10s.
      7. Chạy tối đa `capacity` jobs.
      8. Chỉ sau khi dùng hết capacity mới sang profile tiếp theo,
         trừ lỗi/profile bị unavailable.
    """
    print("=" * 70)
    print(
        f"OPEN PROFILE {profile_number}: "
        f"{profile_dir}"
    )

    browser = (
        playwright.chromium
        .launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            channel="chrome",

            # Playwright mặc định thêm --disable-extensions khi launch
            # Chrome. Profile Flow của chúng ta đã cài TobyFlow sẵn,
            # nên bỏ riêng default argument này để Chrome load extension
            # từ đúng persistent profile (Default/Extensions).
            ignore_default_args=[
                "--disable-extensions",
            ],

            accept_downloads=True,
            args=[
                "--window-size=1900,1000",
                "--window-position=0,0",
                "--no-first-run",
            ],
        )
    )

    try:
        flow_page = (
            browser.pages[0]
            if browser.pages
            else browser.new_page()
        )
        flow_page.bring_to_front()

        flow_page.goto(
            FLOW_URL,
            wait_until="domcontentloaded",
            timeout=120000
        )

        print("Waiting Flow + TobyFlow extension...")
        time.sleep(5)

        if SKIP_FLOW_CREDIT_CHECK:
            capacity = SKIP_CREDIT_CHECK_CAPACITY
            print(
                "TEMP: skipping Flow credit check; "
                f"capacity forced to {capacity} clip(s)."
            )
        else:
            credits = get_flow_credits(flow_page)

            capacity = credits // CREDITS_PER_CLIP

            print(
                f"Profile credits: {credits} | "
                f"{CREDITS_PER_CLIP} credits/clip | "
                f"capacity: {capacity} clip(s)"
            )

            if capacity <= 0:
                print(
                    "Profile does not have enough credits "
                    "for another clip."
                )
                add_blocked_profile(profile_dir)
                return 0, "insufficient_credits"

            print(
                "Waiting for Flow credit UI to close before "
                "opening TobyFlow..."
            )
            time.sleep(POST_CREDIT_CLOSE_WAIT_SECONDS)

        tobyflow_page = open_tobyflow(browser)
        create_tobyflow_project(tobyflow_page)
        configure_tobyflow_video(tobyflow_page)

        completed_in_profile = 0

        while completed_in_profile < capacity:
            rows = load_queue()
            pending_jobs = get_pending_jobs(rows)

            if not pending_jobs:
                print("No pending jobs left.")
                return completed_in_profile, "queue_empty"

            job = pending_jobs[0]
            job_id = job["job_id"]

            save_path = build_video_save_path(job)

            rows = mark_job_status(
                rows,
                job_id,
                "rendering",
                profile=profile_dir,
                error=""
            )
            save_queue(rows)

            print("-" * 70)
            print(
                f"PROFILE {profile_number} "
                f"JOB {completed_in_profile + 1}/{capacity}: "
                f"{job_id}"
            )

            try:
                if completed_in_profile > 0:
                    # Tab TobyFlow da dong trong khoang nghi 15s.
                    # Mo lai cung project, khong tao project moi.
                    if tobyflow_page.is_closed():
                        tobyflow_page = open_tobyflow(browser)
                        configure_tobyflow_video(tobyflow_page)

                    # Xoa cap anh cu roi chon lai Start/End.
                    focus_tobyflow_tab(
                        tobyflow_page,
                        "reopening for the next job"
                    )
                    clear_tobyflow_frames(tobyflow_page)

                render_job_with_tobyflow(
                    page=tobyflow_page,
                    flow_page=flow_page,
                    job=job,
                    save_path=save_path,
                    retry_flow_busy=(completed_in_profile > 0)
                )

                rows = load_queue()

                attempts = int(
                    job.get("attempts") or 0
                ) + 1

                rows = mark_job_status(
                    rows,
                    job_id,
                    "done",
                    video_path=save_path,
                    profile=profile_dir,
                    error="",
                    attempts=str(attempts)
                )
                save_queue(rows)

                completed_in_profile += 1

                print(
                    f"DONE {job_id} | "
                    f"profile progress "
                    f"{completed_in_profile}/{capacity}"
                )

                if (
                    completed_in_profile < capacity
                    and get_pending_jobs(load_queue())
                ):
                    print(
                        "Closing TobyFlow tab, keeping Flow open for "
                        f"{BETWEEN_JOBS_SETTLE_SECONDS}s before next job..."
                    )
                    try:
                        flow_page.bring_to_front()
                        tobyflow_page.close()
                    except Exception as close_exc:
                        # Video da duoc danh dau done; khong ghi de
                        # thanh failed neu chi loi thao tac dong tab.
                        print(f"Could not close TobyFlow tab: {close_exc}")
                        return completed_in_profile, "session_error"
                    time.sleep(BETWEEN_JOBS_SETTLE_SECONDS)

            except Exception as exc:
                error_text = str(exc)

                print(
                    f"Job error: {job_id} | "
                    f"{error_text}"
                )

                unusual = (
                    detect_unusual_activity(flow_page)
                    or "UNUSUAL_ACTIVITY" in error_text
                )

                rows = load_queue()

                if unusual:
                    screenshot_debug(
                        flow_page,
                        "unusual_activity"
                    )

                    # Không tính attempt và không fail job:
                    # profile bị block trong ngày, job trả pending,
                    # caller chuyển profile khác.
                    rows = mark_job_status(
                        rows,
                        job_id,
                        "pending",
                        profile=profile_dir,
                        error="UNUSUAL_ACTIVITY"
                    )
                    save_queue(rows)

                    add_blocked_profile(profile_dir)

                    print(
                        "Unusual activity detected. "
                        "Profile blocked for today; "
                        "switching profile."
                    )

                    return completed_in_profile, "unusual_activity"

                # Các lỗi TobyFlow/UI khác: fail job như worker cũ,
                # rồi vẫn có thể tiếp tục job kế tiếp trên profile.
                attempts = int(
                    job.get("attempts") or 0
                ) + 1

                rows = mark_job_status(
                    rows,
                    job_id,
                    "failed",
                    profile=profile_dir,
                    error=error_text,
                    attempts=str(attempts)
                )
                save_queue(rows)

                screenshot_debug(
                    tobyflow_page,
                    "job_failed"
                )

                # UI có thể đang ở trạng thái không sạch sau lỗi.
                # Dừng session này để tránh job sau bị dính state cũ.
                return completed_in_profile, "session_error"

        print(
            f"Profile {profile_number} reached "
            f"calculated capacity: {capacity} clip(s)."
        )

        print(
            f"Keeping profile {profile_number} open for "
            f"{FINAL_PROFILE_SETTLE_SECONDS}s after its final video..."
        )
        flow_page.wait_for_timeout(
            FINAL_PROFILE_SETTLE_SECONDS * 1000
        )

        return completed_in_profile, "capacity_reached"

    finally:
        browser.close()


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("TOBYFLOW RENDER WORKER")
    print(
        "Queue order: CHANNEL-FIRST "
        "(finish CH01 products before CH02...)"
    )
    print(
        "Profile order: flow_profile_state.txt "
        "(persistent across restarts)"
    )
    print(
        f"Credits rule: {CREDITS_PER_CLIP} credits/clip"
    )
    print(
        f"TobyFlow duration: {TOBYFLOW_VIDEO_DURATION}"
    )
    print(
        f"Watching downloads: {DOWNLOAD_WATCH_DIR}"
    )

    with sync_playwright() as p:
        while True:
            rows = load_queue()
            pending_jobs = get_pending_jobs(rows)

            if not pending_jobs:
                print("=" * 70)
                print("No pending jobs left. Done.")
                break

            profile_cycle = get_profile_cycle_from_state()

            if not profile_cycle:
                print(
                    "No available Flow profiles left today. "
                    "Stopping batch."
                )
                break

            made_progress = False
            switched_profile = False

            for (
                profile_index,
                profile_number,
                profile_dir,
            ) in profile_cycle:

                if not get_pending_jobs(load_queue()):
                    break

                # Ghi lại profile hiện tại trước khi mở.
                # Nếu script/crash đột ngột, restart sẽ bắt đầu lại
                # đúng profile này và check credits thực tế lại.
                save_profile_state_index(profile_index)

                try:
                    completed, reason = run_profile_session(
                        playwright=p,
                        profile_number=profile_number,
                        profile_dir=profile_dir
                    )

                    if completed > 0:
                        made_progress = True

                    if reason == "queue_empty":
                        break

                    # Profile đã dùng xong capacity hoặc không thể
                    # tiếp tục -> state chuyển sang profile kế.
                    if reason in {
                        "capacity_reached",
                        "insufficient_credits",
                        "unusual_activity",
                        "session_error",
                    }:
                        advance_profile_state(profile_index)
                        switched_profile = True

                except Exception as exc:
                    print(
                        f"Profile session error "
                        f"{profile_number}: {exc}"
                    )

                    # Lỗi session: chuyển state sang profile kế,
                    # nhưng không có logic bypass Flow restriction.
                    advance_profile_state(profile_index)
                    switched_profile = True
                    continue

            if not get_pending_jobs(load_queue()):
                continue

            if not made_progress and not switched_profile:
                print(
                    "No profile completed any job and profile state "
                    "did not advance. Stopping to avoid an endless loop."
                )
                break

            # Sau khi đi hết một cycle mà vẫn còn pending nhưng không
            # render được clip nào, dừng để tránh quay vòng profile vô hạn.
            if not made_progress:
                print(
                    "No profile completed any job in this pass. "
                    "Stopping batch."
                )
                break

    print("Batch render finished.")


if __name__ == "__main__":
    main()
