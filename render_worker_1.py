from datetime import datetime
from playwright.sync_api import sync_playwright
import os
import time
import csv
import re
import pyautogui
import pyperclip


FLOW_URL = "https://labs.google/fx/vi/tools/flow"

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
    r"C:\flow_auto_profile_01",
    r"C:\flow_auto_profile_02",
    r"C:\flow_auto_profile_03",
    r"C:\flow_auto_profile_04",
    r"C:\flow_auto_profile_05",
    r"C:\flow_auto_profile_06",
    r"C:\flow_auto_profile_07",
    r"C:\flow_auto_profile_08",
    r"C:\flow_auto_profile_09",
    r"C:\flow_auto_profile_10",
    r"C:\flow_auto_profile_11",
    r"C:\flow_auto_profile_12",
    r"C:\flow_auto_profile_14",
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

    page.mouse.click(
        box["x"] + box["width"] / 2,
        box["y"] + box["height"] / 2
    )

    time.sleep(0.5)


def wait_and_download_video_card(
    page,
    card_index,
    save_path
):
    # SELECTOR MỚI: card giờ là <flow-grid-tile-container>,
    # không còn attribute data-tile-id nữa. Card không dùng
    # thẻ <video> để hiển thị mà chỉ có
    # <img class="thumbnail" alt="Generated video thumbnail">
    # khi video đã render xong.
    VIDEO_CARD_SELECTOR = "flow-grid-tile-container"

    video_cards = page.locator(
        VIDEO_CARD_SELECTOR
    )

    count = video_cards.count()

    print(
        f"Found {count} video cards. "
        f"Targeting index {card_index}."
    )

    card = video_cards.nth(
        card_index
    )

    card.scroll_into_view_if_needed()

    time.sleep(0.5)

    box = card.bounding_box()

    if not box:
        raise Exception(
            f"Cannot get bounding box "
            f"of video card {card_index}"
        )

    cx = (
        box["x"]
        + box["width"] / 2
    )

    cy = (
        box["y"]
        + box["height"] / 2
    )

    print(
        f"Waiting for video card "
        f"{card_index} to be ready..."
    )

    for attempt in range(120):
        page.mouse.move(
            cx,
            cy
        )

        time.sleep(2)

        ready = page.evaluate(
            f"""
            () => {{
                const cards =
                    document.querySelectorAll(
                        '{VIDEO_CARD_SELECTOR}'
                    );

                const card = cards[{card_index}];

                if (!card) return false;

                const thumb = card.querySelector(
                    'img.thumbnail'
                );

                if (!thumb) return false;

                const src = (
                    thumb.getAttribute('src') || ''
                );

                const alt = (
                    thumb.getAttribute('alt') || ''
                );

                // Check cả tiếng Anh lẫn tiếng Việt vì
                // alt bị dịch theo ngôn ngữ tài khoản
                // của từng profile.
                const altReady = (
                    alt === 'Generated video thumbnail'
                    || alt === (
                        'Hình thu nhỏ của video đã tạo'
                    )
                );

                return (
                    src.startsWith('http')
                    && altReady
                );
            }}
            """
        )

        if ready:
            print(
                f"Video card "
                f"{card_index} ready."
            )
            break

        print(
            f"  waiting... "
            f"{attempt + 1}/120"
        )

    else:
        page.screenshot(
            path="debug_video_card_not_ready.png",
            full_page=True
        )

        raise Exception(
            f"Timeout waiting for "
            f"video card {card_index}. "
            f"Saved debug_video_card_not_ready.png"
        )

    time.sleep(1)

    page.mouse.move(
        cx,
        cy
    )

    time.sleep(1)

    page.mouse.click(
        cx,
        cy,
        button="right"
    )

    print(
        f"Right clicked video "
        f"card {card_index}"
    )

    time.sleep(2)

    page.locator(
        "button[mat-menu-item]"
    ).filter(
        has=page.locator(
            "mat-icon:text('download')"
        )
    ).click(
        force=True
    )

    print(
        "Clicked Tải xuống"
    )

    time.sleep(2)

    with page.expect_download(
        timeout=180000
    ) as dl_info:
        page.locator(
            "button[mat-menu-item]"
        ).filter(
            has_text="720p"
        ).click(
            force=True
        )

    download = dl_info.value

    download.save_as(
        save_path
    )

    print(
        f"Saved: {save_path}"
    )


# ─────────────────────────────────────────────
# Setup: new project + settings
# ─────────────────────────────────────────────

def dismiss_possible_ad_overlay(page):
    """Đóng menu quảng cáo/overlay trước khi kiểm tra tài khoản."""
    try:
        print("Trying close popup...")

        # Click vùng giữa phía trên trang,
        # tránh thanh menu bên trái.
        page.mouse.click(1880, 500)
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
                    page.mouse.click(center_x, center_y)
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
                page.mouse.click(center_x, center_y)
                return True

            # Không còn gì che -> click thật vào nút
            try:
                button.click(timeout=2000)
                print(f"{name}: click chuẩn OK (không còn overlay che)")
                return True
            except Exception as e:
                print(f"{name}: click chuẩn fail sau khi hết overlay - {e}")

            try:
                button.evaluate("(el) => el.click()")
                print(f"{name}: JS click OK")
                return True
            except Exception as e:
                print(f"{name}: JS click fail - {e}")

            try:
                button.evaluate(
                    """(el) => {
                        const rect = el.getBoundingClientRect();
                        const x = rect.x + rect.width / 2;
                        const y = rect.y + rect.height / 2;
                        const opts = { bubbles: true, cancelable: true, clientX: x, clientY: y, view: window };
                        el.dispatchEvent(new MouseEvent('mousedown', opts));
                        el.dispatchEvent(new MouseEvent('mouseup', opts));
                        el.dispatchEvent(new MouseEvent('click', opts));
                    }"""
                )
                print(f"{name}: dispatch thủ công OK")
                return True
            except Exception as e:
                print(f"{name}: dispatch thủ công fail - {e}")
                return False

        print(f"{name}: hết số lần thử, overlay vẫn còn che nút")
        return False

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

    time.sleep(3)

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

    time.sleep(2)

    print(
        "Clicked video setting button"
    )

    time.sleep(2)
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
    ).first

    try:
        video_tab.wait_for(
            state="visible",
            timeout=30000
        )

    except Exception as video_tab_error:
        page.screenshot(
            path="debug_video_tab_not_found.png",
            full_page=True
        )

        raise RuntimeError(
            "Video tab was not found or visible. "
            "Saved debug_video_tab_not_found.png"
        ) from video_tab_error

    video_checked = (
            video_tab.get_attribute(
                "aria-checked"
            )
            == "true"
    )
    if video_checked:
        print(
            "Video already selected"
        )

    else:
        video_tab.click(
            force=True
        )

        print(
            "Selected Video"
        )

        # Xác nhận tab đã chuyển sang active.
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

    time.sleep(1)

    page.locator(
        "button.mat-button-toggle-button"
    ).filter(
        has=page.locator(
            "mat-icon:text('crop_free')"
        )
    ).click(
        force=True
    )

    print(
        "Selected Khung hình tab"
    )

    time.sleep(1)

    page.locator(
        "button.mat-button-toggle-button"
    ).filter(
        has=page.locator(
            "mat-icon:text('crop_9_16')"
        )
    ).click(
        force=True
    )

    print(
        "Selected 9:16"
    )

    time.sleep(1)

    page.locator(
        "button.mat-button-toggle-button"
    ).filter(
        has_text="x1"
    ).click(
        force=True
    )

    print(
        "Selected x1"
    )

    time.sleep(1)

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

    model_trigger.click(
        force=True
    )

    print(
        "Opened model dropdown"
    )

    time.sleep(1)

    page.locator(
        "button[mat-menu-item]"
    ).filter(
        has_text="Veo 3.1 - Lite"
    ).click(
        force=True
    )

    print(
        "Selected Veo 3.1 - Lite"
    )

    time.sleep(1)


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
    """

    ai_dir = os.path.abspath(
        os.path.join(
            PRODUCTS_ROOT,
            category,
            product_id,
            "images",
            "ai"
        )
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

    image_paths = [
        get_ai_image_path(
            category,
            product_id,
            image_name
        )
        for image_name in images_to_upload
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
                btn.click(
                    force=True,
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

    time.sleep(2)

    # Chọn Upload trong menu
    upload_item = page.locator(
        "button[mat-menu-item]"
    ).filter(
        has=page.locator(
            "mat-icon:text('upload')"
        )
    ).first

    upload_item.click(
        force=True
    )

    print(
        f"Clicked Upload menu "
        f"(clip {clip_num})"
    )

    time.sleep(2)

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

    time.sleep(2)

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

    time.sleep(3)

    print(
        f"2 images uploaded for clip "
        f"{clip_num}: {images_to_upload}"
    )

    time.sleep(3)


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
    page.locator(
        "button.empty-chip"
    ).filter(
        has_text=re.compile(
            r"^\s*(Start|Bắt đầu)\s*$"
        )
    ).first.click(
        force=True
    )

    print(
        "Clicked Bắt đầu"
    )

    time.sleep(2)

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

    time.sleep(2)

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
            btn_them.click(
                force=True
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
    page.locator(
        "button.empty-chip"
    ).filter(
        has_text=re.compile(
            r"^\s*(End|Kết thúc)\s*$"
        )
    ).first.click(
        force=True
    )

    print(
        "Clicked Kết thúc"
    )

    time.sleep(4)

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

    time.sleep(2)

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
            btn_them2.click(
                force=True
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

    prompt_box.click(
        force=True
    )

    time.sleep(0.5)

    # Click lần 2 để chắc chắn focus rơi đúng vào
    # vùng contenteditable, tránh trường hợp click
    # đầu tiên chỉ trúng placeholder overlay.
    prompt_box.click(
        force=True
    )

    time.sleep(0.5)

    pyperclip.copy(
        prompt_text
    )

    pyautogui.hotkey(
        "ctrl",
        "v"
    )

    time.sleep(2)

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

    time.sleep(2)

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

        time.sleep(2)

    create_button.click(
        force=True
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
                    ],
                )
            )

            try:
                page = browser.new_page()

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

                if credits == 0:
                    print(
                        f"Profile has 0 credits, "
                        f"switching profile: "
                        f"{profile_dir}"
                    )

                    add_blocked_profile(
                        profile_dir
                    )

                    page.screenshot(
                        path=(
                            f"debug_zero_credits_"
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
                page.locator(
                    "mat-list-item"
                ).filter(
                    has=page.locator(
                        "mat-icon:text('videocam')"
                    )
                ).click(
                    force=True
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

    avatar_button.click(
        force=True
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
                close_button.first.click(
                    force=True
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
                    avatar_button.evaluate(
                        "(el) => "
                        "(el.closest('button') || el).click()"
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
        "lipstick / sandal / keychain / phone_case / mask"
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

        if error_text == "UNUSUAL_ACTIVITY":
            new_status = "pending"

        elif attempts >= 3:
            new_status = "failed"

        else:
            new_status = "pending"

        rows = mark_job_status(
            rows,
            job_id,
            new_status,
            attempts=str(attempts),
            error=error_text
        )

        save_queue(
            rows
        )

        time.sleep(5)


print(
    "Batch render finished."
)