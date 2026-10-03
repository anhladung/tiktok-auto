from datetime import datetime
from playwright.sync_api import sync_playwright
import os
import subprocess
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

# image_queue.csv không có cột prompt_file như render_queue.csv.
# Prompt cho từng "step" dùng chung cho mọi product/channel,
# theo cấu trúc:
#   prompts/{category}/image_generation/{step}.txt
# Ví dụ:
#   prompts/keychain/image_generation/03_hand_holding.txt
PROMPTS_ROOT = os.path.join(
    BASE_DIR,
    "prompts"
)

QUEUE_FILE = os.path.join(
    BASE_DIR,
    "queue",
    "image_queue.csv"
)

# Profile rotation giống render worker.
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

IMAGE_PROFILE_STATE_FILE = os.path.join(
    BASE_DIR,
    "image_profile_state.txt"
)

IMAGE_BLOCKED_PROFILE_FILE = os.path.join(
    BASE_DIR,
    "image_blocked_profiles.txt"
)

IMAGES_PER_PROFILE = 1

# Đánh dấu Chrome (thật, channel="chrome") đầu tiên được mở
# trong lần chạy script này, để chờ Chrome ổn định trước khi
# thao tác (giữ nguyên lý do như render_worker_2.py).
_is_first_browser_launch_in_run = True


# ─────────────────────────────────────────────
# Queue
# ─────────────────────────────────────────────

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
            fieldnames=QUEUE_FIELDNAMES,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(rows)


def get_pending_jobs(rows):
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



def get_blocked_profiles():
    if not os.path.exists(IMAGE_BLOCKED_PROFILE_FILE):
        return set()

    today = datetime.now().date().isoformat()
    blocked = set()

    with open(IMAGE_BLOCKED_PROFILE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            if "|" in line:
                profile, date = line.rsplit("|", 1)
                if date == today:
                    blocked.add(profile)

    return blocked


def add_blocked_profile(profile):
    today = datetime.now().date().isoformat()

    if profile in get_blocked_profiles():
        return

    with open(IMAGE_BLOCKED_PROFILE_FILE, "a", encoding="utf-8") as f:
        f.write(f"{profile}|{today}\n")


def get_next_image_profile():
    blocked = get_blocked_profiles()

    if os.path.exists(IMAGE_PROFILE_STATE_FILE):
        with open(IMAGE_PROFILE_STATE_FILE, "r", encoding="utf-8") as f:
            index = int(f.read().strip() or 0)
    else:
        index = 0

    for _ in range(len(FLOW_PROFILES)):
        profile = FLOW_PROFILES[index % len(FLOW_PROFILES)]
        index += 1

        if profile not in blocked:
            with open(IMAGE_PROFILE_STATE_FILE, "w", encoding="utf-8") as f:
                f.write(str(index))

            return profile

    raise Exception("ALL_IMAGE_PROFILES_BLOCKED")


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def resolve_project_path(path):
    """
    Hỗ trợ đường dẫn tương đối (so với BASE_DIR, dùng
    dấu \\ như trong image_queue.csv) và đường dẫn tuyệt đối.
    """

    if not path:
        return ""

    path = str(path).strip()

    path = path.replace(
        "/",
        os.sep
    ).replace(
        "\\",
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


def get_prompt_path(category, step):
    """
    Cấu trúc prompt dùng chung theo category + step:
        prompts/{category}/image_generation/{step}.txt

    Ví dụ:
        prompts/keychain/image_generation/03_hand_holding.txt
    """

    return os.path.join(
        PROMPTS_ROOT,
        category,
        "image_generation",
        f"{step}.txt"
    )


def read_prompt(prompt_file):
    if not os.path.exists(prompt_file):
        raise FileNotFoundError(
            f"Prompt not found: {prompt_file}"
        )

    with open(
        prompt_file,
        "r",
        encoding="utf-8"
    ) as f:
        return f.read().strip()


# ─────────────────────────────────────────────
# Setup project: giống render_worker_2.py nhưng chọn
# Image thay vì Video, và model Nano Banana Pro thay vì
# Omni 1.1 Flash. Không cần chọn 720p/x1 vì đó là setting
# riêng của Video.
# ─────────────────────────────────────────────

def dismiss_possible_ad_overlay(page):
    """Đóng menu quảng cáo/overlay trước khi thao tác tiếp."""
    try:
        print("Trying close popup...")

        page.mouse.click(1880, 500)
        time.sleep(2)

        print("Popup area cleared")

    except Exception as e:
        print("Popup clear skipped:", e)


def try_click_button(button, name, max_backdrop_attempts=3):
    """
    GIỮ NGUYÊN logic từ render_worker_2.py: xử lý trường hợp
    button bị cdk-overlay-backdrop che, đóng overlay trước khi
    click lại vào nút thật.
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


def setup_new_project_image(page):
    # ============================================================
    # CLICK NEW PROJECT BUTTON (giống render_worker_2.py)
    # ============================================================
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

    # VIDEO SETTING BUTTON (mở panel setting - class không đổi
    # theo ngôn ngữ, giữ nguyên selector từ render worker).
    settings_button = page.locator(
        "button.settings-trigger-button"
    ).first

    if settings_button.count() == 0:
        settings_button = page.locator(
            '[aria-label="Settings trigger"], '
            '[aria-label="Điều kiện kích hoạt cài đặt"]'
        ).first

    if not try_click_button(settings_button, "video setting button"):
        raise Exception("Cannot click video setting button")

    print("Clicked video setting button")

    time.sleep(2)

    # ============================================================
    # Chọn tab "Image" (thay vì "Video" như render worker).
    # ============================================================
    image_tab = page.locator(
        "button.mat-button-toggle-button"
    ).filter(
        has=page.locator(
            "mat-icon:text('image')"
        )
    ).first

    try:
        image_tab.wait_for(
            state="visible",
            timeout=30000
        )

    except Exception as image_tab_error:
        page.screenshot(
            path="debug_image_tab_not_found.png",
            full_page=True
        )

        raise RuntimeError(
            "Image tab was not found or visible. "
            "Saved debug_image_tab_not_found.png"
        ) from image_tab_error

    image_checked = (
        image_tab.get_attribute(
            "aria-checked"
        )
        == "true"
    )

    if image_checked:
        print("Image already selected")
    else:
        image_tab.click(
            force=True
        )

        print("Selected Image")

        time.sleep(1)

    time.sleep(1)

    # Ở chế độ Image, nút 9:16 đã hiện sẵn trực tiếp (không
    # có tab "Khung hình"/crop_free riêng để mở trước như
    # trong render_worker_2.py - đó là hành vi của Video).
    aspect_9_16 = page.locator(
        "button.mat-button-toggle-button"
    ).filter(
        has=page.locator(
            "mat-icon:text('crop_9_16')"
        )
    ).first

    try:
        aspect_9_16.wait_for(
            state="visible",
            timeout=30000
        )

    except Exception as aspect_error:
        page.screenshot(
            path="debug_aspect_9_16_not_found.png",
            full_page=True
        )

        raise RuntimeError(
            "9:16 toggle was not found or visible. "
            "Saved debug_aspect_9_16_not_found.png"
        ) from aspect_error

    aspect_checked = (
        aspect_9_16.get_attribute(
            "aria-checked"
        )
        == "true"
    )

    if aspect_checked:
        print("9:16 already selected")
    else:
        aspect_9_16.click(
            force=True
        )

        print("Selected 9:16")

    time.sleep(1)

    # ============================================================
    # Chọn model "Nano Banana Pro" (thay vì "Omni 1.1 Flash").
    # ============================================================
    model_trigger = page.locator(
        "button:has(span.model-select-trigger-content)"
    ).first

    if model_trigger.count() == 0:
        model_trigger = page.locator(
            '[aria-label="Select model family"], '
            '[aria-label="Chọn nhóm mô hình"]'
        ).first

    model_trigger.click(
        force=True
    )

    print("Opened model dropdown")

    time.sleep(1)

    page.locator(
        "button[mat-menu-item]"
    ).filter(
        has_text="Nano Banana Pro"
    ).click(
        force=True
    )

    print("Selected Nano Banana Pro")

    time.sleep(1)

    # Không chọn 720p (đó là độ phân giải riêng của Video),
    # nhưng vẫn cần chọn "x1" (số lượng ảnh tạo ra mỗi lần) -
    # cùng dạng mat-button-toggle như bên Video.
    x1_toggle = page.locator(
        "button.mat-button-toggle-button"
    ).filter(
        has_text=re.compile(
            r"^\s*x1\s*$"
        )
    ).first

    try:
        x1_toggle.wait_for(
            state="visible",
            timeout=30000
        )

    except Exception as x1_error:
        page.screenshot(
            path="debug_x1_not_found.png",
            full_page=True
        )

        raise RuntimeError(
            "x1 toggle was not found or visible. "
            "Saved debug_x1_not_found.png"
        ) from x1_error

    x1_checked = (
        x1_toggle.get_attribute(
            "aria-checked"
        )
        == "true"
    )

    if x1_checked:
        print("x1 already selected")
    else:
        x1_toggle.click(
            force=True
        )

        print("Selected x1")

    time.sleep(1)




# ─────────────────────────────────────────────
# Dán ảnh trực tiếp vào ô prompt (KHÔNG dùng hộp thoại
# Windows nữa) - copy file ảnh vào clipboard hệ điều hành
# rồi Ctrl+V thẳng vào ô prompt, giống cách worker ChatGPT
# cũ của bạn làm.
# ─────────────────────────────────────────────

INGREDIENT_CHIP_SELECTOR = (
    "flow-ingredient-bar "
    "button.chip-container[aria-label='Ingredient']"
)


def copy_image_to_clipboard(image_path):
    """
    Copy file ảnh vào clipboard Windows (giống thao tác
    "Copy" 1 file ảnh trong Explorer), để có thể Ctrl+V dán
    thẳng vào ô prompt của Flow.
    """

    image_path = os.path.abspath(image_path)

    powershell_cmd = (
        "Set-Clipboard -LiteralPath "
        f"'{image_path}'"
    )

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            powershell_cmd
        ],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise Exception(
            "Cannot copy image to clipboard "
            f"({image_path}): {result.stderr.strip()}"
        )


def wait_ingredient_chips_ready(
    page,
    expected_count,
    timeout_rounds=60
):
    """
    Chờ các "ingredient chip" (thẻ ảnh dán vào ô prompt) load
    xong. Dựa theo mã HTML thực tế:
        button.chip-container[aria-label="Ingredient"]
            [aria-busy="false"]
          > div.chip-image-wrapper > img.chip-image[src^=http]
    """

    last_ready_count = -1
    stable_rounds = 0

    for i in range(timeout_rounds):
        debug_info = page.evaluate(
            f"""
            () => {{
                const chips = document.querySelectorAll(
                    "{INGREDIENT_CHIP_SELECTOR}"
                );

                let ready = 0;

                chips.forEach((chip) => {{
                    const busy = (
                        chip.getAttribute('aria-busy')
                    );

                    const img = chip.querySelector(
                        'img.chip-image'
                    );

                    const src = img
                        ? (img.getAttribute('src') || '')
                        : '';

                    const imgReady = (
                        img
                        && src.startsWith('http')
                        && img.complete
                        && img.naturalWidth > 0
                    );

                    if (busy !== 'true' && imgReady) {{
                        ready += 1;
                    }}
                }});

                return {{
                    total: chips.length,
                    ready: ready
                }};
            }}
            """
        )

        total = debug_info.get("total", 0)
        ready_count = debug_info.get("ready", 0)

        print(
            f"Ingredient chips ready: "
            f"{ready_count}/{expected_count} "
            f"(trong DOM: {total})"
        )

        if (
            total >= expected_count
            and ready_count >= expected_count
        ):
            if ready_count == last_ready_count:
                stable_rounds += 1
            else:
                stable_rounds = 0

            last_ready_count = ready_count

            if stable_rounds >= 2:
                print("Ingredient chips stable.")
                return

        else:
            stable_rounds = 0
            last_ready_count = ready_count

        time.sleep(1.5)

    page.screenshot(
        path="debug_ingredient_chips_timeout.png",
        full_page=True
    )

    raise Exception(
        f"Timeout waiting for ingredient chips. "
        f"Expected {expected_count}, got "
        f"{last_ready_count} ready. Saved "
        f"debug_ingredient_chips_timeout.png"
    )


def focus_prompt_box(page, prompt_box):
    """
    Focus THẬT vào ô prompt (ProseMirror).

    Lý do cần hàm riêng: khi ô prompt đang trống, span
    "prosemirror-placeholder" (hiện chữ "What do you want to
    create?") nằm đè lên trên ô contenteditable. Một cú click
    chuột thông thường (kể cả .click(force=True) của Playwright)
    vẫn là 1 real mouse click tại toạ độ tâm phần tử - nếu
    placeholder đang che đúng điểm đó, trình duyệt sẽ tính điểm
    click đó là trúng vào placeholder (span, không phải
    contenteditable), nên ô prompt KHÔNG nhận focus bàn phím và
    Ctrl+V sau đó không dán vào đâu cả / dán sai chỗ.

    Cách sửa: click trước (để đóng placeholder / trigger UI nếu
    có), sau đó gọi thẳng el.focus() bằng JS để đảm bảo focus rơi
    đúng vào contenteditable, rồi verify bằng document.activeElement.
    """

    try:
        prompt_box.click(
            force=True,
            timeout=2000
        )
    except Exception:
        pass

    prompt_box.evaluate(
        "(el) => el.focus()"
    )

    time.sleep(0.2)

    is_focused = prompt_box.evaluate(
        "(el) => document.activeElement === el"
    )

    if not is_focused:
        page.screenshot(
            path="debug_prompt_box_not_focused.png",
            full_page=True
        )

        raise Exception(
            "Prompt box khong nhan focus sau khi click/focus(). "
            "Saved debug_prompt_box_not_focused.png"
        )


def paste_images_into_prompt(
    page,
    prompt_box,
    image_paths
):
    """
    Dán từng ảnh trực tiếp vào ô prompt bằng clipboard
    (Ctrl+V), không mở hộp thoại Windows. Chờ ảnh load xong
    (ingredient chip) trước khi dán ảnh tiếp theo / dán prompt
    text.
    """

    for image_path in image_paths:
        if not os.path.exists(image_path):
            raise FileNotFoundError(
                f"Missing reference image: {image_path}"
            )

    for index, image_path in enumerate(image_paths):
        copy_image_to_clipboard(image_path)

        focus_prompt_box(page, prompt_box)

        time.sleep(0.3)

        pyautogui.hotkey(
            "ctrl",
            "v"
        )

        print(
            f"Pasted image {index + 1}/"
            f"{len(image_paths)}: "
            f"{os.path.basename(image_path)}"
        )

        time.sleep(1)

        # Chờ chip của ảnh vừa dán load xong trước khi dán
        # ảnh tiếp theo, tránh dán chồng khi ảnh trước chưa
        # kịp xử lý.
        wait_ingredient_chips_ready(
            page,
            expected_count=index + 1
        )

    print(
        f"{len(image_paths)} image(s) pasted into prompt: "
        f"{[os.path.basename(p) for p in image_paths]}"
    )


# ─────────────────────────────────────────────
# Tạo 1 ảnh
# ─────────────────────────────────────────────

def create_image_job(
    page,
    image_paths,
    prompt_text
):
    print("\n--- Creating Image ---")

    # GIỮ NGUYÊN SELECTOR INSPECT.
    # Chỉ lấy ProseMirror đang thực sự hiển thị.
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

    # Dán ảnh trực tiếp vào ô prompt (không mở hộp thoại
    # Windows nữa), chờ load xong từng ảnh.
    paste_images_into_prompt(
        page,
        prompt_box,
        image_paths
    )

    focus_prompt_box(page, prompt_box)

    time.sleep(0.5)

    pyperclip.copy(
        prompt_text
    )

    pyautogui.hotkey(
        "ctrl",
        "v"
    )

    time.sleep(2)

    pasted_text = prompt_box.inner_text().strip()

    if not pasted_text:
        page.screenshot(
            path="debug_prompt_box_empty.png",
            full_page=True
        )

        raise Exception(
            "Prompt box vẫn trống sau khi dán. Saved "
            "debug_prompt_box_empty.png"
        )

    print(
        f"Pasted prompt "
        f"(verified {len(pasted_text)} ký tự)"
    )

    time.sleep(2)

    # Nút Create/Generate - GIỮ NGUYÊN selector fallback
    # theo thứ tự ưu tiên từ render_worker_2.py.
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

        print("Waiting for Create button to become enabled...")

        time.sleep(2)

    # Chụp lại toàn bộ data-media-id đang có trên canvas NGAY
    # TRƯỚC khi bấm Create. Hàng flow-grid-tile-container chứa
    # CẢ ảnh reference vừa dán vào prompt (ingredient) lẫn ảnh
    # sẽ được generate, nên không thể giả định card cuối cùng
    # trong DOM luôn là ảnh mới. Baseline này dùng để xác định
    # đúng card mới xuất hiện sau khi generate xong.
    existing_media_ids = get_current_media_ids(page)

    print(
        "Media ids truoc khi bam Create: "
        f"{len(existing_media_ids)}"
    )

    create_button.click(
        force=True
    )

    print("Clicked Create")

    # Không cần bấm vào tab Video sau khi send prompt (khác
    # với render worker) - ảnh sẽ tự hiện trong grid.
    time.sleep(5)

    return existing_media_ids


# ─────────────────────────────────────────────
# Chờ + chọn đúng thẻ ảnh vừa tạo + tải xuống 2K
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# Xác định đúng card MỚI generate (không dựa vào index
# cuối cùng trong DOM, vì ảnh reference dùng làm ingredient
# cũng hiện thành flow-grid-tile-container trên canvas).
# ─────────────────────────────────────────────

def get_current_media_ids(page):
    """
    Lấy toàn bộ data-media-id của các ảnh đang hiển thị trong
    flow-grid-tile-container (bao gồm cả ảnh reference/ingredient
    lẫn ảnh đã generate trước đó).
    """

    return page.evaluate(
        """
        () => {
            const ids = [];

            document.querySelectorAll(
                "flow-grid-tile-container img.image[data-media-id]"
            ).forEach((img) => {
                ids.push(
                    img.getAttribute("data-media-id")
                );
            });

            return ids;
        }
        """
    )


def wait_for_new_generated_card(
    page,
    existing_media_ids,
    timeout_rounds=120
):
    """
    Sau khi bấm Create, tìm đúng flow-grid-tile-container có
    data-media-id CHƯA từng có trong existing_media_ids (chụp
    trước khi bấm Create) và ảnh đã load xong. Trả về index của
    card đó trong danh sách flow-grid-tile-container hiện tại,
    để dùng cho wait_and_download_image_card().
    """

    last_info = None

    for attempt in range(timeout_rounds):
        time.sleep(2)

        info = page.evaluate(
            """
            (existingIds) => {
                const existing = new Set(existingIds);

                const cards = document.querySelectorAll(
                    "flow-grid-tile-container"
                );

                for (let i = 0; i < cards.length; i++) {
                    const card = cards[i];

                    const img = card.querySelector(
                        "img.image[data-media-id]"
                    );

                    if (!img) {
                        continue;
                    }

                    const id = img.getAttribute(
                        "data-media-id"
                    );

                    if (existing.has(id)) {
                        continue;
                    }

                    const src = (
                        img.getAttribute("src") || ""
                    );

                    const ready = (
                        src.startsWith("http")
                        && img.complete
                        && img.naturalWidth > 0
                    );

                    if (ready) {
                        return {
                            found: true,
                            index: i,
                            media_id: id
                        };
                    }

                    return {
                        found: false,
                        reason: "new_card_not_ready",
                        index: i,
                        media_id: id
                    };
                }

                return {
                    found: false,
                    reason: "no_new_card",
                    total_cards: cards.length
                };
            }
            """,
            existing_media_ids
        )

        last_info = info

        if info.get("found"):
            print(
                "New generated card found: "
                f"index={info['index']} "
                f"media_id={info['media_id']}"
            )

            return info["index"]

        print(
            f"  waiting for new card... "
            f"{attempt + 1}/{timeout_rounds} | {info}"
        )

    page.screenshot(
        path="debug_new_card_not_found.png",
        full_page=True
    )

    raise Exception(
        "Timeout waiting for new generated card "
        f"(chua thay data-media-id moi). last_info={last_info}. "
        "Saved debug_new_card_not_found.png"
    )


def wait_and_download_image_card(
    page,
    card_index,
    save_path
):
    # Card ảnh: <flow-grid-tile-container> > <flow-tile-container>
    # > <flow-image-tile> > <img class="image" data-media-id="...">
    IMAGE_CARD_SELECTOR = "flow-grid-tile-container"

    image_cards = page.locator(
        IMAGE_CARD_SELECTOR
    )

    count = image_cards.count()

    print(
        f"Found {count} image cards. "
        f"Targeting index {card_index}."
    )

    card = image_cards.nth(
        card_index
    )

    card.scroll_into_view_if_needed()

    time.sleep(0.5)

    box = card.bounding_box()

    if not box:
        raise Exception(
            f"Cannot get bounding box "
            f"of image card {card_index}"
        )

    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2

    print(
        f"Waiting for image card "
        f"{card_index} to be ready..."
    )

    # Tương tự render_worker_2.py: KHÔNG hover vào card khi
    # đang chờ (tránh preview làm card đổi kích thước/nội dung
    # liên tục, khiến check ready() sai).
    for attempt in range(120):
        time.sleep(2)

        debug_info = page.evaluate(
            f"""
            () => {{
                const cards =
                    document.querySelectorAll(
                        '{IMAGE_CARD_SELECTOR}'
                    );

                const card = cards[{card_index}];

                if (!card) {{
                    return {{
                        ready: false,
                        reason: 'card_not_found',
                        total_cards: cards.length
                    }};
                }}

                const thumb = card.querySelector(
                    'img.image'
                );

                if (!thumb) {{
                    return {{
                        ready: false,
                        reason: 'thumb_not_found',
                        total_cards: cards.length,
                        card_html: (
                            card.outerHTML || ''
                        ).slice(0, 500)
                    }};
                }}

                const src = (
                    thumb.getAttribute('src') || ''
                );

                const ready = (
                    src.startsWith('http')
                    && thumb.complete
                    && thumb.naturalWidth > 0
                );

                return {{
                    ready: ready,
                    reason: 'checked',
                    total_cards: cards.length,
                    src_prefix: src.slice(0, 40)
                }};
            }}
            """
        )

        ready = debug_info.get("ready", False)

        if ready:
            print(f"Image card {card_index} ready.")
            break

        print(
            f"  waiting... "
            f"{attempt + 1}/120 | "
            f"reason={debug_info.get('reason')} "
            f"total_cards={debug_info.get('total_cards')} "
            f"src={debug_info.get('src_prefix', '')!r}"
        )

        if debug_info.get("reason") == "thumb_not_found":
            print(
                "  card_html: "
                f"{debug_info.get('card_html', '')}"
            )

    else:
        page.screenshot(
            path="debug_image_card_not_ready.png",
            full_page=True
        )

        raise Exception(
            f"Timeout waiting for "
            f"image card {card_index}. "
            f"Saved debug_image_card_not_ready.png"
        )

    time.sleep(1)

    page.mouse.move(cx, cy)

    time.sleep(1)

    page.mouse.click(
        cx,
        cy,
        button="right"
    )

    print(f"Right clicked image card {card_index}")

    time.sleep(2)

    # Click "Tải xuống" / "Download" trong context menu.
    page.locator(
        "button[mat-menu-item]"
    ).filter(
        has=page.locator(
            "mat-icon:text('download')"
        )
    ).click(
        force=True
    )

    print("Clicked Tải xuống")

    time.sleep(2)

    # Download 1K và chỉ return sau khi file đã được save
    # thành công. Browser chỉ được đóng sau khi hàm này return.
    with page.expect_download(timeout=300000) as dl_info:
        page.locator(
            "button[mat-menu-item]"
        ).filter(
            has=page.locator(
                "span.label"
            ).filter(
                has_text=re.compile(r"^\s*1K\s*$")
            )
        ).first.click(force=True)

        print(
            "Clicked 1K (Original size), "
            "waiting for download to finish..."
        )

    download = dl_info.value

    # save_as chạy khi browser/context vẫn còn sống.
    try:
        download.save_as(save_path)
    except Exception as save_error:
        print(
            "LOI KHI LUU DOWNLOAD - browser/context co the "
            "da bi dong truoc khi save_as. Chi tiet:",
            save_error
        )
        raise

    # Chỉ return khi file đã thực sự tồn tại và có dữ liệu.
    if not os.path.exists(save_path):
        raise Exception(
            f"Download completed but file was not found: {save_path}"
        )

    file_size = os.path.getsize(save_path)

    if file_size <= 0:
        raise Exception(
            f"Downloaded file is empty: {save_path}"
        )

    print(
        f"Saved: {save_path} "
        f"({file_size:,} bytes)"
    )



# ─────────────────────────────────────────────
# Render 1 job ảnh trong 1 session riêng biệt
# ─────────────────────────────────────────────

def generate_single_image(
    category,
    input_paths,
    prompt_text,
    save_path
):
    print("=" * 60)

    print(
        f"Generating image: {category} "
        f"| inputs: {[os.path.basename(p) for p in input_paths]}"
    )

    global _is_first_browser_launch_in_run

    with sync_playwright() as p:
        profile_dir = get_next_image_profile()

        print(
            f"Using image profile: {profile_dir}"
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
                    "--disable-features="
                    "CalculateNativeWinOcclusion",
                    "--disable-backgrounding-"
                    "occluded-windows",
                    "--disable-renderer-"
                    "backgrounding",
                    "--disable-background-"
                    "timer-throttling",
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

            page.bring_to_front()

            page.goto(
                FLOW_URL,
                wait_until="domcontentloaded",
                timeout=120000
            )

            print("Waiting Google Flow load...")

            time.sleep(5)

            dismiss_possible_ad_overlay(page)

            setup_new_project_image(page)

            existing_media_ids = create_image_job(
                page=page,
                image_paths=input_paths,
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
                    path="debug_unusual_activity_image.png",
                    full_page=True
                )

                raise Exception("UNUSUAL_ACTIVITY")

            # Không cần bấm filter sidebar cho ảnh (khác với
            # render worker phải lọc theo "Videos").

            # KHÔNG dùng total_cards - 1 nữa: hàng
            # flow-grid-tile-container chứa CẢ ảnh reference
            # vừa dán vào prompt (ingredient) lẫn ảnh vừa
            # generate, nên card cuối cùng trong DOM không chắc
            # là ảnh mới. Xác định đúng card mới bằng
            # data-media-id chưa từng thấy trước khi bấm Create.
            new_card_index = wait_for_new_generated_card(
                page,
                existing_media_ids
            )

            wait_and_download_image_card(
                page,
                card_index=new_card_index,
                save_path=save_path
            )

            print(f"Image downloaded: {save_path}")

            return profile_dir

        finally:
            print(
                "Closing browser AFTER download has been "
                "saved and verified."
            )
            browser.close()


# ─────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────

while True:
    rows = load_queue()

    pending_jobs = get_pending_jobs(rows)

    if not pending_jobs:
        print("=" * 60)
        print("No pending image jobs left. Done.")
        break

    job = pending_jobs[0]

    job_id = job["job_id"]

    category = (
        job.get("category")
        or ""
    ).strip()

    product_id = job.get("product_id", "")

    channel_id = job.get("channel_id", "")

    step = (
        job.get("step")
        or ""
    ).strip()

    input_1 = resolve_project_path(
        job.get("input_1", "")
    )

    input_2 = resolve_project_path(
        job.get("input_2", "")
    )

    output_path = resolve_project_path(
        job.get("output", "")
    )

    print("=" * 60)

    print(
        f"Next job: {job_id} "
        f"| category: {category} "
        f"| product: {product_id} "
        f"| channel: {channel_id} "
        f"| step: {step}"
    )

    rows = mark_job_status(
        rows,
        job_id,
        "processing"
    )

    save_queue(rows)

    try:
        if not category:
            raise ValueError(
                f"Missing category for job: {job_id}"
            )

        if not input_1 or not os.path.exists(input_1):
            raise FileNotFoundError(
                f"Missing input_1: {input_1}"
            )

        input_paths = [input_1]

        if input_2:
            if not os.path.exists(input_2):
                raise FileNotFoundError(
                    f"Missing input_2: {input_2}"
                )

            input_paths.append(input_2)

        if not step:
            raise ValueError(
                f"Missing step for job: {job_id}"
            )

        if not output_path:
            raise ValueError(
                f"Missing output for job: {job_id}"
            )

        prompt_file = get_prompt_path(
            category,
            step
        )

        prompt_text = read_prompt(prompt_file)

        os.makedirs(
            os.path.dirname(output_path),
            exist_ok=True
        )

        profile_used = generate_single_image(
            category=category,
            input_paths=input_paths,
            prompt_text=prompt_text,
            save_path=output_path
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
            error="",
            attempts=str(attempts)
        )

        save_queue(rows)

        print(f"Job done: {job_id}")

        # Không nghỉ giữa các job.
        # Sau khi hoàn thành ảnh, chuyển ngay sang job tiếp theo.

    except Exception as e:
        error_text = str(e)

        print(f"Job failed: {job_id}")
        print("Error:", error_text)

        rows = load_queue()

        attempts = (
            int(
                job.get("attempts")
                or 0
            )
            + 1
        )

        if error_text == "UNUSUAL_ACTIVITY":
            # Profile hiện tại đã được add vào
            # image_blocked_profiles.txt trong generate_single_image().
            #
            # Không fail job và không dừng batch.
            # Đưa job về pending để vòng lặp tiếp theo lấy profile
            # kế tiếp thông qua get_next_image_profile().
            rows = mark_job_status(
                rows,
                job_id,
                "pending",
                attempts=str(attempts - 1),
                error=(
                    "Unusual activity detected. "
                    "Current profile was blocked for today. "
                    "Retrying with next profile."
                )
            )

            save_queue(rows)

            print(
                "Unusual activity detected. "
                "Current profile blocked. "
                "Moving to next profile."
            )

            time.sleep(5)

            continue

        new_status = (
            "failed"
            if attempts >= 3
            else "pending"
        )

        rows = mark_job_status(
            rows,
            job_id,
            new_status,
            attempts=str(attempts),
            error=error_text
        )

        save_queue(rows)

        time.sleep(5)


print("Batch image generation finished.")