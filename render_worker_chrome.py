from datetime import datetime
from playwright.sync_api import sync_playwright
import os
import time
import csv
import re
import random
import pyautogui
import pyperclip


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


FLOW_PROFILES = [
    #r"C:\flow_auto_profile_01",
    r"C:\flow_auto_profile_02",
    r"C:\flow_auto_profile_03",
    r"C:\flow_auto_profile_04",
    r"C:\flow_auto_profile_05",
    r"C:\flow_auto_profile_06",
    r"C:\flow_auto_profile_07",
    r"C:\flow_auto_profile_08",
    r"C:\flow_auto_profile_09",
    #r"C:\flow_auto_profile_10",
    #r"C:\flow_auto_profile_11",
    #r"C:\flow_auto_profile_12",
    #r"C:\flow_auto_profile_14",
]


VIDEOS_PER_PROFILE = 1

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


def human_click(page, locator, name="element", button="left", timeout=10000):
    """
    Di chuyển con trỏ Windows thật tới gần vị trí nút, sau đó để
    Playwright click đúng tâm element. Cách hybrid này giữ được vị trí
    chuột có chuyển động trên màn hình nhưng không phụ thuộc tuyệt đối vào
    phép quy đổi viewport -> screen vốn có thể lệch khi Windows display
    scaling/DPI hoặc Chrome toolbar thay đổi.
    """
    locator = locator.first
    locator.wait_for(state="visible", timeout=timeout)
    locator.scroll_into_view_if_needed()
    human_delay(0.10, 0.24)

    box = locator.bounding_box()
    if not box:
        raise Exception(f"{name}: cannot get bounding box")

    viewport_x = box["x"] + box["width"] / 2
    viewport_y = box["y"] + box["height"] / 2

    print(
        f"{name}: move mouse near viewport "
        f"({viewport_x:.0f}, {viewport_y:.0f})"
    )

    try:
        page.bring_to_front()
    except Exception:
        pass

    # Di chuyển chuột Windows thật tới vị trí ước lượng gần nút.
    # Không dùng vị trí này để quyết định click -> tránh lệch DPI/window.
    try:
        screen = viewport_to_screen(page, viewport_x, viewport_y)
        offset_x = random.randint(-18, 18)
        offset_y = random.randint(-12, 12)
        pyautogui.moveTo(
            int(screen["x"]) + offset_x,
            int(screen["y"]) + offset_y,
            duration=random.uniform(0.08, 0.18)
        )
    except Exception as e:
        print(f"{name}: OS mouse move skipped: {e}")

    human_delay(0.06, 0.14)

    # Click thật trên page tại đúng vị trí Playwright đã xác định.
    # Vị trí cursor vật lý không ảnh hưởng tới độ chính xác của click này.
    page.mouse.move(viewport_x, viewport_y, steps=3)
    page.mouse.click(viewport_x, viewport_y, button=button)

    human_delay(0.16, 0.34)


def human_click_xy(page, x, y, name="coordinate", button="left"):
    """
    Di chuyển con trỏ Windows thật tới gần tọa độ mục tiêu rồi click chính
    xác bằng Playwright tại đúng viewport coordinate.
    """
    print(
        f"{name}: move mouse near viewport "
        f"({x:.0f}, {y:.0f})"
    )

    try:
        page.bring_to_front()
    except Exception:
        pass

    try:
        screen = viewport_to_screen(page, x, y)
        offset_x = random.randint(-18, 18)
        offset_y = random.randint(-12, 12)
        pyautogui.moveTo(
            int(screen["x"]) + offset_x,
            int(screen["y"]) + offset_y,
            duration=random.uniform(0.08, 0.18)
        )
    except Exception as e:
        print(f"{name}: OS mouse move skipped: {e}")

    human_delay(0.06, 0.14)
    page.mouse.move(x, y, steps=3)
    page.mouse.click(x, y, button=button)
    human_delay(0.16, 0.34)


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
        products/lipstick/LP001/images/ai/...
        products/sandal/SDL001/images/ai/...
        products/keychain/KC001/images/ai/...
        products/phone_case/PC001/images/ai/...
        products/mask/MSK001/images/ai/...
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

    keychain:
        chỉ còn Clip 02
        03_hand_holding.png
        -> 04_hand_holding_next_frame.png

    phone_case:
        chỉ còn Clip 01
        01_clip_01_first_frame.png
        -> 02_clip_01_last_frame.png

    mask:
        chỉ có Clip 01
        01_side_view.png
        -> 02_front_view.png

    eyeglasses:
        chỉ có Clip 01
        01_hand_holding.png
        -> 02_closeup.png

    lipstick và sandal giữ nguyên logic queue hiện tại.
    """

    normalized_category = (
        str(category or "")
        .strip()
        .lower()
    )

    if normalized_category not in {
        "keychain",
        "phone_case",
        "mask",
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
    timeout_rounds=180
):
    last_ready_count = -1
    stable_rounds = 0

    for i in range(timeout_rounds):
        total_count = page.locator(
            ASSET_CARD_SELECTOR
        ).count()

        ready_count = page.locator(
            ASSET_CARD_READY_SELECTOR
        ).count()

        print(
            f"Image cards ready: "
            f"{ready_count}/{expected_count} "
            f"(trong DOM: {total_count})"
        )

        if ready_count >= expected_count:
            if ready_count == last_ready_count:
                stable_rounds += 1
            else:
                stable_rounds = 0

            last_ready_count = ready_count

            if stable_rounds >= 3:
                print(
                    "Image cards stable."
                )
                return

        else:
            stable_rounds = 0
            last_ready_count = ready_count

        time.sleep(2)

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


def wait_and_download_video_card(
    page,
    card_index,
    save_path
):
    VIDEO_CARD_SELECTOR = "flow-grid-tile-container"

    video_cards = page.locator(VIDEO_CARD_SELECTOR)
    count = video_cards.count()

    print(
        f"Found {count} video cards. "
        f"Targeting index {card_index}."
    )

    if count <= card_index:
        page.screenshot(
            path="debug_video_card_not_found.png",
            full_page=True
        )
        raise Exception(
            f"Video card {card_index} not found. "
            f"Found {count} cards."
        )

    print(f"Waiting for video card {card_index} to be ready...")

    # KHÔNG hover trong lúc chờ. Hover có thể bật preview và làm Flow
    # thay đổi DOM/card liên tục.
    for attempt in range(120):
        time.sleep(2)

        debug_info = page.evaluate(
            f"""
            () => {{
                const cards = document.querySelectorAll(
                    '{VIDEO_CARD_SELECTOR}'
                );
                const card = cards[{card_index}];

                if (!card) {{
                    return {{
                        ready: false,
                        reason: 'card_not_found',
                        total_cards: cards.length
                    }};
                }}

                const videoTile = card.querySelector('flow-video-tile');
                const thumb = card.querySelector('img.thumbnail');

                if (!videoTile) {{
                    return {{
                        ready: false,
                        reason: 'video_tile_not_found',
                        total_cards: cards.length,
                        card_html: (card.outerHTML || '').slice(0, 800)
                    }};
                }}

                if (!thumb) {{
                    return {{
                        ready: false,
                        reason: 'thumb_not_found',
                        total_cards: cards.length,
                        card_html: (card.outerHTML || '').slice(0, 800)
                    }};
                }}

                const src = thumb.getAttribute('src') || '';
                const currentSrc = thumb.currentSrc || '';
                const alt = thumb.getAttribute('alt') || '';
                const thumbnailUrl = currentSrc || src;

                // Không bắt buộc thumb.complete/naturalWidth > 0 nữa.
                // Chỉ cần đúng video card + thumbnail đã có URL thực.
                const ready = Boolean(
                    thumbnailUrl &&
                    /^(https?:|blob:|data:)/i.test(thumbnailUrl)
                );

                return {{
                    ready: ready,
                    reason: ready ? 'ready' : 'thumbnail_url_not_ready',
                    total_cards: cards.length,
                    src_prefix: src.slice(0, 80),
                    current_src_prefix: currentSrc.slice(0, 80),
                    alt: alt,
                    complete: thumb.complete,
                    natural_width: thumb.naturalWidth,
                    natural_height: thumb.naturalHeight
                }};
            }}
            """
        )

        if debug_info.get("ready", False):
            print(
                f"Video card {card_index} ready | "
                f"src={debug_info.get('src_prefix', '')!r} | "
                f"currentSrc={debug_info.get('current_src_prefix', '')!r}"
            )
            break

        print(
            f"  waiting... {attempt + 1}/120 | "
            f"reason={debug_info.get('reason')} | "
            f"total_cards={debug_info.get('total_cards')} | "
            f"src={debug_info.get('src_prefix', '')!r} | "
            f"currentSrc={debug_info.get('current_src_prefix', '')!r} | "
            f"complete={debug_info.get('complete')} | "
            f"natural={debug_info.get('natural_width')}x"
            f"{debug_info.get('natural_height')}"
        )

        if debug_info.get("reason") in {
            "video_tile_not_found",
            "thumb_not_found"
        }:
            print(
                "  card_html: "
                f"{debug_info.get('card_html', '')}"
            )

    else:
        page.screenshot(
            path="debug_video_card_not_ready.png",
            full_page=True
        )
        raise Exception(
            f"Timeout waiting for video card {card_index}. "
            f"Saved debug_video_card_not_ready.png"
        )

    # Flow có thể replace DOM sau khi thumbnail ready -> lấy lại card.
    card = page.locator(VIDEO_CARD_SELECTOR).nth(card_index)
    card.scroll_into_view_if_needed()
    time.sleep(0.5)

    box = card.bounding_box()
    if not box:
        raise Exception(
            f"Cannot get bounding box of video card {card_index}"
        )

    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2

    # Từ thời điểm video đã render xong, không dùng human_click /
    # pyautogui nữa. Click trực tiếp bằng Playwright để tránh việc
    # di chuyển chuột vật lý làm menu bị mất focus hoặc đóng ngoài ý muốn.
    card.click(
        button="right",
        force=True,
        timeout=10000
    )

    print(f"Right clicked video card {card_index} (direct Playwright click)")
    time.sleep(2)

    download_menu_item = page.locator(
        "button[mat-menu-item]"
    ).filter(
        has=page.locator("mat-icon:text('download')")
    ).first

    download_menu_item.wait_for(
        state="visible",
        timeout=10000
    )

    download_menu_item.click(
        force=True,
        timeout=10000
    )

    print("Clicked Tải xuống (direct Playwright click)")
    time.sleep(2)

    with page.expect_download(timeout=180000) as dl_info:
        # Flow UI hiện tại: 720p nằm trong
        # <button mat-menu-item> -> <span class="item-text">
        # -> <span class="label">720p</span>.
        # Khớp trực tiếp label để không phụ thuộc caption/language.
        resolution_menu_item = page.locator(
            "button[mat-menu-item]"
        ).filter(
            has=page.locator(
                "span.item-text span.label"
            ).filter(
                has_text=re.compile(r"^\s*720p\s*$")
            )
        ).first

        # Fallback 1: class item-text thay đổi nhưng span.label vẫn còn.
        if resolution_menu_item.count() == 0:
            resolution_menu_item = page.locator(
                "button[mat-menu-item]"
            ).filter(
                has=page.locator(
                    "span.label"
                ).filter(
                    has_text=re.compile(r"^\s*720p\s*$")
                )
            ).first

        # Fallback 2: match trực tiếp text của menu item. HTML hiện tại
        # có cả "720p" và caption "Original size", nên dùng regex chứa 720p.
        if resolution_menu_item.count() == 0:
            resolution_menu_item = page.locator(
                "button[mat-menu-item]"
            ).filter(
                has_text=re.compile(r"\b720p\b", re.IGNORECASE)
            ).first

        resolution_menu_item.wait_for(
            state="visible",
            timeout=15000
        )

        print("720p download menu item found, clicking directly...")

        # Không dùng human_click ở bước download. Menu Angular Material
        # có thể đóng nếu con trỏ vật lý di chuyển/focus thay đổi.
        resolution_menu_item.click(
            force=True,
            timeout=10000
        )

        print("Clicked 720p download option (direct Playwright click)")

    download = dl_info.value

    try:
        download.save_as(save_path)
    except Exception as save_error:
        print(
            "LOI KHI LUU DOWNLOAD - browser/context co the "
            "da bi dong giua chung (khong phai do click sai "
            "nut). Chi tiet:",
            save_error
        )
        raise

    print(f"Saved: {save_path}")


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

        for attempt in range(1, max_attempts + 1):
            already_checked = (
                button.get_attribute(
                    "aria-checked"
                )
                == "true"
            )

            if already_checked:
                print(
                    f"{name}: already selected, skip click"
                )
                return True

            try_click_button(
                button,
                name
            )

            page.wait_for_timeout(700)

            now_checked = (
                button.get_attribute(
                    "aria-checked"
                )
                == "true"
            )

            if now_checked:
                print(
                    f"{name}: selected OK "
                    f"(attempt {attempt})"
                )
                return True

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

    human_delay(1.20, 1.95)

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

    human_delay(0.85, 1.55)

    print(
        "Clicked video setting button"
    )

    human_delay(0.85, 1.55)
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

    human_delay(0.55, 1.05)

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

    human_delay(0.55, 1.05)

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

    human_delay(0.55, 1.05)

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

    human_delay(0.55, 1.05)

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

        page.wait_for_timeout(700)

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

    human_delay(0.55, 1.05)

    # Thời lượng 8s: mặc định thường đã được chọn sẵn,
    # nhưng vẫn chủ động chọn để không phụ thuộc vào
    # mặc định của từng profile/phiên bản UI.
    duration_8s = page.locator(
        "button.mat-button-toggle-button"
    ).filter(
        has_text="8s"
    )

    if duration_8s.count() > 0:
        click_toggle_and_verify(
            duration_8s,
            "8s duration"
        )

        human_delay(0.55, 1.05)

    speed_x1 = page.locator(
        "button.mat-button-toggle-button"
    ).filter(
        has_text="x1"
    )

    click_toggle_and_verify(
        speed_x1,
        "x1 speed"
    )

    human_delay(0.55, 1.05)


# ─────────────────────────────────────────────
# Upload 2 ảnh của một clip
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
    Giữ nguyên thao tác upload ảnh vào Google Flow.

    Tên ảnh thực tế luôn được đọc từ render_queue.csv.

    Pipeline hiện tại:

    Son:
        clip 1: 01_hand_holding + 02_opened_product
        clip 2: 03_mid_swatch + 04_final_swatch

    Dép:
        clip 1: 01_hand_holding + 02_product_closeup
        clip 2: 03_on_foot + 04_on_foot_next_frame

    Móc khóa:
        chỉ còn clip 2:
        03_hand_holding + 04_hand_holding_next_frame

    Ốp lưng:
        chỉ còn clip 1:
        01_clip_01_first_frame
        + 02_clip_01_last_frame

    Khẩu trang:
        chỉ có clip 1:
        01_side_view + 02_front_view

    Mắt kính:
        chỉ có clip 1:
        01_hand_holding + 02_closeup
    """

    # QUAN TRỌNG: KHÔNG dùng cứng
    # products/{category}/{product_id}/images/ai vì
    # ảnh giờ nằm trong subfolder theo channel
    # (images/ai/channel_1 ... channel_5). Lấy đúng
    # thư mục chứa ảnh từ start_image đã resolve
    # (đường dẫn đầy đủ từ render_queue.csv) để hộp
    # thoại Windows mở đúng nơi, không bị kẹt ở
    # images/ai.
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

    images_to_upload = [
        start_image_name,
        end_image_name
    ]

    # QUAN TRỌNG: dùng thẳng start_image/end_image đã
    # được resolve từ render_queue.csv (giữ nguyên
    # subfolder channel, vd images/ai/channel_3/...).
    # KHÔNG dựng lại path qua get_ai_image_path vì hàm
    # đó giả định ảnh nằm trực tiếp trong images/ai/,
    # sẽ làm mất phần channel_X và gây lỗi
    # "Missing AI image".
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

    image_paths = [
        start_image,
        end_image
    ]

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

    human_delay(0.85, 1.55)

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

    human_delay(0.85, 1.55)

    file_names_text = " ".join([
        f'"{os.path.basename(path)}"'
        for path in image_paths
    ])

    # GIỮ NGUYÊN THỨ TỰ THAO TÁC HỘP THOẠI WINDOWS
    pyperclip.copy(
        ai_dir
    )

    pyautogui.hotkey(
        "ctrl",
        "l"
    )

    time.sleep(0.5)

    pyautogui.hotkey(
        "ctrl",
        "v"
    )

    time.sleep(0.5)

    pyautogui.press(
        "enter"
    )

    human_delay(0.85, 1.55)

    pyperclip.copy(
        file_names_text
    )

    pyautogui.hotkey(
        "alt",
        "n"
    )

    time.sleep(0.5)

    pyautogui.hotkey(
        "ctrl",
        "v"
    )

    time.sleep(0.5)

    pyautogui.press(
        "enter"
    )

    human_delay(1.20, 1.95)

    print(
        f"2 images uploaded for clip "
        f"{clip_num}: {images_to_upload}"
    )

    human_delay(1.20, 1.95)


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

    human_delay(0.85, 1.55)

    # Panel Bắt đầu vừa mở ra, ảnh vừa upload
    # cần thời gian để hiện thành card chọn được.
    # Card CHỈ xuất hiện sau khi bấm Start,
    # không phải ngay sau khi upload xong.
    wait_image_cards_stable(
        page,
        expected_count=2
    )

    click_image_card(
        page,
        start_image_name
    )

    print(
        f"Selected start image: "
        f"{start_image_name}"
    )

    human_delay(0.85, 1.55)

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

    human_delay(1.45, 2.35)

    # Tương tự panel Start, panel End cũng cần
    # chờ card ảnh hiện ra sau khi bấm mới chọn được.
    wait_image_cards_stable(
        page,
        expected_count=2
    )

    click_image_card(
        page,
        end_image_name
    )

    print(
        f"Selected end image: "
        f"{end_image_name}"
    )

    human_delay(0.85, 1.55)

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

    time.sleep(0.5)

    # Click lần 2 để chắc chắn focus rơi đúng vào
    # vùng contenteditable, tránh trường hợp click
    # đầu tiên chỉ trúng placeholder overlay.
    human_click(
        page,
        prompt_box,
        name="Prompt box (second focus)"
    )

    time.sleep(0.5)

    pyperclip.copy(
        prompt_text
    )

    pyautogui.hotkey(
        "ctrl",
        "v"
    )

    human_delay(0.85, 1.55)

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

    human_delay(0.85, 1.55)

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

        human_delay(0.85, 1.55)

    human_click(
        page,
        create_button,
        name=f"Create clip {clip_num}"
    )

    print(
        f"Clicked Create for clip "
        f"{clip_num}"
    )

    time.sleep(5)


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
    - lipstick
    - sandal
    - keychain
    - phone_case
    - mask
    - eyeglasses
    - category mới thêm sau này

    Category, ảnh đầu, ảnh cuối và prompt đều được lấy
    trực tiếp từ render_queue.csv.

    Worker validate riêng các pipeline đã đổi:
    - keychain:
        Clip 02: 03_hand_holding
        -> 04_hand_holding_next_frame
    - phone_case:
        Clip 01: 01_clip_01_first_frame
        -> 02_clip_01_last_frame
    - mask:
        Clip 01: 01_side_view
        -> 02_front_view
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
                    args=[
                        "--window-size=1900,1000",
                        "--window-position=0,0",
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
                    "Cho them de Chrome on dinh truoc khi "
                    "thao tac..."
                )

                time.sleep(8)

                _is_first_browser_launch_in_run = False

            try:
                page = browser.new_page()

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

                time.sleep(5)

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

                total_cards = page.locator(
                    "flow-grid-tile-container"
                ).count()

                print(
                    f"Total video cards: "
                    f"{total_cards}"
                )

                if total_cards <= 0:
                    raise Exception(
                        "No video cards found "
                        "after generation."
                    )

                # Card cuối cùng là clip vừa generate.
                wait_and_download_video_card(
                    page,
                    card_index=total_cards - 1,
                    save_path=save_path
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

def get_pending_jobs(rows):
    """
    Trả về list các job pending,
    mỗi job là một clip độc lập.
    """

    return [
        row
        for row in rows
        if (
            row.get("status", "")
            .strip()
            .lower()
            == "pending"
        )
    ]


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

while True:
    rows = load_queue()

    pending_jobs = get_pending_jobs(
        rows
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
        "lipstick / sandal / keychain / phone_case / mask / eyeglasses"
    )

    normalized_category = (
        category.lower()
    )

    if normalized_category == "keychain":
        print(
            "Keychain pipeline:",
            "ONLY clip2 03->04"
        )

    elif normalized_category == "phone_case":
        print(
            "Phone-case pipeline:",
            "ONLY clip1 01->02"
        )

    elif normalized_category == "mask":
        print(
            "Mask pipeline:",
            "ONLY clip1 side_view->front_view"
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
        # products/keychain/KC001/output/videos
        # products/phone_case/PC001/output/videos
        # products/mask/MSK001/output/videos
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