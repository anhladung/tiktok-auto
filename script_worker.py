from playwright.sync_api import sync_playwright
import csv
import os
import time
import pyautogui
import pyperclip


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

CHATGPT_URL = (
    "https://chatgpt.com/"
    "g/g-p-6a59ccfe43208191a8a880795664b046/project"
)
CHATGPT_PROFILE_DIR = (
    r"C:\chatgpt_auto_profile"
)

QUEUE_FILE = os.path.join(
    BASE_DIR,
    "queue",
    "script_queue.csv"
)

MAX_ATTEMPTS = 3

MAX_WAIT_SCRIPT_SECONDS = 300
RESPONSE_STABLE_ROUNDS = 3
RESPONSE_POLL_SECONDS = 2
MIN_SCRIPT_CHARACTERS = 30

RESTART_BROWSER_AFTER_EACH_SCRIPT = True
BROWSER_RESTART_DELAY_SECONDS = 8


# =========================
# PATH HANDLING
# =========================

def resolve_path(path):
    """
    Hỗ trợ cả đường dẫn tương đối và tuyệt đối.

    Ví dụ tương đối:
    products/sandal/SDL001/images/ai/02_product_closeup.png
    products/keychain/KC001/images/ai/02_backpack_swing.png

    Ví dụ tuyệt đối:
    C:\\project\\products\\sandal\\SDL001\\...
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


def file_exists_and_not_empty(path):
    return (
        os.path.isfile(path)
        and os.path.getsize(path) > 0
    )


def get_script_input_images(
    category,
    image_1,
    image_2
):
    """
    Chọn ảnh thực sự sẽ upload cho từng category.

    Quy tắc mới:
    - lipstick:
        vẫn giữ 2 ảnh như queue.
    - sandal:
        chỉ dùng 1 ảnh cầm sản phẩm trên tay:
        01_hand_holding.png
    - keychain:
        chỉ dùng 1 ảnh cầm sản phẩm trên tay:
        03_hand_holding.png

    Nếu queue vẫn còn image_1 / image_2 cũ thì worker
    sẽ tự suy ra đúng ảnh cần dùng từ cùng folder.
    """

    category = str(
        category or ""
    ).strip().lower()

    image_1 = resolve_path(
        image_1
    )

    image_2 = resolve_path(
        image_2
    )

    reference_path = (
        image_1
        or image_2
    )

    if not reference_path:
        raise ValueError(
            "Missing image paths in queue."
        )

    base_dir = os.path.dirname(
        reference_path
    )

    if category == "snack":
        selected_images = [
            image_1
        ]

    elif category == "keychain":
        selected_images = [
            os.path.join(
                base_dir,
                "03_hand_holding.png"
            )
        ]

    else:
        # Category khác giữ hành vi cũ.
        selected_images = [
            path
            for path in [
                image_1,
                image_2
            ]
            if path
        ]

    # Loại path rỗng/trùng.
    cleaned_images = []

    for path in selected_images:
        normalized = resolve_path(
            path
        )

        if (
            normalized
            and normalized
            not in cleaned_images
        ):
            cleaned_images.append(
                normalized
            )

    if not cleaned_images:
        raise ValueError(
            f"No input image selected for category: "
            f"{category}"
        )

    for path in cleaned_images:
        if not file_exists_and_not_empty(
            path
        ):
            raise FileNotFoundError(
                f"Selected input image not found "
                f"or empty: {path}"
            )

    return cleaned_images


# =========================
# QUEUE HANDLING
# =========================

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
        "status",
        "attempts",
        "prompt_file",
        "image_1",
        "image_2",
        "output",
        "error"
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


def update_job(job_id, **updates):
    rows = load_queue()

    job_found = False

    for row in rows:
        if row["job_id"] == job_id:
            for key, value in updates.items():
                row[key] = str(value)

            job_found = True
            break

    if not job_found:
        raise KeyError(
            f"Job not found: {job_id}"
        )

    save_queue(rows)


def get_next_job():
    rows = load_queue()

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

    return (
        pending[0]
        if pending
        else None
    )


# =========================
# IMAGE UPLOAD
# =========================

def upload_images(
    page,
    image_paths
):
    """
    Upload 1 hoặc 2 ảnh từ script_queue.csv.

    Quy tắc hiện tại:
    - lipstick: 2 ảnh
    - sandal: 1 ảnh cầm sản phẩm trên tay
    - keychain: 1 ảnh cầm sản phẩm trên tay
    """

    if isinstance(
        image_paths,
        str
    ):
        image_paths = [
            image_paths
        ]

    resolved_images = [
        resolve_path(path)
        for path in image_paths
        if str(path or "").strip()
    ]

    if not resolved_images:
        raise ValueError(
            "No image selected for upload."
        )

    for path in resolved_images:
        if not file_exists_and_not_empty(
            path
        ):
            raise FileNotFoundError(
                f"Image not found or empty: "
                f"{path}"
            )

    image_dirs = {
        os.path.normcase(
            os.path.dirname(path)
        )
        for path in resolved_images
    }

    if len(image_dirs) != 1:
        raise ValueError(
            "All selected images must be "
            "in the same folder."
        )

    base_image_dir = os.path.dirname(
        resolved_images[0]
    )

    page.locator(
        'button[data-testid="composer-plus-btn"]'
    ).click(
        force=True
    )

    time.sleep(2)

    page.get_by_text(
        "Add photos & files",
        exact=True
    ).click(
        force=True
    )

    time.sleep(3)

    pyautogui.hotkey(
        "ctrl",
        "l"
    )

    time.sleep(0.5)

    pyperclip.copy(
        base_image_dir
    )

    pyautogui.hotkey(
        "ctrl",
        "v"
    )

    pyautogui.press(
        "enter"
    )

    time.sleep(2)

    file_names_text = " ".join(
        f'"{os.path.basename(path)}"'
        for path in resolved_images
    )

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

    pyautogui.press(
        "enter"
    )

    time.sleep(3)

    print(
        "Uploaded images:"
    )

    for index, path in enumerate(
        resolved_images,
        start=1
    ):
        print(
            f"  Image {index}:",
            path
        )


# =========================
# GET CHATGPT RESPONSE
# =========================

def get_assistant_message_count(page):
    return page.locator(
        "div[data-message-author-role='assistant']"
    ).count()


def normalize_response_text(value):
    return " ".join(
        str(value or "")
        .strip()
        .lower()
        .split()
    )


def is_temporary_assistant_status(text):
    normalized = normalize_response_text(
        text
    )

    if not normalized:
        return True

    temporary_phrases = [
        "analyzing images",
        "analysing images",
        "analyzing image",
        "analysing image",
        "processing images",
        "processing image",
        "đang phân tích hình ảnh",
        "đang phân tích ảnh",
        "thinking",
        "đang suy nghĩ",
        "working on it",
    ]

    return any(
        phrase in normalized
        for phrase in temporary_phrases
    )


def is_chatgpt_generating(page):
    selectors = [
        "button[data-testid='stop-button']",
        "button[aria-label='Stop generating']",
        "button[aria-label='Dừng tạo']",
        "button[aria-label='Stop']",
    ]

    for selector in selectors:
        locator = page.locator(
            selector
        )

        try:
            count = locator.count()
        except Exception:
            count = 0

        for index in range(count):
            try:
                if locator.nth(index).is_visible():
                    return True
            except Exception:
                continue

    return False


def get_latest_assistant_text(
    page,
    before_count,
    timeout=MAX_WAIT_SCRIPT_SECONDS
):
    start_time = time.time()
    new_message_detected = False
    last_final_candidate = ""
    stable_count = 0

    while time.time() - start_time < timeout:
        messages = page.locator(
            "div[data-message-author-role='assistant']"
        )

        current_count = messages.count()

        print(
            "Assistant messages:",
            current_count,
            "| Before send:",
            before_count
        )

        if current_count <= before_count:
            time.sleep(
                RESPONSE_POLL_SECONDS
            )
            continue

        if not new_message_detected:
            print(
                "New assistant message detected."
            )
            new_message_detected = True

        try:
            current_text = (
                messages
                .nth(before_count)
                .inner_text(
                    timeout=10000
                )
                .strip()
            )
        except Exception:
            current_text = (
                messages
                .last
                .inner_text(
                    timeout=10000
                )
                .strip()
            )

        if is_temporary_assistant_status(
            current_text
        ):
            print(
                "Temporary assistant status:",
                normalize_response_text(
                    current_text
                )[:120]
            )

            last_final_candidate = ""
            stable_count = 0

            time.sleep(
                RESPONSE_POLL_SECONDS
            )
            continue

        if len(current_text) < MIN_SCRIPT_CHARACTERS:
            print(
                "Response is still too short:",
                len(current_text)
            )

            last_final_candidate = ""
            stable_count = 0

            time.sleep(
                RESPONSE_POLL_SECONDS
            )
            continue

        if is_chatgpt_generating(
            page
        ):
            print(
                "ChatGPT is still generating. "
                "Not saving yet."
            )

            last_final_candidate = (
                current_text
            )
            stable_count = 0

            time.sleep(
                RESPONSE_POLL_SECONDS
            )
            continue

        if current_text == last_final_candidate:
            stable_count += 1
        else:
            last_final_candidate = current_text
            stable_count = 0

        print(
            "Final candidate length:",
            len(current_text),
            "| Stable count:",
            stable_count,
            "/",
            RESPONSE_STABLE_ROUNDS
        )

        if stable_count >= RESPONSE_STABLE_ROUNDS:
            if is_temporary_assistant_status(
                current_text
            ):
                stable_count = 0
                time.sleep(
                    RESPONSE_POLL_SECONDS
                )
                continue

            if is_chatgpt_generating(
                page
            ):
                stable_count = 0
                time.sleep(
                    RESPONSE_POLL_SECONDS
                )
                continue

            print(
                "Final script response confirmed."
            )

            return current_text

        time.sleep(
            RESPONSE_POLL_SECONDS
        )

    if not new_message_detected:
        raise TimeoutError(
            "Không phát hiện assistant response mới "
            f"trong {timeout} giây."
        )

    raise TimeoutError(
        "ChatGPT chưa tạo xong script hợp lệ "
        f"trong {timeout} giây."
    )


# =========================
# BROWSER SESSION
# =========================

def open_chatgpt_browser(playwright):
    browser = (
        playwright.chromium
        .launch_persistent_context(
            user_data_dir=CHATGPT_PROFILE_DIR,
            headless=False,
            channel="chrome"
        )
    )

    if browser.pages:
        page = browser.pages[0]

        for extra_page in browser.pages[1:]:
            try:
                extra_page.close()
            except Exception:
                pass
    else:
        page = browser.new_page()

    page.goto(
        CHATGPT_URL,
        wait_until="domcontentloaded",
        timeout=120000
    )

    print(
        "Waiting ChatGPT..."
    )

    time.sleep(5)

    return browser, page


def close_chatgpt_browser(browser):
    if browser is None:
        return

    try:
        print(
            "Closing browser after script job..."
        )

        browser.close()

        print(
            "Browser closed."
        )

    except Exception as error:
        print(
            "Could not close browser:",
            error
        )


# =========================
# INIT JOB
# =========================

if not os.path.isfile(
    QUEUE_FILE
):
    print(
        f"Queue file not found: "
        f"{QUEUE_FILE}"
    )

    raise SystemExit


job = get_next_job()

if not job:
    print(
        "No script jobs left"
    )

    raise SystemExit


print(
    "Found job:",
    job["job_id"]
)


# =========================
# BROWSER
# =========================

with sync_playwright() as p:
    browser, page = open_chatgpt_browser(
        p
    )

    # =========================
    # MAIN LOOP
    # =========================

    while job:
        job_id = (
            job["job_id"]
        )

        # Category được lấy trực tiếp từ queue.
        # Không giới hạn riêng lipstick/sandal,
        # vì vậy keychain được xử lý bằng cùng core worker.
        category = (
            job.get("category")
            or ""
        ).strip()

        product_id = (
            job["product_id"]
        )

        prompt_file = resolve_path(
            job.get("prompt_file")
            or ""
        )

        image_1 = resolve_path(
            job.get("image_1")
            or ""
        )

        image_2 = resolve_path(
            job.get("image_2")
            or ""
        )

        output_path = resolve_path(
            job.get("output")
            or ""
        )

        if not category:
            update_job(
                job_id,
                status="failed",
                error="missing category"
            )

            job = get_next_job()
            continue

        if not file_exists_and_not_empty(
            prompt_file
        ):
            update_job(
                job_id,
                status="failed",
                error=(
                    "missing or empty prompt: "
                    f"{prompt_file}"
                )
            )

            job = get_next_job()
            continue

        try:
            selected_images = (
                get_script_input_images(
                    category=category,
                    image_1=image_1,
                    image_2=image_2
                )
            )

        except Exception as image_error:
            update_job(
                job_id,
                status="failed",
                error=str(image_error)
            )

            job = get_next_job()
            continue

        if not output_path:
            update_job(
                job_id,
                status="failed",
                error="missing output path"
            )

            job = get_next_job()
            continue

        with open(
            prompt_file,
            "r",
            encoding="utf-8-sig"
        ) as f:
            prompt = f.read()

        print("=" * 50)

        print(
            "Running:",
            job_id
        )

        print(
            "Category:",
            category
        )

        print(
            "Multi-category worker:",
            "lipstick / sandal / keychain"
        )

        print(
            "Product:",
            product_id
        )

        print(
            "Prompt:",
            prompt_file
        )

        print(
            "Image 1:",
            image_1
        )

        print(
            "Image 2:",
            image_2
        )

        print(
            "Selected upload images:",
            selected_images
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
            # =========================
            # UPLOAD IMAGES
            # =========================

            upload_images(
                page,
                selected_images
            )

            time.sleep(5)

            # =========================
            # FILL PROMPT
            # =========================

            # Không dùng pyautogui Ctrl+V cho prompt.
            # Pyautogui phụ thuộc focus của Windows nên đôi khi
            # dán nhầm prompt vào thanh URL.
            page.bring_to_front()

            prompt_box = page.locator(
                "#prompt-textarea"
            ).first

            prompt_box.wait_for(
                state="visible",
                timeout=60000
            )

            prompt_box.scroll_into_view_if_needed()

            prompt_box.click(
                force=True
            )

            time.sleep(0.5)

            # Điền trực tiếp vào đúng composer bằng Playwright.
            prompt_box.fill(
                prompt,
                timeout=60000
            )

            # Xác nhận prompt thật sự đã được đưa vào composer.
            inserted_prompt = (
                prompt_box
                .inner_text(
                    timeout=10000
                )
                .strip()
            )

            if not inserted_prompt:
                raise RuntimeError(
                    "Prompt textarea is empty after fill."
                )

            print(
                "Filled prompt directly into ChatGPT composer"
            )

            time.sleep(1)

            # =========================
            # SEND
            # =========================

            # Ghi nhận số phản hồi assistant trước khi
            # gửi prompt mới để không lấy nhầm script cũ.
            assistant_count_before_send = (
                get_assistant_message_count(
                    page
                )
            )

            print(
                "Assistant messages before send:",
                assistant_count_before_send
            )

            page.locator(
                'button[data-testid="send-button"]'
            ).click(
                force=True
            )

            print(
                "Sent"
            )

            # =========================
            # WAIT + GET RESPONSE
            # =========================

            latest_text = (
                get_latest_assistant_text(
                    page,
                    before_count=(
                        assistant_count_before_send
                    ),
                    timeout=MAX_WAIT_SCRIPT_SECONDS
                )
            )

            print(
                "Got response"
            )

            # =========================
            # SAVE OUTPUT
            # =========================

            output_dir = os.path.dirname(
                output_path
            )

            os.makedirs(
                output_dir,
                exist_ok=True
            )

            with open(
                output_path,
                "w",
                encoding="utf-8"
            ) as f:
                f.write(
                    latest_text
                )

            print(
                "Saved:",
                output_path
            )

            update_job(
                job_id,
                status="done",
                output=output_path,
                error=""
            )

        except Exception as e:
            update_job(
                job_id,
                status="failed",
                error=str(e)
            )

            print(
                "FAILED:",
                job_id,
                e
            )

            time.sleep(5)

        # =========================
        # NEXT JOB
        # =========================

        job = get_next_job()

        if RESTART_BROWSER_AFTER_EACH_SCRIPT:
            close_chatgpt_browser(
                browser
            )

            browser = None
            page = None

            time.sleep(
                BROWSER_RESTART_DELAY_SECONDS
            )

            if job is not None:
                print(
                    "Opening a fresh browser "
                    "for the next script job..."
                )

                browser, page = (
                    open_chatgpt_browser(
                        p
                    )
                )

    if browser is not None:
        close_chatgpt_browser(
            browser
        )