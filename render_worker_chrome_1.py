from datetime import datetime
from playwright.sync_api import sync_playwright
import os
import time
import math
import csv
import re
import random
import sys
import pyautogui
import pyperclip

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


FLOW_URL = "https://flow.google.com/"

# Đánh dấu Chrome (thật, channel="chrome") đầu tiên được mở
# trong lần chạy script này. Nghi vấn: browser đầu tiên trong
# ngày/phiên có thể tự relaunch giữa chừng do cơ chế cập nhật
# nền của Chrome thật, đúng lúc download đang diễn ra -> mất
# kết nối context giữa chừng ("Target page, context or browser
# has been closed"). Các profile mở SAU trong cùng lần chạy
# không gặp lại vì Chrome khi đó đã "ổn định". Ta thêm thời
# gian khởi động ấm + tắt bớt cơ chế nền chỉ để giảm khả năng
# này, không đảm bảo tuyệt đối vì đây là hành vi của Chrome,
# không phải lỗi logic trong script.
_is_first_browser_launch_in_run = True

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

PRODUCTS_ROOT = os.path.join(
    BASE_DIR,
    "products"
)

PROMPTS_ROOT = os.path.join(
    BASE_DIR,
    "prompts",
    "video_generation"
)

QUEUE_FILE = os.path.join(
    BASE_DIR,
    "queue",
    "render_queue.csv"
)


try:
    from profiles_manager import get_active_flow_profiles, load_profiles_config
    FLOW_PROFILES = get_active_flow_profiles()
    _cfg = load_profiles_config()
    print("=" * 60)
    print("🔧 CHROME PROFILES CẤU HÌNH CHO GOOGLE FLOW:")
    print(f"   Chế độ: {_cfg.get('run_mode', 'single')} | Profile chính: {_cfg.get('active_flow_profile')}")
    print(f"   Danh sách sử dụng ({len(FLOW_PROFILES)}): {FLOW_PROFILES}")
    print("=" * 60)
except Exception as _e:
    print(f"⚠️ Không thể đọc profiles_manager: {_e}. Dùng danh sách mặc định.")
    FLOW_PROFILES = [
        r"C:\flow_auto_profile_01",
        r"C:\flow_auto_profile_02",
        r"C:\flow_auto_profile_03",
        r"C:\flow_auto_profile_04",
        r"C:\flow_auto_profile_05",
    ]


VIDEOS_PER_PROFILE = 3

PROFILE_STATE_FILE = os.path.join(
    BASE_DIR,
    "flow_profile_state.txt"
)

BLOCKED_PROFILE_FILE = os.path.join(
    BASE_DIR,
    "flow_blocked_profiles.txt"
)


# ─────────────────────────────────────────────
# Queue
# ─────────────────────────────────────────────

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
    fieldnames = [
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

    with open(
        QUEUE_FILE,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(rows)


# ─────────────────────────────────────────────
# Profile management
# ─────────────────────────────────────────────

def get_blocked_profiles():
    """
    Chỉ trả về các profile bị block trong ngày hiện tại.

    Dòng mới có định dạng:
        C:\\flow_auto_profile_01|2026-07-17

    Dòng cũ chỉ chứa đường dẫn vẫn được hỗ trợ. Với định dạng cũ,
    profile chỉ bị xem là block nếu file được cập nhật trong hôm nay.
    """

    if not os.path.exists(
        BLOCKED_PROFILE_FILE
    ):
        return set()

    today = (
        datetime.now()
        .date()
        .isoformat()
    )

    legacy_is_today = (
        datetime.fromtimestamp(
            os.path.getmtime(
                BLOCKED_PROFILE_FILE
            )
        ).date()
        == datetime.now().date()
    )

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
                profile_dir, blocked_date = (
                    line.rsplit(
                        "|",
                        1
                    )
                )

                if blocked_date == today:
                    blocked.add(
                        profile_dir
                    )

            elif legacy_is_today:
                blocked.add(
                    line
                )

    return blocked


def add_blocked_profile(profile_dir):
    """
    Block profile đến hết ngày hiện tại,
    tránh ghi trùng.
    """

    if profile_dir in get_blocked_profiles():
        return

    today = (
        datetime.now()
        .date()
        .isoformat()
    )

    with open(
        BLOCKED_PROFILE_FILE,
        "a",
        encoding="utf-8"
    ) as f:
        f.write(
            f"{profile_dir}|{today}\n"
        )


def get_job_index():
    if not os.path.exists(
        PROFILE_STATE_FILE
    ):
        return 0

    with open(
        PROFILE_STATE_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        value = f.read().strip()

    return (
        int(value)
        if value.isdigit()
        else 0
    )


def save_job_index(index):
    with open(
        PROFILE_STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(
            str(index)
        )


def get_next_profile():
    """
    Lấy profile tiếp theo chưa bị block,
    tăng job_index lên 1.
    """

    blocked_profiles = (
        get_blocked_profiles()
    )

    job_index = get_job_index()

    for _ in range(
        len(FLOW_PROFILES)
    ):
        profile_index = (
            job_index
            // VIDEOS_PER_PROFILE
        ) % len(FLOW_PROFILES)

        profile_dir = (
            FLOW_PROFILES[
                profile_index
            ]
        )

        if (
            profile_dir
            not in blocked_profiles
        ):
            save_job_index(
                job_index + 1
            )

            return (
                profile_dir,
                profile_index + 1
            )

        job_index += (
            VIDEOS_PER_PROFILE
        )

    raise Exception(
        "All Flow profiles are blocked."
    )


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def human_delay(min_seconds=0.12, max_seconds=0.30):
    """Delay ngẫu nhiên ngắn giữa các thao tác UI."""
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)
    return delay


def viewport_to_screen(page, x, y):
    """
    Đổi tọa độ viewport của Playwright sang tọa độ màn hình Windows.

    Playwright page.mouse chỉ phát mouse event bên trong browser context và
    không di chuyển con trỏ Windows thật. Hàm này dùng geometry của browser
    để map điểm trong viewport -> vị trí màn hình, sau đó pyautogui sẽ điều
    khiển con trỏ thật.
    """
    geometry = page.evaluate(
        """([x, y]) => {
            const dpr = window.devicePixelRatio || 1;
            const screenX = window.screenX || window.screenLeft || 0;
            const screenY = window.screenY || window.screenTop || 0;
            const outerWidth = window.outerWidth || window.innerWidth;
            const outerHeight = window.outerHeight || window.innerHeight;
            const innerWidth = window.innerWidth;
            const innerHeight = window.innerHeight;

            // Chrome desktop: viewport nằm bên trong outer window.
            // Phần chênh ngang là 2 bên viền; phần chênh dọc chủ yếu là
            // title bar + toolbar. Dùng tỷ lệ devicePixelRatio để quy đổi
            // CSS pixel -> physical screen pixel cho pyautogui.
            const chromeLeft = Math.max(0, (outerWidth - innerWidth) / 2);
            const chromeTop = Math.max(0, outerHeight - innerHeight);

            return {
                x: Math.round((screenX + chromeLeft + x) * dpr),
                y: Math.round((screenY + chromeTop + y) * dpr),
                dpr,
                screenX,
                screenY,
                innerWidth,
                innerHeight,
                outerWidth,
                outerHeight
            };
        }""",
        [x, y]
    )
    return geometry


def bezier_curve(p0, p1, p2, p3, num_points=15):
    """Tạo danh sách các tọa độ dọc theo đường cong Bézier bậc 3 với Ease-InOut."""
    points = []
    for i in range(num_points + 1):
        t = i / float(num_points)
        ease_t = (1 - math.cos(t * math.pi)) / 2
        cx = (
            (1 - ease_t)**3 * p0[0]
            + 3 * (1 - ease_t)**2 * ease_t * p1[0]
            + 3 * (1 - ease_t) * ease_t**2 * p2[0]
            + ease_t**3 * p3[0]
        )
        cy = (
            (1 - ease_t)**3 * p0[1]
            + 3 * (1 - ease_t)**2 * ease_t * p1[1]
            + 3 * (1 - ease_t) * ease_t**2 * p2[1]
            + ease_t**3 * p3[1]
        )
        points.append((cx, cy))
    return points


def human_click(page, locator, name="element", button="left", timeout=10000):
    """
    Di chuyển con trỏ mượt mà theo đường cong Bézier uốn lượn tự nhiên
    vào bên trong vị trí nút và click chân thực (mouse down -> hold -> up).
    """
    locator = locator.first
    locator.wait_for(state="visible", timeout=timeout)
    locator.scroll_into_view_if_needed()
    human_delay(0.06, 0.14)

    box = locator.bounding_box()
    if not box:
        raise Exception(f"{name}: cannot get bounding box")

    # Chọn một điểm ngẫu nhiên an toàn trong vùng nút (30% - 70%)
    padding_x = box["width"] * 0.25
    padding_y = box["height"] * 0.25
    viewport_x = box["x"] + random.uniform(padding_x, max(padding_x, box["width"] - padding_x))
    viewport_y = box["y"] + random.uniform(padding_y, max(padding_y, box["height"] - padding_y))

    print(
        f"{name}: bezier move -> viewport "
        f"({viewport_x:.0f}, {viewport_y:.0f})"
    )

    try:
        page.bring_to_front()
    except Exception:
        pass

    # Di chuyển chuột Windows thật theo đường cong Bézier
    try:
        cur_x, cur_y = pyautogui.position()
        screen = viewport_to_screen(page, viewport_x, viewport_y)
        target_x = int(screen["x"])
        target_y = int(screen["y"])

        dx = target_x - cur_x
        dy = target_y - cur_y
        dist = math.hypot(dx, dy)

        if dist > 8:
            # Tạo 2 điểm uốn cong ngẫu nhiên (Control Points)
            side = 1 if random.random() > 0.5 else -1
            deviation = min(60, dist * random.uniform(0.12, 0.28)) * side
            p1 = (cur_x + dx * 0.3 - dy * deviation / (dist + 0.1), cur_y + dy * 0.3 + dx * deviation / (dist + 0.1))
            p2 = (cur_x + dx * 0.7 + dy * deviation / (dist + 0.1), cur_y + dy * 0.7 - dx * deviation / (dist + 0.1))

            steps = max(6, min(18, int(dist / 35)))
            pts = bezier_curve((cur_x, cur_y), p1, p2, (target_x, target_y), num_points=steps)

            for pt_x, pt_y in pts:
                pyautogui.moveTo(int(pt_x), int(pt_y))
                time.sleep(random.uniform(0.005, 0.012))
        else:
            pyautogui.moveTo(target_x, target_y)

    except Exception as e:
        print(f"{name}: OS mouse move skipped: {e}")

    # Phát chuỗi mouse.move chuẩn xác bên trong DOM để Google Flow ghi nhận trajectory
    page.mouse.move(viewport_x, viewport_y, steps=4)
    human_delay(0.04, 0.08)

    # Click chân thực: down -> giữ vài ms -> up
    page.mouse.down(button=button)
    time.sleep(random.uniform(0.035, 0.075))
    page.mouse.up(button=button)

    human_delay(0.10, 0.22)


def human_click_xy(page, x, y, name="coordinate", button="left"):
    """
    Di chuyển con trỏ Windows thật theo đường cong Bézier tới tọa độ mục tiêu
    rồi click chân thực bằng Playwright.
    """
    print(
        f"{name}: bezier move -> viewport "
        f"({x:.0f}, {y:.0f})"
    )

    try:
        page.bring_to_front()
    except Exception:
        pass

    try:
        cur_x, cur_y = pyautogui.position()
        screen = viewport_to_screen(page, x, y)
        target_x = int(screen["x"])
        target_y = int(screen["y"])

        dx = target_x - cur_x
        dy = target_y - cur_y
        dist = math.hypot(dx, dy)

        if dist > 8:
            side = 1 if random.random() > 0.5 else -1
            deviation = min(60, dist * random.uniform(0.12, 0.28)) * side
            p1 = (cur_x + dx * 0.3 - dy * deviation / (dist + 0.1), cur_y + dy * 0.3 + dx * deviation / (dist + 0.1))
            p2 = (cur_x + dx * 0.7 + dy * deviation / (dist + 0.1), cur_y + dy * 0.7 - dx * deviation / (dist + 0.1))

            steps = max(6, min(18, int(dist / 35)))
            pts = bezier_curve((cur_x, cur_y), p1, p2, (target_x, target_y), num_points=steps)

            for pt_x, pt_y in pts:
                pyautogui.moveTo(int(pt_x), int(pt_y))
                time.sleep(random.uniform(0.005, 0.012))
        else:
            pyautogui.moveTo(target_x, target_y)

    except Exception as e:
        print(f"{name}: OS mouse move skipped: {e}")

    page.mouse.move(x, y, steps=4)
    human_delay(0.04, 0.08)
    page.mouse.down(button=button)
    time.sleep(random.uniform(0.035, 0.075))
    page.mouse.up(button=button)
    human_delay(0.10, 0.22)


def resolve_project_path(path):
    """
    Hỗ trợ đường dẫn tương đối và tuyệt đối.

    Build render queue mới có thể ghi đường dẫn đầy đủ.
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


def get_ai_image_path(
    category,
    product_id,
    filename
):
    """
    Đường dẫn ảnh dùng chung cho mọi category:

    products/{category}/{product_id}/images/ai/{filename}

    Ví dụ:
        products/snack/SNK001/images/ai/...
        products/keychain/KC001/images/ai/...
        products/phone_case/PC001/images/ai/...
        products/eyeglasses/GL001/images/ai/...
    """

    path = os.path.abspath(
        os.path.join(
            PRODUCTS_ROOT,
            category,
            product_id,
            "images",
            "ai",
            filename
        )
    )

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Missing AI image: {path}"
        )

    return path


def validate_render_pair(
    category,
    clip_index,
    start_image,
    end_image
):
    """
    Kiểm tra các category đã đổi pipeline để bảo đảm
    render_queue bám đúng frame pair hiện tại.

    snack:
        chỉ có Clip 01
        01_hand_holding.png
        -> 01_hand_holding.png

    keychain:
        chỉ còn Clip 02
        03_hand_holding.png
        -> 04_hand_holding_next_frame.png

    phone_case:
        chỉ còn Clip 01
        01_clip_01_first_frame.png
        -> 02_clip_01_last_frame.png

    eyeglasses:
        chỉ có Clip 01
        01_hand_holding.png
        -> 02_closeup.png
    """

    normalized_category = (
        str(category or "")
        .strip()
        .lower()
    )

    if normalized_category not in {
        "snack",
        "keychain",
        "phone_case",
        "eyeglasses",
    }:
        return

    try:
        clip_index_int = int(
            clip_index
        )
    except Exception:
        raise ValueError(
            f"Invalid {normalized_category} "
            f"clip_index: {clip_index}"
        )

    start_name = os.path.basename(
        str(start_image or "")
    )

    end_name = os.path.basename(
        str(end_image or "")
    )

    expected_by_category = {
        "snack": {
            1: (
                "01_hand_holding.png",
                "01_hand_holding.png",
            ),
        },
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
        "eyeglasses": {
            1: (
                "01_hand_holding.png",
                "02_closeup.png",
            ),
        },
    }

    expected_pair = (
        expected_by_category[
            normalized_category
        ].get(
            clip_index_int
        )
    )

    if expected_pair is None:
        valid_clips = ", ".join(
            str(value)
            for value in sorted(
                expected_by_category[
                    normalized_category
                ].keys()
            )
        )

        raise ValueError(
            f"Invalid {normalized_category} "
            f"clip_index: {clip_index}. "
            f"Expected clip(s): {valid_clips}"
        )

    expected_start, expected_end = (
        expected_pair
    )

    if (
        start_name != expected_start
        or end_name != expected_end
    ):
        raise ValueError(
            f"{normalized_category} render pair "
            "does not match the current pipeline. "
            f"clip_index={clip_index} | "
            f"expected=({expected_start} -> "
            f"{expected_end}) | "
            f"got=({start_name} -> {end_name})"
        )


def read_prompt(prompt_file):
    """
    Hỗ trợ prompt_file là đường dẫn đầy đủ
    hoặc đường dẫn tương đối từ project.
    """

    if not prompt_file:
        raise FileNotFoundError(
            "Prompt file is empty."
        )

    if os.path.isabs(prompt_file):
        path = os.path.normpath(
            prompt_file
        )

    else:
        project_path = os.path.normpath(
            os.path.join(
                BASE_DIR,
                prompt_file
            )
        )

        old_prompt_path = os.path.normpath(
            os.path.join(
                PROMPTS_ROOT,
                prompt_file
            )
        )

        if os.path.exists(project_path):
            path = project_path
        else:
            path = old_prompt_path

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Prompt not found: {path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        return f.read().strip()


# role="option" nằm trên <button class="asset-item">.
# Tên file nằm trong <span class="asset-title">,
# KHÔNG nằm trong img alt (alt="" luôn rỗng).
ASSET_CARD_SELECTOR = "button.asset-item[role='option']"

# Card chỉ thực sự "ready" khi thumbnail đã load ảnh
# thật (src bắt đầu bằng http...). Card có thể đã
# xuất hiện trong DOM nhưng vẫn đang loading, chưa có
# ảnh thumbnail -> không được tính là ready.
ASSET_CARD_READY_SELECTOR = (
    f"{ASSET_CARD_SELECTOR}"
    f":has(img.asset-thumbnail-image[src^='http'])"
)


def wait_image_cards_stable(
    page,
    expected_count,
    timeout_seconds=60
):
    start_time = time.time()
    last_ready_count = -1

    while time.time() - start_time < timeout_seconds:
        ready_count = page.locator(
            ASSET_CARD_READY_SELECTOR
        ).count()

        if ready_count >= expected_count:
            print(
                f"Image cards ready: {ready_count}/{expected_count}. Proceeding."
            )
            return

        last_ready_count = ready_count
        time.sleep(0.5)

    page.screenshot(
        path="debug_upload_timeout.png",
        full_page=True
    )

    raise Exception(
        f"Upload timeout. "
        f"Expected {expected_count}, "
        f"got {last_ready_count} ready"
    )


def click_image_card(
    page,
    filename,
    timeout_seconds=15
):
    # Lọc theo đúng tên trong span.asset-title
    # (khớp chính xác, tránh nhầm giữa 2 file có
    # tên gần giống nhau, vd 03_hand_holding.png
    # và 03_hand_holding_v2.png).
    card = page.locator(
        ASSET_CARD_SELECTOR
    ).filter(
        has=page.locator(
            f"span.asset-title:text-is('{filename}')"
        )
    )

    if card.count() == 0:
        raise Exception(
            f"Image card '{filename}' not found."
        )

    card = card.first

    # Đợi thumbnail thật load xong (src http...)
    # trước khi bấm, tránh bấm nhầm lúc card còn
    # đang loading (chưa có ảnh).
    thumb = card.locator(
        "img.asset-thumbnail-image"
    )

    ready = False

    for i in range(int(timeout_seconds / 0.5)):
        if thumb.count() > 0:
            src = thumb.get_attribute("src")

            if src and src.startswith("http"):
                ready = True
                break

        time.sleep(0.5)

    if not ready:
        raise Exception(
            f"Image card '{filename}' chưa sẵn sàng "
            f"(thumbnail chưa load xong sau "
            f"{timeout_seconds}s)."
        )

    card.scroll_into_view_if_needed()

    time.sleep(0.3)

    box = card.bounding_box()

    if not box:
        raise Exception(
            f"Image card '{filename}' not visible."
        )

    human_click(
        page,
        card,
        name=f"Image card {filename}"
    )

    time.sleep(0.5)


def detect_video_card_selector(page, timeout_sec=20):
    """
    Tự động nhận diện selector cho video card trên Google Flow:
    Ưu tiên 'flow-grid-tile-container:has(flow-video-tile)', sau đó 'flow-video-tile', 'flow-tile-container:has(flow-video-tile)'.
    """
    for _ in range(timeout_sec):
        if page.locator("flow-grid-tile-container:has(flow-video-tile)").count() > 0:
            return "flow-grid-tile-container:has(flow-video-tile)"
        if page.locator("flow-video-tile").count() > 0:
            return "flow-video-tile"
        if page.locator("flow-tile-container:has(flow-video-tile)").count() > 0:
            return "flow-tile-container:has(flow-video-tile)"
        time.sleep(1)
    return "flow-grid-tile-container:has(flow-video-tile), flow-video-tile"


# ─────────────────────────────────────────────
# Context menu (chuột phải) của video card
# ─────────────────────────────────────────────
VIDEO_MENU_ITEM_SELECTOR = (
    "flow-video-context-menu-items button[mat-menu-item], "
    "flow-media-context-menu-items button[mat-menu-item]"
)
DOWNLOAD_LABEL_RE = re.compile(r"^\s*(Download|Tải xuống)\s*$", re.IGNORECASE)


def get_video_card_locator(page, card_selector, idx):
    """Trả về locator của video card thứ idx (None nếu không có card nào)."""
    loc = page.locator(card_selector)
    if loc.count() == 0:
        loc = page.locator("flow-video-tile")
    total = loc.count()
    if total == 0:
        return None
    if idx is None or idx < 0 or idx >= total:
        idx = 0
    return loc.nth(idx)


def find_download_menu_item(page):
    """
    Tìm mục 'Download' đang HIỂN THỊ và KHÔNG bị disable trong menu chuột phải
    (<flow-video-context-menu-items> / <flow-media-context-menu-items>).
    Trả về locator hoặc None.
    """
    candidates = [
        page.locator(VIDEO_MENU_ITEM_SELECTOR).filter(
            has=page.locator(".label", has_text=DOWNLOAD_LABEL_RE)
        ),
        page.locator(
            "div[role='menu'] button[mat-menu-item], .mat-mdc-menu-panel button[mat-menu-item]"
        ).filter(
            has=page.locator("mat-icon", has_text=re.compile(r"^\s*download\s*$"))
        ),
    ]
    for cand in candidates:
        try:
            if cand.count() == 0:
                continue
            item = cand.first
            if not item.is_visible():
                continue
            disabled = (
                item.get_attribute("disabled") is not None
                or item.get_attribute("aria-disabled") == "true"
            )
            if disabled:
                continue
            return item
        except Exception:
            continue
    return None


def close_video_context_menu(page):
    """Đóng mọi menu đang mở (Escape), đảm bảo không còn backdrop che card."""
    for _ in range(3):
        try:
            if page.locator(".mat-mdc-menu-panel:visible, div[role='menu']:visible").count() == 0:
                break
            page.keyboard.press("Escape")
            time.sleep(0.25)
        except Exception:
            break


def _poll_download_item(page, timeout_sec=2.5):
    """Chờ tối đa timeout_sec giây cho mục Download xuất hiện."""
    end = time.time() + timeout_sec
    while time.time() < end:
        item = find_download_menu_item(page)
        if item is not None:
            return item
        time.sleep(0.15)
    return None


def open_video_context_menu(page, card_loc, card_selector="", card_index=0, full_fallback=True):
    """
    Mở menu của video card và trả về locator mục 'Download' nếu mở thành công,
    ngược lại trả về None. Dùng làm phép KIỂM TRA VIDEO READY:
    video chỉ có mục Download bấm được khi đã render xong.

    Thứ tự thử (mỗi cách tự dọn menu cũ trước khi thử cách mới):
      A. Chuột phải THẬT (human_click, button='right') vào ảnh thumbnail
      B. Hover card -> bấm nút 3 chấm 'More options' trên hotbar
      C. Phát sự kiện contextmenu giả lên đúng phần tử có class mat-context-menu-trigger
    """
    close_video_context_menu(page)

    try:
        card_loc.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass
    time.sleep(0.3)

    # ── A. Chuột phải thật vào thumbnail ──
    try:
        target = card_loc.locator("img.thumbnail").first
        if target.count() == 0:
            target = card_loc.locator("flow-video-tile, .container").first
        if target.count() == 0:
            target = card_loc
        human_click(page, target, name="video card (right-click)", button="right", timeout=4000)
        item = _poll_download_item(page, 2.5)
        if item is not None:
            return item
    except Exception as e:
        print(f"  [menu] Chuột phải thật lỗi: {e}")

    if not full_fallback:
        close_video_context_menu(page)
        return None

    # ── B. Nút 3 chấm trên hotbar (chỉ hiện khi hover) ──
    close_video_context_menu(page)
    try:
        hover_target = card_loc.locator("img.thumbnail, flow-video-tile").first
        if hover_target.count() == 0:
            hover_target = card_loc
        hover_target.hover(force=True, timeout=3000)
        time.sleep(0.5)
        more_btn = card_loc.locator(
            "button[aria-label='More options'], button[aria-label='Tuỳ chọn khác'], "
            "button:has(mat-icon:has-text('more_vert'))"
        ).first
        if more_btn.count() > 0:
            more_btn.click(force=True, timeout=3000)
            item = _poll_download_item(page, 2.5)
            if item is not None:
                return item
    except Exception as e:
        print(f"  [menu] Nút 3 chấm lỗi: {e}")

    # ── C. contextmenu giả, nhắm vào phần tử có mat-context-menu-trigger ──
    close_video_context_menu(page)
    try:
        page.evaluate(
            """
            (args) => {
                let cards = Array.from(document.querySelectorAll(args.sel));
                if (cards.length === 0) cards = Array.from(document.querySelectorAll('flow-video-tile'));
                const card = cards[args.idx] || cards[0];
                if (!card) return false;
                const trigger = card.matches('.mat-context-menu-trigger')
                    ? card
                    : (card.closest('.mat-context-menu-trigger') || card.querySelector('.mat-context-menu-trigger') || card);
                const inner = card.querySelector('img.thumbnail') || trigger;
                const r = inner.getBoundingClientRect();
                const init = {bubbles: true, cancelable: true, composed: true, view: window,
                              clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
                              button: 2, buttons: 2};
                inner.dispatchEvent(new MouseEvent('contextmenu', init));
                return true;
            }
            """,
            {"sel": card_selector or "flow-video-tile", "idx": card_index or 0},
        )
        item = _poll_download_item(page, 2.5)
        if item is not None:
            return item
    except Exception as e:
        print(f"  [menu] contextmenu giả lỗi: {e}")

    close_video_context_menu(page)
    return None


def wait_and_download_video_card(
    page,
    card_index=0,
    save_path="",
    prompt_text=""
):
    """
    Chờ video render hoàn tất trên thẻ video card và tải về.
    Hỗ trợ nhận diện chính xác card mới tạo qua:
    1. Card đang có tiến trình sinh (.progress-bar hoặc overlay-has-progress-bar)
    2. Card có aria-label / footer-title khớp từ khóa prompt
    3. Thẻ img.thumbnail có src hợp lệ, badge play_arrow / footer play_circle, hotbar nút 3 chấm
    4. Kích hoạt menu chuột phải (<flow-video-context-menu-items>) hoặc nút 3 chấm để tải video
    """
    prompt_keywords = []
    if prompt_text:
        raw_words = re.findall(r"\b[a-zA-Z0-9_-]{4,}\b", prompt_text)
        stop_words = {"cinematic", "commercial", "shot", "ultra", "realistic", "high", "quality", "with", "from", "video"}
        prompt_keywords = [w for w in raw_words if w.lower() not in stop_words][:6]

    card_selector = detect_video_card_selector(page, timeout_sec=20)
    print(f"Bắt đầu theo dõi video card ({card_selector}). Từ khóa prompt: {prompt_keywords}")

    target_index = card_index
    locked_index = None
    last_probe_attempt = -100

    for attempt in range(240):
        time.sleep(1)

        eval_data = {
            "cardSelector": card_selector,
            "targetIndex": target_index if locked_index is None else locked_index,
            "promptKeywords": prompt_keywords
        }

        debug_info = page.evaluate(
            r"""
            (args) => {
                const selector = args.cardSelector;
                const targetIdx = args.targetIndex;
                const keywords = args.promptKeywords || [];

                // 1. Tìm tất cả các thẻ video trên trang
                let cards = Array.from(document.querySelectorAll(selector));
                if (cards.length === 0) {
                    cards = Array.from(document.querySelectorAll('flow-video-tile'));
                }
                if (cards.length === 0) {
                    cards = Array.from(document.querySelectorAll('flow-grid-tile-container')).filter(c => {
                        return c.querySelector('flow-video-tile, .mobile-play-badge, flow-video-hotbar, video, img.thumbnail');
                    });
                }

                if (cards.length === 0) {
                    return {
                        ready: false,
                        reason: 'no_cards_found',
                        total_cards: 0
                    };
                }

                // 2. Xác định đúng thẻ card đang tạo / cần lấy:
                let targetCard = null;
                let finalIdx = -1;

                // A. Ưu tiên card đang có thanh tiến trình (đang generate)
                for (let i = 0; i < cards.length; i++) {
                    const c = cards[i];
                    const hasProgressBar = Boolean(c.querySelector('.progress-bar, mat-progress-bar, [class*="progress-bar"]'));
                    const hasProgressClass = Boolean(c.querySelector('.hover-overlay-has-progress-bar, .footer-overlay-has-progress-bar'));
                    if (hasProgressBar || hasProgressClass) {
                        targetCard = c;
                        finalIdx = i;
                        break;
                    }
                }

                // B. Nếu không có card nào đang render dở, tìm theo từ khóa prompt
                if (!targetCard && keywords.length > 0) {
                    for (let i = 0; i < cards.length; i++) {
                        const c = cards[i];
                        const titleEl = c.querySelector('.footer-title, [class*="footer-title"]');
                        const labelText = ((c.getAttribute('aria-label') || '') + ' ' + (titleEl ? titleEl.innerText : '')).toLowerCase();
                        const matches = keywords.filter(k => labelText.includes(k.toLowerCase())).length;
                        if (matches >= 2 || (keywords.length === 1 && matches === 1)) {
                            targetCard = c;
                            finalIdx = i;
                            break;
                        }
                    }
                }

                // C. Nếu không khớp từ khóa, lấy theo targetIdx (mặc định 0 - mới nhất)
                if (!targetCard) {
                    let idx = targetIdx;
                    if (idx < 0 || idx >= cards.length) {
                        idx = 0;
                    }
                    targetCard = cards[idx];
                    finalIdx = idx;
                }

                if (!targetCard) {
                    return {
                        ready: false,
                        reason: 'card_not_resolved',
                        total_cards: cards.length
                    };
                }

                // 3. Kiểm tra thông báo lỗi sinh video
                const cardText = (targetCard.innerText || '').toLowerCase();
                if (cardText.includes('failed to generate') || cardText.includes('không thể tạo') || cardText.includes('generation error') || cardText.includes('thử lại sau')) {
                    return {
                        ready: false,
                        reason: 'generation_failed',
                        card_text: cardText.slice(0, 150),
                        card_index: finalIdx,
                        total_cards: cards.length
                    };
                }

                // 4. Kiểm tra tiến trình render
                const progressBar = targetCard.querySelector('.progress-bar, mat-progress-bar, [class*="progress-bar"]');
                const hasProgressClass = Boolean(targetCard.querySelector('.hover-overlay-has-progress-bar, .footer-overlay-has-progress-bar'));

                let progressPercent = null;
                if (progressBar) {
                    const style = progressBar.getAttribute('style') || '';
                    const match = style.match(/--progress-percent:\s*([\d.]+)%/);
                    if (match) {
                        progressPercent = parseFloat(match[1]);
                    }
                }

                let isGenerating = false;
                if (progressBar) {
                    if (progressPercent !== null) {
                        isGenerating = progressPercent < 99.0;
                    } else {
                        isGenerating = true;
                    }
                } else if (hasProgressClass) {
                    isGenerating = true;
                }

                // 5. Kiểm tra tài nguyên media & các thành phần UI hoàn tất
                const video = targetCard.querySelector('video');
                const videoSrc = video ? (video.getAttribute('src') || video.currentSrc || '') : '';
                const hasValidVideoSrc = Boolean(videoSrc && /^(https?:|blob:)/i.test(videoSrc));

                const thumb = targetCard.querySelector('img.thumbnail, img');
                const thumbSrc = thumb ? (thumb.currentSrc || thumb.getAttribute('src') || '') : '';
                const hasValidThumb = Boolean(thumbSrc && /^(https?:|blob:)/i.test(thumbSrc) && !thumbSrc.includes('placeholder'));

                // Play badge / Play icon
                const playBadge = targetCard.querySelector('.mobile-play-badge, mat-icon:not(.fill):not(.flow-icon-m), mat-icon');
                const playIconText = playBadge ? (playBadge.innerText || '').trim() : '';
                const hasPlayIcon = Boolean(playIconText === 'play_arrow' || playIconText === 'play_circle' || targetCard.querySelector('.mobile-play-badge'));

                // Hotbar nút 3 chấm / Tùy chọn khác
                const hotbar = targetCard.querySelector('flow-video-hotbar, .hotbar-container, button[aria-label="More options"], button[aria-label="Tuỳ chọn khác"], button[aria-label="Favorite"]');

                // Video được coi là READY khi:
                // - Không còn đang sinh (isGenerating = false)
                // - Đã có ảnh thumbnail hoặc video src hợp lệ
                // - Đã xuất hiện icon Play (play_arrow / play_circle) hoặc hotbar menu
                const ready = (!isGenerating) && (hasValidVideoSrc || hasValidThumb) && (hasPlayIcon || Boolean(hotbar));

                return {
                    ready: ready,
                    reason: ready ? 'ready' : (isGenerating ? 'generating' : 'waiting_media_ready'),
                    card_index: finalIdx,
                    progress: progressPercent,
                    has_progress_bar: Boolean(progressBar),
                    has_progress_class: hasProgressClass,
                    video_src_prefix: videoSrc.slice(0, 80),
                    thumb_src_prefix: thumbSrc.slice(0, 80),
                    has_play_icon: hasPlayIcon,
                    has_hotbar: Boolean(hotbar),
                    total_cards: cards.length
                };
            }
            """,
            eval_data
        )

        resolved_idx = debug_info.get("card_index")
        if resolved_idx is not None and locked_index is None:
            locked_index = resolved_idx

        if debug_info.get("reason") == "generation_failed":
            page.screenshot(path="debug_video_generation_failed.png", full_page=True)
            raise Exception(f"Video generation failed: {debug_info.get('card_text')}")

        # ── READY = chuột phải vào video và menu hiện mục 'Download' bấm được ──
        # Chỉ chuột phải khi DOM đã báo ready (hết progress bar + có thumbnail + play/hotbar).
        # Nếu DOM chưa báo ready thì KHÔNG chuột phải liên tục (card đang generating chỉ có
        # menu Delete). Chỉ thăm dò nhẹ (1 lần chuột phải, không fallback) mỗi 20 giây sau 60 giây
        # đầu, phòng khi heuristic DOM bị sai.
        reason = debug_info.get("reason")
        dom_ready = bool(debug_info.get("ready", False))
        if dom_ready:
            should_probe = (attempt - last_probe_attempt) >= 4
            full_fb = True
        else:
            should_probe = (
                reason == "waiting_media_ready"
                and attempt >= 60
                and (attempt - last_probe_attempt) >= 20
            )
            full_fb = False

        if should_probe:
            last_probe_attempt = attempt
            probe_loc = get_video_card_locator(
                page, card_selector,
                locked_index if locked_index is not None else target_index
            )
            if probe_loc is not None:
                menu_download_item = open_video_context_menu(
                    page, probe_loc, card_selector,
                    locked_index if locked_index is not None else target_index,
                    full_fallback=full_fb
                )
                if menu_download_item is not None:
                    print(
                        f"✅ Video card {locked_index} ĐÃ HOÀN TẤT (menu chuột phải có 'Download') | "
                        f"dom_ready={dom_ready} | thumb_src={debug_info.get('thumb_src_prefix', '')!r}"
                    )
                    break
                print(
                    f"  [Check Video {attempt + 1}/240] Menu chưa có 'Download' "
                    f"(dom_ready={dom_ready}, reason={reason}) -> đợi thêm"
                )

        progress_str = f"{debug_info.get('progress'):.1f}%" if debug_info.get("progress") is not None else "N/A"
        print(
            f"  [Check Video {attempt + 1}/240] status={debug_info.get('reason')} | "
            f"progress={progress_str} | card_idx={locked_index} | total_cards={debug_info.get('total_cards')}"
        )
    else:
        page.screenshot(path="debug_video_card_timeout.png", full_page=True)
        raise Exception(f"Hết thời gian chờ video render (timeout 240s). Đã lưu debug_video_card_timeout.png")

    time.sleep(1)
    target_idx = locked_index if locked_index is not None else 0

    # Lấy locator card đã hoàn tất
    card_loc = page.locator(card_selector).nth(target_idx)
    if card_loc.count() == 0:
        card_loc = page.locator("flow-video-tile").nth(target_idx)
    card_loc.scroll_into_view_if_needed()
    time.sleep(0.5)

    # Thử lấy link video trực tiếp từ thẻ video nếu có
    video_src = ""
    try:
        v_elem = card_loc.locator("video").first
        if v_elem.count() > 0:
            video_src = v_elem.get_attribute("src") or ""
    except Exception:
        pass

    download_success = False

    # ─────────────────────────────────────────────
    # PHƯƠNG ÁN 1: Tải trực tiếp siêu tốc từ CDN nếu có thẻ <video src="...">
    # ─────────────────────────────────────────────
    if video_src and re.match(r"^https?://", video_src, re.IGNORECASE):
        print(f"🚀 Tải trực tiếp video từ CDN Google Flow: {video_src[:80]}...")
        try:
            import urllib.request
            req = urllib.request.Request(
                video_src,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://flow.google.com/"
                }
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                if resp.status == 200:
                    with open(save_path, "wb") as f:
                        while True:
                            chunk = resp.read(64 * 1024)
                            if not chunk:
                                break
                            f.write(chunk)

                    if os.path.exists(save_path) and os.path.getsize(save_path) > 10000:
                        file_mb = os.path.getsize(save_path) / (1024 * 1024)
                        print(f"✅ Tải video thành công từ CDN: {save_path} ({file_mb:.2f} MB)")
                        download_success = True
        except Exception as cdn_err:
            print(f"Tải qua CDN không thành công: {cdn_err}, chuyển sang Menu UI...")

    # ─────────────────────────────────────────────
    # PHƯƠNG ÁN 2: Nhấn CHUỘT PHẢI vào Video Card để mở Menu -> Click Tải xuống
    # ─────────────────────────────────────────────
    if not download_success:
        print(f"🖱️ Đang mở menu chuột phải của video card (index {target_idx}) để tải...")
        try:
            # Nếu menu từ bước check READY vẫn đang mở thì dùng luôn, không thì mở lại
            download_item = find_download_menu_item(page)
            if download_item is None:
                download_item = open_video_context_menu(page, card_loc, card_selector, target_idx)
            if download_item is None:
                page.screenshot(path="debug_video_menu_not_open.png", full_page=True)
                raise Exception("Không mở được menu chuột phải / 3 chấm có mục Download (đã lưu debug_video_menu_not_open.png)")

            download_item.wait_for(state="visible", timeout=8000)
            print("Đã thấy mục 'Download' trong Context Menu, bắt đầu xử lý tải...")

            # 6. Nút Download là một Submenu trigger (chứa svg mũi tên). Hover hoặc click để mở submenu độ phân giải
            try:
                download_item.hover(force=True)
                time.sleep(0.3)
            except Exception:
                pass

            try:
                # Thử kích hoạt download trực tiếp nếu click download tải ngay
                with page.expect_download(timeout=5000) as quick_dl:
                    download_item.click(force=True)
                download = quick_dl.value
                download.save_as(save_path)
                download_success = True
                print("✅ Đã tải video ngay sau khi click Download")
            except Exception:
                # Nếu mở Submenu độ phân giải (720p / 1080p / Original), click vào tùy chọn độ phân giải
                print("Submenu độ phân giải xuất hiện, click chọn độ phân giải...")
                with page.expect_download(timeout=180000) as full_dl:
                    # Submenu là panel menu MỚI NHẤT (panel cuối cùng), không phải mục 'Download' cha
                    res_item = page.locator(
                        ".mat-mdc-menu-panel button[mat-menu-item]"
                    ).filter(
                        has_text=re.compile(r"(\b720p\b|\b1080p\b|\b4K\b|Original|Gốc)", re.IGNORECASE)
                    ).first
                    if res_item.count() == 0:
                        res_item = page.locator(".mat-mdc-menu-panel").last.locator("button[mat-menu-item]").first
                    res_item.wait_for(state="visible", timeout=8000)
                    res_item.click(force=True)

                download = full_dl.value
                download.save_as(save_path)
                download_success = True

            if os.path.exists(save_path) and os.path.getsize(save_path) > 10000:
                file_mb = os.path.getsize(save_path) / (1024 * 1024)
                print(f"✅ Tải video thành công qua Menu chuột phải: {save_path} ({file_mb:.2f} MB)")
        except Exception as ui_err:
            print(f"Tải qua Menu chuột phải thất bại: {ui_err}")

    # ─────────────────────────────────────────────
    # PHƯƠNG ÁN 3 (Dự phòng tối thượng): Click mở Modal Player để lấy link <video> phát thật
    # ─────────────────────────────────────────────
    if not download_success:
        print("🔄 Thử phương án dự phòng 3: Mở modal player để trích xuất link video...")
        try:
            # Nhấn vào giữa thẻ video card để mở popup player
            card_loc.click(force=True)
            time.sleep(2)

            modal_video_src = page.evaluate(
                """
                () => {
                    const video = document.querySelector('video[src], video source[src]');
                    if (video) {
                        return video.getAttribute('src') || video.currentSrc || '';
                    }
                    return '';
                }
                """
            )

            if modal_video_src and modal_video_src.startswith("http"):
                print(f"Tìm thấy link video từ Modal Player: {modal_video_src[:80]}...")
                import urllib.request
                req = urllib.request.Request(
                    modal_video_src,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Referer": "https://flow.google.com/"
                    }
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    if resp.status == 200:
                        with open(save_path, "wb") as f:
                            while True:
                                chunk = resp.read(64 * 1024)
                                if not chunk:
                                    break
                                f.write(chunk)
                        if os.path.exists(save_path) and os.path.getsize(save_path) > 10000:
                            download_success = True
                            print(f"✅ Tải video thành công từ Modal Player: {save_path}")

            # Đóng modal player bằng phím Escape
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        except Exception as modal_err:
            print(f"Phương án Modal Player thất bại: {modal_err}")

    if not download_success:
        page.screenshot(path="debug_video_download_failed.png", full_page=True)
        raise Exception(f"Không thể tải video từ card {target_idx} qua bất kỳ phương thức nào.")

    print(f"🎉 Hoàn thành lưu video: {save_path}")


# ─────────────────────────────────────────────
# Setup: new project + settings
# ─────────────────────────────────────────────

def dismiss_possible_ad_overlay(page):
    """Đóng menu quảng cáo/overlay trước khi kiểm tra tài khoản."""
    try:
        print("Trying close popup...")

        # Click vùng giữa phía trên trang,
        # tránh thanh menu bên trái.
        human_click_xy(page, 1880, 500, name="Popup clear area")
        time.sleep(2)

        print("Popup area cleared")

    except Exception as e:
        print("Popup clear skipped:", e)


def setup_new_project(page):
    # GIỮ NGUYÊN TOÀN BỘ SELECTOR INSPECT

    # ============================================================
    # CLICK NEW PROJECT BUTTON
    # ============================================================
    def try_click_button(button, name, max_backdrop_attempts=3):
        """
        Thử click 1 button, xử lý đúng trường hợp bị cdk-overlay-backdrop
        (trong suốt) che - phải ĐÓNG overlay TRƯỚC, đợi nó biến mất khỏi
        DOM, rồi mới click lại vào nút thật. Không coi click vào backdrop
        là đã xong việc (đây là bug của bản cũ).
        """
        page = button.page

        for attempt in range(max_backdrop_attempts):
            box = button.bounding_box()
            if not box:
                print(f"{name}: bounding_box() None, bỏ qua")
                return False

            print(f"{name} size: {box['width']}x{box['height']}")

            center_x = box["x"] + box["width"] / 2
            center_y = box["y"] + box["height"] / 2

            hit_info = page.evaluate(
                """([x, y]) => {
                    const el = document.elementFromPoint(x, y);
                    return el ? { tag: el.tagName, class: el.className } : null;
                }""",
                [center_x, center_y]
            )
            print(f"{name} (attempt {attempt+1}): element tại điểm click = {hit_info}")

            is_backdrop = (
                hit_info is not None
                and "cdk-overlay-backdrop" in (hit_info.get("class") or "")
            )

            if is_backdrop:
                print(f"{name}: bị che bởi overlay backdrop, đóng overlay trước")
                page.keyboard.press("Escape")
                try:
                    page.wait_for_selector(
                        ".cdk-overlay-backdrop-showing",
                        state="detached",
                        timeout=2000
                    )
                    print(f"{name}: overlay đã biến mất")
                except Exception:
                    human_click_xy(page, center_x, center_y, name=f"{name} overlay backdrop")
                    try:
                        page.wait_for_selector(
                            ".cdk-overlay-backdrop-showing",
                            state="detached",
                            timeout=2000
                        )
                        print(f"{name}: overlay đã biến mất sau khi click backdrop")
                    except Exception:
                        print(f"{name}: overlay vẫn còn sau khi thử đóng, thử lại vòng lặp")
                # CHƯA coi là đã click nút thật - quay lại đầu vòng lặp kiểm tra tiếp
                continue

            is_covered_by_other = (
                hit_info is not None
                and "new-project-button" not in (hit_info.get("class") or "")
                and hit_info["tag"] not in ("MAT-ICON", "SPAN", "BUTTON", "FONT")
            )

            if is_covered_by_other:
                print(f"{name}: bị che bởi phần tử khác (không phải overlay backdrop) - {hit_info}")
                human_click_xy(page, center_x, center_y, name=f"{name} covered button")
                return True

            # Không còn gì che -> đưa chuột tới nút rồi click thật
            try:
                human_click(
                    page,
                    button,
                    name=name,
                    timeout=2000
                )
                print(f"{name}: click thật OK (mouse move -> click)")
                return True
            except Exception as e:
                print(f"{name}: human click fail - {e}")
                return False

        print(f"{name}: hết số lần thử, overlay vẫn còn che nút")
        return False

    def click_toggle_and_verify(
        locator,
        name,
        max_attempts=3
    ):
        """
        Bấm 1 mat-button-toggle và XÁC NHẬN aria-checked
        thật sự đổi thành "true" sau khi bấm.

        Trước đây chỉ nút Video được kiểm tra aria-checked,
        các nút còn lại (Frames, 9:16, 720p, x1, 8s...) bấm
        "mù" bằng click(force=True) rồi coi như xong - nếu
        đúng lúc đó overlay/animation còn che nút, cú click
        không có tác dụng gì mà code không hề biết.

        Hàm này dùng lại try_click_button (đã xử lý tốt case
        bị cdk-overlay-backdrop che) để bấm, sau đó đọc lại
        aria-checked để xác nhận, và thử lại nếu chưa đổi.
        """

        button = locator.first

        button.wait_for(
            state="visible",
            timeout=15000
        )

        def is_btn_checked(btn):
            try:
                if btn.get_attribute("aria-checked") == "true":
                    return True
                parent_checked = btn.evaluate(
                    """(el) => {
                        const toggle = el.closest('mat-button-toggle');
                        return Boolean(
                            toggle && (
                                toggle.classList.contains('mat-button-toggle-checked')
                                || toggle.getAttribute('aria-checked') === 'true'
                            )
                        );
                    }"""
                )
                if parent_checked:
                    return True
            except Exception:
                pass
            return False

        for attempt in range(1, max_attempts + 1):
            if is_btn_checked(button):
                print(
                    f"{name}: already selected, skip click"
                )
                return True

            try_click_button(
                button,
                name
            )

            page.wait_for_timeout(350)

            if is_btn_checked(button):
                print(
                    f"{name}: selected OK "
                    f"(attempt {attempt})"
                )
                return True

            # Nếu thử lần 2 trở đi mà chưa đổi trạng thái, thử click trực tiếp qua DOM
            if attempt >= 2:
                try:
                    button.click(force=True, timeout=2000)
                    page.wait_for_timeout(300)
                    if is_btn_checked(button):
                        print(f"{name}: selected OK via force click (attempt {attempt})")
                        return True
                except Exception:
                    pass

            print(
                f"{name}: click chưa đổi trạng thái, "
                f"thử lại ({attempt}/{max_attempts})"
            )

        try:
            safe_name = (
                name.lower()
                .replace(" ", "_")
            )

            page.screenshot(
                path=(
                    f"debug_toggle_{safe_name}"
                    f"_not_selected.png"
                ),
                full_page=True
            )

        except Exception:
            pass

        raise Exception(
            f"Cannot select {name} after "
            f"{max_attempts} attempts"
        )

    new_project_clicked = False

    new_project_selectors = [
        (
            "button:has(mat-icon:text('add'))",
            "add icon button"
        ),
        (
            "button.mat-mdc-fab",
            "mat fab button"
        ),
        (
            "button[mat-fab]",
            "mat-fab attribute button"
        ),
    ]

    for selector, name in new_project_selectors:

        try:
            buttons = page.locator(selector)
            count = buttons.count()

            print(f"Checking {name}: {count} buttons")

            for i in range(count):
                button = buttons.nth(i)

                if button.is_visible():
                    if try_click_button(button, name):
                        print(f"Clicked New Project using {name}")
                        new_project_clicked = True
                        break

            if new_project_clicked:
                break

        except Exception as e:
            print(f"Failed {name}: {e}")
            continue

    if not new_project_clicked:
        raise Exception("Cannot find New Project button")

    human_delay(0.35, 0.70)

    # VIDEO SETTING BUTTON
    # KHÔNG dùng aria-label vì nó đổi theo ngôn ngữ
    # tài khoản của từng profile: "Settings trigger"
    # (EN) hoặc "Điều kiện kích hoạt cài đặt" (VI).
    # Đây là lý do có profile bấm được, có profile
    # không - class settings-trigger-button không đổi
    # theo ngôn ngữ nên dùng ổn định cho mọi profile.
    settings_button = page.locator(
        "button.settings-trigger-button"
    ).first

    if settings_button.count() == 0:
        # fallback phòng khi class cũng đổi,
        # thử theo cả 2 ngôn ngữ.
        settings_button = page.locator(
            '[aria-label="Settings trigger"], '
            '[aria-label="Điều kiện kích hoạt cài đặt"]'
        ).first

    if not try_click_button(settings_button, "video setting button"):
        raise Exception("Cannot click video setting button")

    print("Clicked video setting button")

    human_delay(0.35, 0.70)
    # Nút Video hiện tại có:
    # role="tab"
    # aria-controls="...content-VIDEO"
    # data-state="active"
    #
    # Không dùng radix id vì phần giữa của id thay đổi
    # sau mỗi session.
    video_tab = page.locator(
        "button.mat-button-toggle-button"
    ).filter(
        has=page.locator(
            "mat-icon:text('videocam')"
        )
    )

    click_toggle_and_verify(
        video_tab,
        "Video tab"
    )

    # Xác nhận tab đã chuyển sang active.
    try:
        page.wait_for_function(
            """
            () => {
                const tab = document.querySelector(
                    "button[role='tab']"
                    + "[aria-controls$='content-VIDEO']"
                );

                return Boolean(
                    tab
                    && (
                        tab.getAttribute(
                            "aria-selected"
                        ) === "true"
                        || tab.getAttribute(
                            "data-state"
                        ) === "active"
                    )
                );
            }
            """,
            timeout=10000
        )
    except Exception:
        # Không phải mọi phiên bản UI đều có
        # role="tab" này - bỏ qua nếu không tìm thấy,
        # đã verify bằng aria-checked ở trên rồi.
        pass

    human_delay(0.55, 1.05)

    frames_tab = page.locator(
        "button.mat-button-toggle-button"
    ).filter(
        has=page.locator(
            "mat-icon:text('crop_free')"
        )
    )

    click_toggle_and_verify(
        frames_tab,
        "Frames tab"
    )

    human_delay(0.20, 0.45)

    ratio_9_16 = page.locator(
        "button.mat-button-toggle-button"
    ).filter(
        has=page.locator(
            "mat-icon:text('crop_9_16')"
        )
    )

    click_toggle_and_verify(
        ratio_9_16,
        "9:16 ratio"
    )

    human_delay(0.20, 0.45)

    # KHÔNG dùng aria-label vì đổi theo ngôn ngữ
    # tài khoản của từng profile: "Select model family"
    # (EN) hoặc "Chọn nhóm mô hình" (VI) - đây là lý do
    # có profile bấm được, có profile không. Dùng class
    # model-select-trigger-content (không đổi theo
    # ngôn ngữ) để chạy ổn định cho mọi profile.
    model_trigger = page.locator(
        "button:has(span.model-select-trigger-content)"
    ).first

    if model_trigger.count() == 0:
        # fallback phòng khi class cũng đổi,
        # thử theo cả 2 ngôn ngữ.
        model_trigger = page.locator(
            '[aria-label="Select model family"], '
            '[aria-label="Chọn nhóm mô hình"]'
        ).first

    try_click_button(
        model_trigger,
        "model dropdown trigger"
    )

    print(
        "Opened model dropdown"
    )

    human_delay(0.20, 0.45)

    omni_flash_item = page.locator(
        "button[mat-menu-item]"
    ).filter(
        has_text="Omni 1.1 Flash"
    ).first

    omni_flash_item.wait_for(
        state="visible",
        timeout=10000
    )

    try_click_button(
        omni_flash_item,
        "Omni 1.1 Flash menu item"
    )

    # Xác nhận đã chọn: menu item cha (flow-menu-item)
    # có class "selected", hoặc trigger đã đổi text.
    try:
        page.wait_for_function(
            """
            () => {
                const trigger = document.querySelector(
                    "span.model-select-trigger-content"
                );

                return Boolean(
                    trigger
                    && trigger.textContent.includes(
                        "Omni 1.1 Flash"
                    )
                );
            }
            """,
            timeout=5000
        )

        print(
            "Selected Omni 1.1 Flash (verified)"
        )

    except Exception:
        print(
            "Selected Omni 1.1 Flash "
            "(could not verify trigger text, "
            "continuing anyway)"
        )

    human_delay(0.20, 0.45)

    # ============================================================
    # RESOLUTION 720P
    # ============================================================
    # Flow UI mới có thể hiển thị 720p dưới dạng mat-menu-item:
    #
    # <button mat-menu-item ...>
    #   <span class="item-text">
    #     <span class="label">720p</span>
    #     <span class="caption">Original size</span>
    #   </span>
    # </button>
    #
    # Ưu tiên selector theo đúng cấu trúc này. Nếu profile/UI cũ
    # vẫn dùng mat-button-toggle thì fallback về selector cũ.

    resolution_720p_menu = page.locator(
        "button[mat-menu-item]"
    ).filter(
        has=page.locator(
            "span.label"
        ).filter(
            has_text=re.compile(r"^\s*720p\s*$")
        )
    ).first

    if (
        resolution_720p_menu.count() > 0
        and resolution_720p_menu.is_visible()
    ):
        print(
            "720p resolution found as mat-menu-item, clicking..."
        )

        human_click(
            page,
            resolution_720p_menu,
            name="720p resolution menu item",
            timeout=10000
        )

        page.wait_for_timeout(250)

        print(
            "720p resolution selected through mat-menu-item."
        )

    else:
        print(
            "720p mat-menu-item not visible. "
            "Trying legacy mat-button-toggle selector..."
        )

        resolution_720p_toggle = page.locator(
            "button.mat-button-toggle-button"
        ).filter(
            has_text=re.compile(r"^\s*720p\s*$")
        ).first

        click_toggle_and_verify(
            resolution_720p_toggle,
            "720p resolution"
        )

    human_delay(0.20, 0.45)

    # ============================================================
    # THỜI LƯỢNG 10s: Hỗ trợ tiếng Việt ("10 giây") và tiếng Anh ("10s")
    # ============================================================
    duration_10s = page.locator(
        "mat-button-toggle button.mat-button-toggle-button, "
        "button.mat-button-toggle-button"
    ).filter(
        has_text=re.compile(r"^\s*10\s*(s|giây|sec|seconds)?\s*$", re.IGNORECASE)
    ).first

    if duration_10s.count() == 0:
        duration_10s = page.locator("mat-button-toggle").filter(
            has_text=re.compile(r"^\s*10\s*(s|giây|sec|seconds)?\s*$", re.IGNORECASE)
        ).locator("button").first

    if duration_10s.count() > 0:
        click_toggle_and_verify(
            duration_10s,
            "10s duration"
        )
        human_delay(0.20, 0.45)
    else:
        print("Warning: 10s duration button not found")

    # ============================================================
    # SỐ LƯỢNG CLIP / TỐC ĐỘ: x1
    # ============================================================
    speed_x1 = page.locator(
        "mat-button-toggle button.mat-button-toggle-button, "
        "button.mat-button-toggle-button"
    ).filter(
        has_text=re.compile(r"^\s*x1\s*$", re.IGNORECASE)
    ).first

    if speed_x1.count() == 0:
        speed_x1 = page.locator("mat-button-toggle").filter(
            has_text=re.compile(r"^\s*x1\s*$", re.IGNORECASE)
        ).locator("button").first

    if speed_x1.count() > 0:
        click_toggle_and_verify(
            speed_x1,
            "x1 speed"
        )
        human_delay(0.20, 0.45)
    else:
        print("Warning: x1 speed button not found")


# ─────────────────────────────────────────────
# Upload ảnh của một clip
# ─────────────────────────────────────────────

def upload_clip_images(
    page,
    category,
    product_id,
    clip_num,
    start_image,
    end_image
):
    """
    Upload ảnh vào Google Flow.

    Tên ảnh thực tế luôn được đọc từ render_queue.csv.

    Pipeline hiện tại:

    Snack:
        clip 1: 01_hand_holding.png (upload 1 ảnh dùng cho cả start và end)

    Móc khóa:
        clip 2: 03_hand_holding + 04_hand_holding_next_frame

    Ốp lưng:
        clip 1: 01_clip_01_first_frame + 02_clip_01_last_frame

    Mắt kính:
        clip 1: 01_hand_holding + 02_closeup
    """

    ai_dir = os.path.dirname(
        os.path.abspath(
            start_image
        )
    )

    end_image_dir = os.path.dirname(
        os.path.abspath(
            end_image
        )
    )

    if ai_dir != end_image_dir:
        raise Exception(
            f"start_image và end_image không "
            f"cùng thư mục channel: "
            f"{ai_dir} != {end_image_dir}"
        )

    start_image_name = os.path.basename(
        start_image
    )

    end_image_name = os.path.basename(
        end_image
    )

    # Loại bỏ trùng lặp nếu start_image == end_image (như snack)
    unique_names = list(dict.fromkeys([start_image_name, end_image_name]))

    for image_path in (
        start_image,
        end_image
    ):
        if not os.path.exists(
            image_path
        ):
            raise FileNotFoundError(
                f"Missing AI image: {image_path}"
            )

    # FLOW UI MỚI:
    # + button -> Upload

    upload_opened = False

    upload_selectors = [
        (
            "button[aria-label='Add media menu']",
            "add media button"
        ),
        (
            "button:has(mat-icon:text('add'))",
            "plus icon button"
        ),
    ]

    for selector, name in upload_selectors:
        try:
            btn = page.locator(selector).first

            if btn.count() > 0 and btn.is_visible():
                human_click(
                    page,
                    btn,
                    name=name,
                    timeout=3000
                )

                print(
                    f"Clicked {name}"
                )

                upload_opened = True
                break

        except Exception:
            continue

    if not upload_opened:
        raise Exception(
            "Cannot open upload menu"
        )

    human_delay(0.35, 0.70)

    # Chọn Upload trong menu
    upload_item = page.locator(
        "button[mat-menu-item]"
    ).filter(
        has=page.locator(
            "mat-icon:text('upload')"
        )
    ).first

    human_click(
        page,
        upload_item,
        name="Upload menu item"
    )

    print(
        f"Clicked Upload menu "
        f"(clip {clip_num})"
    )

    human_delay(0.35, 0.70)

    file_names_text = " ".join([
        f'"{name}"'
        for name in unique_names
    ])

    # GIỮ NGUYÊN THỨ TỰ THAO TÁC HỘP THOẠI WINDOWS
    pyperclip.copy(
        ai_dir
    )

    pyautogui.hotkey(
        "ctrl",
        "l"
    )

    time.sleep(0.25)

    pyautogui.hotkey(
        "ctrl",
        "v"
    )

    time.sleep(0.25)

    pyautogui.press(
        "enter"
    )

    human_delay(0.35, 0.70)

    pyperclip.copy(
        file_names_text
    )

    pyautogui.hotkey(
        "alt",
        "n"
    )

    time.sleep(0.25)

    pyautogui.hotkey(
        "ctrl",
        "v"
    )

    time.sleep(0.25)

    pyautogui.press(
        "enter"
    )

    human_delay(0.40, 0.80)

    print(
        f"Uploaded {len(unique_names)} image(s) for clip "
        f"{clip_num}: {unique_names}"
    )

    human_delay(0.40, 0.80)


# ─────────────────────────────────────────────
# Tạo 1 clip
# ─────────────────────────────────────────────

def create_clip(
    page,
    category,
    product_id,
    clip_num,
    start_image,
    end_image,
    prompt_text
):
    print(
        f"\n--- Creating Clip "
        f"{clip_num} ---"
    )

    start_image_name = os.path.basename(
        start_image
    )

    end_image_name = os.path.basename(
        end_image
    )

    unique_names = list(dict.fromkeys([start_image_name, end_image_name]))
    expected_image_count = len(unique_names)

    # FLOW UI MỚI:
    # Phải mở Add media -> Upload trước
    # rồi mới bấm Start.
    upload_clip_images(
        page=page,
        category=category,
        product_id=product_id,
        clip_num=clip_num,
        start_image=start_image,
        end_image=end_image
    )

    # KHÔNG chỉ khớp "Start" vì có thể hiển thị
    # "Bắt đầu" ở profile để ngôn ngữ tài khoản
    # là tiếng Việt - cùng lỗi như settings-trigger-button
    # và model-select trước đó.
    start_button = page.locator(
        "button.empty-chip"
    ).filter(
        has_text=re.compile(
            r"^\s*(Start|Bắt đầu)\s*$"
        )
    ).first

    human_click(
        page,
        start_button,
        name="Start button"
    )

    print(
        "Clicked Bắt đầu"
    )

    human_delay(0.35, 0.70)

    # Panel Bắt đầu vừa mở ra, ảnh vừa upload
    # cần thời gian để hiện thành card chọn được.
    # Card CHỈ xuất hiện sau khi bấm Start,
    # không phải ngay sau khi upload xong.
    wait_image_cards_stable(
        page,
        expected_count=expected_image_count
    )

    click_image_card(
        page,
        start_image_name
    )

    print(
        f"Selected start image: "
        f"{start_image_name}"
    )

    human_delay(0.35, 0.70)

    # Click "Add to prompt"
    # trong panel Bắt đầu.
    try:
        btn_them = page.locator(
            "button.detail-add-to-prompt-btn"
        ).first

        if btn_them.count() == 0:
            btn_them = page.locator(
                "button"
            ).filter(
                has_text="Add to prompt"
            ).first

        if (
            btn_them.count() > 0
            and btn_them.is_visible()
        ):
            human_click(
                page,
                btn_them,
                name="Add start image to prompt"
            )

            print(
                "Added start image to prompt"
            )

        else:
            print(
                "Skip start Add to Prompt "
                "(not found)"
            )

    except:
        print(
            "Skip start Add to Prompt "
            "(error)"
        )

    # Đóng panel Bắt đầu,
    # mở panel Kết thúc.
    # KHÔNG chỉ khớp "End" vì có thể hiển thị
    # "Kết thúc" ở profile để ngôn ngữ tài khoản
    # là tiếng Việt.
    end_button = page.locator(
        "button.empty-chip"
    ).filter(
        has_text=re.compile(
            r"^\s*(End|Kết thúc)\s*$"
        )
    ).first

    human_click(
        page,
        end_button,
        name="End button"
    )

    print(
        "Clicked Kết thúc"
    )

    human_delay(0.35, 0.70)

    # Tương tự panel Start, panel End cũng cần
    # chờ card ảnh hiện ra sau khi bấm mới chọn được.
    wait_image_cards_stable(
        page,
        expected_count=expected_image_count
    )

    click_image_card(
        page,
        end_image_name
    )

    print(
        f"Selected end image: "
        f"{end_image_name}"
    )

    human_delay(0.35, 0.70)

    # Click "Add to prompt"
    # trong panel Kết thúc.
    try:
        btn_them2 = page.locator(
            "button.detail-add-to-prompt-btn"
        ).first

        if btn_them2.count() == 0:
            btn_them2 = page.locator(
                "button"
            ).filter(
                has_text="Add to prompt"
            ).first

        if (
            btn_them2.count() > 0
            and btn_them2.is_visible()
        ):
            human_click(
                page,
                btn_them2,
                name="Add end image to prompt"
            )

            print(
                "Added end image to prompt"
            )

        else:
            print(
                "Skip end Add to Prompt "
                "(not found)"
            )

    except:
        print(
            "Skip end Add to Prompt "
            "(error)"
        )

    # GIỮ NGUYÊN SELECTOR INSPECT
    # Chỉ lấy ProseMirror đang thực sự hiển thị,
    # tránh trường hợp trang có nhiều flow-rich-text-editor
    # ẩn khác khiến .first chọn nhầm ô không hiển thị.
    prompt_box_candidates = page.locator(
        "flow-rich-text-editor.prompt-input "
        "div.ProseMirror[contenteditable='true']"
    )

    prompt_box = None

    for i in range(prompt_box_candidates.count()):
        candidate = prompt_box_candidates.nth(i)

        if candidate.is_visible():
            prompt_box = candidate
            break

    if prompt_box is None:
        page.screenshot(
            path="debug_prompt_box_not_found.png",
            full_page=True
        )

        raise Exception(
            "Prompt box (ProseMirror) not found "
            "or not visible. Saved "
            "debug_prompt_box_not_found.png"
        )

    human_click(
        page,
        prompt_box,
        name="Prompt box"
    )

    time.sleep(0.3)

    # Click lần 2 để chắc chắn focus rơi đúng vào
    # vùng contenteditable, tránh trường hợp click
    # đầu tiên chỉ trúng placeholder overlay.
    human_click(
        page,
        prompt_box,
        name="Prompt box (second focus)"
    )

    time.sleep(0.3)

    pyperclip.copy(
        prompt_text
    )

    pyautogui.hotkey(
        "ctrl",
        "v"
    )

    human_delay(0.35, 0.70)

    # Xác minh prompt đã thực sự được dán vào ô,
    # tránh trường hợp click bị trượt ra ngoài
    # ProseMirror khiến Create button mãi không sáng.
    pasted_text = prompt_box.inner_text().strip()

    if not pasted_text:
        page.screenshot(
            path="debug_prompt_box_empty.png",
            full_page=True
        )

        raise Exception(
            "Prompt box vẫn trống sau khi dán. "
            "Có thể click bị trượt ra ngoài "
            "ProseMirror. Saved "
            "debug_prompt_box_empty.png"
        )

    print(
        f"Pasted prompt for clip "
        f"{clip_num} "
        f"(verified {len(pasted_text)} ký tự)"
    )

    human_delay(0.35, 0.70)

    # KHÔNG chỉ dùng aria-label="Start generation" vì
    # có thể đổi theo ngôn ngữ tài khoản của từng profile
    # (giống lỗi settings-trigger-button/model-select
    # trước đó). Dùng class generate-icon-button
    # (không đổi theo ngôn ngữ) làm chính, fallback qua
    # icon arrow_forward (tên icon font cũng không đổi
    # theo ngôn ngữ) rồi mới tới aria-label.
    create_button = page.locator(
        "button.generate-icon-button"
    ).first

    if create_button.count() == 0:
        create_button = page.locator(
            "button:has(mat-icon:text('arrow_forward'))"
        ).first

    if create_button.count() == 0:
        create_button = page.locator(
            "button[aria-label='Start generation']"
        ).first

    try:
        create_button.wait_for(
            state="visible",
            timeout=30000
        )

    except Exception as create_button_error:
        page.screenshot(
            path="debug_create_button_not_found.png",
            full_page=True
        )

        raise RuntimeError(
            "Create button was not found or visible. "
            "Saved debug_create_button_not_found.png"
        ) from create_button_error

    start_wait_create = time.time()

    while True:
        aria_disabled = (
            create_button.get_attribute(
                "aria-disabled"
            )
        )

        disabled_attr = (
            create_button.get_attribute(
                "disabled"
            )
        )

        try:
            button_enabled = (
                create_button.is_enabled()
            )
        except Exception:
            button_enabled = False

        if (
            aria_disabled != "true"
            and disabled_attr is None
            and button_enabled
        ):
            break

        if (
            time.time() - start_wait_create
            > 60
        ):
            page.screenshot(
                path="debug_create_button_disabled.png",
                full_page=True
            )

            raise TimeoutError(
                "Create button remained disabled "
                "for more than 60 seconds."
            )

        print(
            "Waiting for Create button "
            "to become enabled..."
        )

        human_delay(0.35, 0.70)

    human_click(
        page,
        create_button,
        name=f"Create clip {clip_num}"
    )

    print(
        f"Clicked Create for clip "
        f"{clip_num}"
    )

    time.sleep(2)


# ─────────────────────────────────────────────
# Render 1 clip trong 1 session riêng biệt
# ─────────────────────────────────────────────

def render_single_clip(
    category,
    product_id,
    clip_num,
    start_image,
    end_image,
    prompt_text,
    save_path
):
    """
    Thử lần lượt các profile chưa bị block trong ngày.

    Dùng chung cho:
    - snack
    - keychain
    - phone_case
    - eyeglasses
    - category mới thêm sau này

    Category, ảnh đầu, ảnh cuối và prompt đều được lấy
    trực tiếp từ render_queue.csv.

    Worker validate riêng các pipeline đã đổi:
    - snack:
        Clip 01: 01_hand_holding
        -> 01_hand_holding
    - keychain:
        Clip 02: 03_hand_holding
        -> 04_hand_holding_next_frame
    - phone_case:
        Clip 01: 01_clip_01_first_frame
        -> 02_clip_01_last_frame
    - eyeglasses:
        Clip 01: 01_hand_holding
        -> 02_closeup

    Trình tự của mỗi profile:
    1. Mở Flow.
    2. Đóng menu quảng cáo/overlay.
    3. Mở avatar và đọc Google Flow credits.
    4. Nếu credits = 0: block profile trong ngày và chuyển profile khác.
    5. Nếu còn credits: đóng menu tài khoản, tạo dự án và render.
    """

    print("=" * 60)

    print(
        f"Rendering product: "
        f"{category}/{product_id} "
        f"| Clip {clip_num}"
    )

    global _is_first_browser_launch_in_run

    with sync_playwright() as p:
        while True:
            try:
                profile_dir, profile_number = (
                    get_next_profile()
                )

            except Exception as e:
                if (
                    str(e)
                    == "All Flow profiles are blocked."
                ):
                    raise Exception(
                        "NO_FLOW_CREDITS_AVAILABLE"
                    ) from e

                raise

            print(
                f"Profile: {profile_number} "
                f"| {profile_dir}"
            )

            browser = (
                p.chromium
                .launch_persistent_context(
                    user_data_dir=profile_dir,
                    headless=False,
                    channel="chrome",
                    accept_downloads=True,
                    ignore_default_args=["--enable-automation"],
                    args=[
                        "--window-size=1900,1000",
                        "--window-position=0,0",
                        "--disable-blink-features=AutomationControlled",
                        # QUAN TRỌNG: Windows có API
                        # "Native Window Occlusion" báo
                        # cho Chrome biết cửa sổ đang bị
                        # che/không active. Khi đó Chrome
                        # tự throttle tải ảnh/network/JS
                        # timer của tab để tiết kiệm tài
                        # nguyên -> video thumbnail không
                        # bao giờ load xong cho tới khi
                        # cửa sổ được đưa lên trước
                        # (giống hệt việc "phóng to" thủ
                        # công). Tắt các cờ dưới đây để
                        # Chrome luôn chạy như cửa sổ
                        # đang active, kể cả khi bị che.
                        "--disable-features="
                        "CalculateNativeWinOcclusion",
                        "--disable-backgrounding-"
                        "occluded-windows",
                        "--disable-renderer-"
                        "backgrounding",
                        "--disable-background-"
                        "timer-throttling",
                        # Giảm khả năng Chrome thật tự làm
                        # gì đó ở nền (kiểm tra update, tải
                        # component, đồng bộ...) ngay khi
                        # vừa mở, tránh việc này chen ngang
                        # đúng lúc đang download.
                        "--no-first-run",
                        "--disable-background-networking",
                        "--disable-component-update",
                        "--disable-client-side-"
                        "phishing-detection",
                        "--disable-sync",
                    ],
                )
            )

            if _is_first_browser_launch_in_run:
                print(
                    "Browser dau tien trong lan chay nay. "
                    "Cho Chrome on dinh truoc khi thao tac..."
                )

                time.sleep(3)

                _is_first_browser_launch_in_run = False

            try:
                page = browser.new_page()

                # Stealth: Ẩn cờ navigator.webdriver
                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)

                # Đưa tab lên foreground để tránh Chrome
                # coi đây là tab nền và throttle thêm.
                page.bring_to_front()

                page.goto(
                    FLOW_URL,
                    wait_until="domcontentloaded",
                    timeout=120000
                )

                print(
                    "Waiting Google Flow load..."
                )

                time.sleep(2)

                # Bắt buộc đóng quảng cáo
                # trước khi mở avatar.
                dismiss_possible_ad_overlay(
                    page
                )

                credits = get_flow_credits(
                    page
                )

                print(
                    f"Google Flow credits: "
                    f"{credits}"
                )

                if credits < 12:
                    print(
                        f"Profile has {credits} credits "
                        f"(< 12), switching profile: "
                        f"{profile_dir}"
                    )

                    add_blocked_profile(
                        profile_dir
                    )

                    page.screenshot(
                        path=(
                            f"debug_low_credits_"
                            f"profile_{profile_number}.png"
                        ),
                        full_page=True
                    )

                    continue

                # Menu avatar đã được đóng trong
                # get_flow_credits khi credits > 0.
                setup_new_project(
                    page
                )

                create_clip(
                    page=page,
                    category=category,
                    product_id=product_id,
                    clip_num=clip_num,
                    start_image=start_image,
                    end_image=end_image,
                    prompt_text=prompt_text
                )

                # Kiểm tra unusual activity.
                page_text = (
                    page.locator("body")
                    .inner_text()
                    .lower()
                )

                if (
                    "unusual activity"
                    in page_text
                    or
                    "hoạt động bất thường"
                    in page_text
                ):
                    print(
                        "Detected unusual activity:",
                        profile_dir
                    )

                    add_blocked_profile(
                        profile_dir
                    )

                    page.screenshot(
                        path=(
                            f"debug_unusual_activity_"
                            f"clip{clip_num}.png"
                        ),
                        full_page=True
                    )

                    raise Exception(
                        "UNUSUAL_ACTIVITY"
                    )

                # GIỮ NGUYÊN CÁCH LỌC VIDEO.
                # Bỏ filter has_text="Videos" vì có thể
                # hiển thị khác ở ngôn ngữ khác (vd tiếng
                # Việt). Icon "videocam" đã đủ để xác định
                # đúng mục trong danh sách, không cần thêm
                # điều kiện text phụ thuộc ngôn ngữ.
                filter_item = page.locator(
                    "mat-list-item"
                ).filter(
                    has=page.locator(
                        "mat-icon:text('videocam')"
                    )
                ).first

                human_click(
                    page,
                    filter_item,
                    name="Videos filter"
                )

                print(
                    "Clicked Videos filter"
                )

                time.sleep(3)

                # Tự động nhận diện selector card
                card_selector = detect_video_card_selector(page, timeout_sec=20)
                total_cards = page.locator(card_selector).count()

                print(
                    f"Total video cards hiện tại ({card_selector}): "
                    f"{total_cards}"
                )

                # Chờ video render xong và tải về (tự động nhận diện đúng card qua progress bar/từ khóa prompt/vị trí mới nhất)
                wait_and_download_video_card(
                    page,
                    card_index=0,
                    save_path=save_path,
                    prompt_text=prompt_text
                )

                print(
                    f"Clip {clip_num} "
                    f"downloaded: {save_path}"
                )

                return profile_dir

            finally:
                browser.close()


# ─────────────────────────────────────────────
# Queue helpers
# ─────────────────────────────────────────────

def get_pending_jobs(rows, target_category=None):
    """
    Trả về list các job pending,
    mỗi job là một clip độc lập.
    Nếu có target_category thì lọc theo ngành hàng đó.
    """

    jobs = [
        row
        for row in rows
        if (
            row.get("status", "")
            .strip()
            .lower()
            == "pending"
        )
    ]
    if target_category:
        cat_clean = target_category.strip().lower()
        jobs = [j for j in jobs if (j.get("category") or "").strip().lower() == cat_clean]
    return jobs


def mark_job_status(
    rows,
    job_id,
    status,
    **kwargs
):
    for row in rows:
        if row["job_id"] == job_id:
            row["status"] = status

            row["updated_at"] = (
                datetime.now()
                .isoformat(
                    timespec="seconds"
                )
            )

            for key, value in kwargs.items():
                row[key] = value

    return rows


def get_flow_credits(page):
    """
    Mở menu avatar, đọc số Google Flow credits.

    Chỉ đóng menu khi credits > 0.
    Nếu credits = 0, caller sẽ đóng browser
    và chuyển sang profile khác.
    """

    import re

    print(
        "Checking Google Flow credits..."
    )

    # GIỮ NGUYÊN SELECTOR INSPECT.
    # ============================================================
    # CLICK AVATAR BUTTON
    # ============================================================

    avatar_button = page.locator(
        'button:has('
        'img[alt="User profile image"]'
        ')'
    ).first

    try:
        avatar_button.wait_for(
            state="visible",
            timeout=15000
        )

    except Exception:

        try:
            # fallback 1
            avatar_button = page.locator(
                ".header-user-button"
            ).first

            avatar_button.wait_for(
                state="visible",
                timeout=5000
            )

        except Exception:

            # fallback 2
            avatar_button = page.locator(
                "button.sc-355d1ae3-7"
            ).first

            avatar_button.wait_for(
                state="visible",
                timeout=10000
            )

    human_click(
        page,
        avatar_button,
        name="Avatar button"
    )

    print(
        "Clicked avatar button"
    )

    # GIỮ NGUYÊN SELECTOR INSPECT.
    credit_locator = page.locator(
        'a[href*="flow_ai_credits_page"]'
    ).first

    credit_locator.wait_for(
        state="visible",
        timeout=15000
    )

    text = (
        credit_locator
        .inner_text()
        .strip()
    )

    print(
        f"Credits text: {text}"
    )

    match = re.search(
        r"([\d.,]+)\s+Google Flow credits",
        text,
        re.IGNORECASE
    )

    if not match:
        match = re.search(
            r"[\d.,]+",
            text
        )

    if not match:
        raise Exception(
            f"FLOW_CREDITS_NOT_FOUND: "
            f"{text}"
        )

    credits_text = (
        match.group(1)
        if match.lastindex
        else match.group(0)
    )

    credits = int(
        re.sub(
            r"\D",
            "",
            credits_text
        )
    )

    if credits > 0:
        # GIỮ NGUYÊN SELECTOR INSPECT.
        close_button = page.locator(
            'button[aria-label="Close this modal"]'
        )

        try:
            if (
                close_button.count() > 0
                and close_button.first.is_visible()
            ):
                human_click(
                    page,
                    close_button.first,
                    name="Close avatar menu"
                )

                print(
                    "Closed avatar menu "
                    "with close button"
                )

            else:
                page.keyboard.press(
                    "Escape"
                )

                page.wait_for_timeout(
                    500
                )

                if (
                    credit_locator.count() > 0
                    and
                    credit_locator.first.is_visible()
                ):
                    # Chỉ sửa tên biến bị thiếu.
                    # Thao tác vẫn là bấm lại avatar.
                    human_click(
                        page,
                        avatar_button,
                        name="Avatar button (close menu)"
                    )

                    print(
                        "Closed avatar menu by "
                        "clicking avatar again"
                    )

        except Exception as e:
            print(
                "Close avatar menu skipped:",
                e
            )

    return credits


# ─────────────────────────────────────────────
# Main loop
# Mỗi job (clip) dùng 1 session riêng
# ─────────────────────────────────────────────

target_category = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].strip() else None
if target_category:
    print(f"🎯 Target category: {target_category}")

while True:
    rows = load_queue()

    pending_jobs = get_pending_jobs(
        rows,
        target_category
    )

    if not pending_jobs:
        print("=" * 60)
        print(
            "No pending jobs left. Done."
        )
        break

    job = pending_jobs[0]

    job_id = job["job_id"]

    category = (
        job.get("category")
        or ""
    ).strip()

    product_id = job["product_id"]

    channel = (
        job.get("channel")
        or "01"
    ).zfill(2)

    clip_index = int(
        job.get("clip_index", 1)
    )

    start_image = resolve_project_path(
        job.get("start_image", "")
    )

    end_image = resolve_project_path(
        job.get("end_image", "")
    )

    prompt_file = resolve_project_path(
        job.get("prompt_file", "")
    )

    print("=" * 60)

    print(
        f"Next job: {job_id} "
        f"| category: {category} "
        f"| product: {product_id} "
        f"| channel: CH{channel} "
        f"| clip: {clip_index}"
    )

    print(
        "Multi-category render worker:",
        "snack / keychain / phone_case / eyeglasses"
    )

    normalized_category = (
        category.lower()
    )

    if normalized_category == "snack":
        print(
            "Snack pipeline:",
            "ONLY clip1 01_hand_holding -> 01_hand_holding"
        )

    elif normalized_category == "keychain":
        print(
            "Keychain pipeline:",
            "ONLY clip2 03->04"
        )

    elif normalized_category == "phone_case":
        print(
            "Phone-case pipeline:",
            "ONLY clip1 01->02"
        )

    elif normalized_category == "eyeglasses":
        print(
            "Eyeglasses pipeline:",
            "ONLY clip1 01_hand_holding->02_closeup"
        )

    # Đánh dấu rendering.
    rows = mark_job_status(
        rows,
        job_id,
        "rendering"
    )

    save_queue(
        rows
    )

    try:
        if not category:
            raise ValueError(
                f"Missing category for job: "
                f"{job_id}"
            )

        if not os.path.exists(
            start_image
        ):
            raise FileNotFoundError(
                f"Missing start image: "
                f"{start_image}"
            )

        if not os.path.exists(
            end_image
        ):
            raise FileNotFoundError(
                f"Missing end image: "
                f"{end_image}"
            )

        validate_render_pair(
            category=category,
            clip_index=clip_index,
            start_image=start_image,
            end_image=end_image
        )

        prompt_text = read_prompt(
            prompt_file
        )

        # Cấu trúc output dùng chung:
        # products/{category}/{product_id}/output/videos
        #
        # Ví dụ:
        # products/snack/SNK001/output/videos
        # products/keychain/KC001/output/videos
        # products/phone_case/PC001/output/videos
        # products/eyeglasses/GL001/output/videos
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

        timestamp = (
            datetime.now()
            .strftime(
                "%Y%m%d_%H%M%S"
            )
        )

        save_path = os.path.join(
            video_output_dir,
            (
                f"{product_id}_"
                f"CH{channel}_"
                f"clip_{clip_index:02d}_"
                f"{timestamp}.mp4"
            )
        )

        profile_dir = render_single_clip(
            category=category,
            product_id=product_id,
            clip_num=clip_index,
            start_image=start_image,
            end_image=end_image,
            prompt_text=prompt_text,
            save_path=save_path
        )

        rows = load_queue()

        attempts = (
            int(
                job.get("attempts")
                or 0
            )
            + 1
        )

        rows = mark_job_status(
            rows,
            job_id,
            "done",
            video_path=save_path,
            profile=profile_dir,
            error="",
            attempts=str(attempts)
        )

        save_queue(
            rows
        )

        print(
            f"Job done: {job_id}"
        )

    except Exception as e:
        error_text = str(e)

        print(
            f"Job failed: {job_id}"
        )

        print(
            "Error:",
            error_text
        )

        rows = load_queue()

        if (
            error_text
            == "NO_FLOW_CREDITS_AVAILABLE"
        ):
            # Không tính là một lần render thất bại.
            attempts = int(
                job.get("attempts")
                or 0
            )

            rows = mark_job_status(
                rows,
                job_id,
                "pending",
                attempts=str(attempts),
                error=(
                    "All Flow profiles "
                    "have 0 credits today."
                )
            )

            save_queue(
                rows
            )

            print(
                "All profiles have 0 credits "
                "today. Stopping batch."
            )

            break

        attempts = (
            int(
                job.get("attempts")
                or 0
            )
            + 1
        )

        # Chỉ riêng trường hợp TẤT CẢ profile đều hết credit mới
        # không đánh failed (branch NO_FLOW_CREDITS_AVAILABLE ở trên).
        # Mọi lỗi khác mà job không thể hoàn tất -> failed ngay, không retry.
        rows = mark_job_status(
            rows,
            job_id,
            "failed",
            attempts=str(attempts),
            error=error_text
        )

        print(
            f"Job {job_id} -> FAILED immediately (no retry)."
        )

        save_queue(
            rows
        )

        time.sleep(5)


print(
    "Batch render finished."
)