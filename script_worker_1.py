from playwright.sync_api import sync_playwright
import csv
import os
import time
import re
import base64
import mimetypes


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

GEMINI_URL = (
    "https://gemini.google.com/app"
)

GEMINI_PROFILE_DIR = (
    r"C:\gemini_auto_profile"
)

CHROME_EXECUTABLE = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe"
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
    products/sandal/SDL001/images/ai/01_hand_holding.png
    products/keychain/KC001/images/ai/03_hand_holding.png
    products/mask/MSK001/images/raw/product/1.jpg

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

    Pipeline hiện tại:
    - lipstick:
        dùng 2 ảnh từ queue.
    - sandal:
        dùng 01_hand_holding.png.
    - keychain:
        dùng 03_hand_holding.png.
    - phone_case:
        dùng 01_clip_01_first_frame.png từ queue.
    - mask:
        dùng trực tiếp RAW PRODUCT từ image_1 của queue.

    Với mask, build_script_queue.py đã tự tìm file thật trong:
        products/mask/{product_id}/images/raw/product/

    Vì vậy script_worker không tự ghép tên file hoặc extension
    cho mask; chỉ dùng đúng path image_1 đã được queue cung cấp.
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

    if category == "lipstick":
        selected_images = [
            image_1,
            image_2,
        ]

    elif category == "sandal":
        selected_images = [
            os.path.join(
                base_dir,
                "01_hand_holding.png"
            )
        ]

    elif category == "keychain":
        selected_images = [
            os.path.join(
                base_dir,
                "03_hand_holding.png"
            )
        ]

    elif category == "phone_case":
        # Pipeline mới chỉ còn 2 frame / 1 clip.
        # build_script_queue.py đã đưa đúng Frame 01 vào image_1.
        selected_images = [
            image_1
        ]

    elif category == "mask":
        # Dùng trực tiếp ảnh RAW PRODUCT được build_script_queue.py
        # đưa vào image_1. Không tự đổi folder/tên file/extension.
        selected_images = [
            image_1
        ]

    else:
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
    """
    Ghi queue qua file tạm rồi replace atomically.

    Tránh trường hợp queue bị ghi dở hoặc status vừa cập nhật
    bị mất nếu worker/browser gặp lỗi đúng lúc đang save.
    """

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

    temporary_file = (
        QUEUE_FILE + ".temporary"
    )

    with open(
        temporary_file,
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

    os.replace(
        temporary_file,
        QUEUE_FILE
    )


def update_job(job_id, **updates):
    """
    Cập nhật một job và ghi lại queue.

    Sau khi save, caller có thể dùng verify_job_status()
    để xác nhận status đã thực sự persist xuống CSV.
    """

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


def verify_job_status(
    job_id,
    expected_status
):
    """
    Reload queue từ disk và xác nhận status của job.

    Không dựa vào dữ liệu đang giữ trong RAM.
    """

    expected_status = str(
        expected_status or ""
    ).strip().lower()

    rows = load_queue()

    for row in rows:
        if row.get("job_id") != job_id:
            continue

        actual_status = (
            row.get("status")
            or ""
        ).strip().lower()

        if actual_status != expected_status:
            raise RuntimeError(
                "Script queue status did not persist. "
                f"job_id={job_id} | "
                f"expected={expected_status} | "
                f"actual={actual_status}"
            )

        print(
            "Queue status verified:",
            job_id,
            "->",
            actual_status
        )

        return True

    raise KeyError(
        f"Job not found while verifying: {job_id}"
    )


def get_next_job():
    """
    Lấy job pending tiếp theo.

    FIX chống lặp:
    Nếu queue vẫn ghi pending nhưng file output script đã tồn tại
    và không rỗng, coi job đó là done và persist lại queue
    thay vì gửi prompt Gemini lần nữa.
    """

    rows = load_queue()

    queue_changed = False

    for row in rows:
        status = (
            row.get("status", "")
            .strip()
            .lower()
        )

        if status != "pending":
            continue

        output_path = resolve_path(
            row.get("output")
            or ""
        )

        if (
            output_path
            and file_exists_and_not_empty(
                output_path
            )
        ):
            row["status"] = "done"
            row["error"] = ""

            queue_changed = True

            print(
                "Recovered completed script job "
                "from existing output:",
                row.get("job_id"),
                "->",
                output_path
            )

    if queue_changed:
        save_queue(
            rows
        )

        # Reload từ disk để chắc chắn dùng trạng thái mới.
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
# GEMINI PROMPT + IMAGE UPLOAD
# =========================

def get_gemini_prompt_box(page):
    """
    Tìm ô prompt Gemini theo DOM mới.

    Gemini hiện dùng:
        div[data-test-id="textarea-inner"]
        rich-textarea
        div.ql-editor[contenteditable="true"][role="textbox"]

    Không phụ thuộc vào class Angular động (_ngcontent / ng-tns).

    Có fallback cho:
    - aria-label tiếng Việt: "Nhập câu lệnh cho Gemini"
    - aria-label tiếng Anh: "Enter a prompt for Gemini"
    - textbox contenteditable generic bên trong textarea-inner
    """

    candidates = [
        page.locator(
            'div[data-test-id="textarea-inner"] '
            'rich-textarea '
            'div.ql-editor[contenteditable="true"][role="textbox"]'
        ).first,

        page.locator(
            'div[data-test-id="textarea-inner"] '
            'div[contenteditable="true"][role="textbox"]'
        ).first,

        page.locator(
            'div[contenteditable="true"]'
            '[role="textbox"]'
            '[aria-label="Nhập câu lệnh cho Gemini"]'
        ).first,

        page.locator(
            'div[contenteditable="true"]'
            '[role="textbox"]'
            '[aria-label="Enter a prompt for Gemini"]'
        ).first,

        page.locator(
            'rich-textarea '
            'div[contenteditable="true"][role="textbox"]'
        ).first,
    ]

    last_error = None

    for index, prompt_box in enumerate(
        candidates,
        start=1
    ):
        try:
            prompt_box.wait_for(
                state="visible",
                timeout=12000
            )

            print(
                "Gemini prompt box found "
                f"with selector fallback #{index}"
            )

            return prompt_box

        except Exception as error:
            last_error = error
            continue

    raise RuntimeError(
        "Could not find Gemini prompt box with "
        "current DOM selectors. "
        f"Last error: {last_error}"
    )


def fill_gemini_prompt(
    page,
    prompt
):
    """
    Theo flow mới: dán prompt TRƯỚC khi upload ảnh.
    """

    page.bring_to_front()

    prompt_box = get_gemini_prompt_box(
        page
    )

    prompt_box.scroll_into_view_if_needed()

    prompt_box.click(
        force=True
    )

    time.sleep(0.5)

    prompt_box.fill(
        prompt,
        timeout=60000
    )

    inserted_prompt = (
        prompt_box
        .inner_text(
            timeout=10000
        )
        .strip()
    )

    if not inserted_prompt:
        raise RuntimeError(
            "Gemini prompt box is empty after fill."
        )

    print(
        "Filled prompt directly into Gemini composer"
    )


def image_file_to_data_url(image_path):
    """
    Đọc ảnh local và chuyển thành data URL.

    Browser sẽ decode ảnh rồi convert sang PNG trước khi
    đưa vào Clipboard API. Nhờ vậy ảnh raw .jpg/.jpeg/.webp
    của mask vẫn paste được vào Gemini.
    """

    resolved_path = resolve_path(
        image_path
    )

    if not file_exists_and_not_empty(
        resolved_path
    ):
        raise FileNotFoundError(
            f"Image not found or empty: "
            f"{resolved_path}"
        )

    mime_type, _ = mimetypes.guess_type(
        resolved_path
    )

    if not mime_type:
        mime_type = "image/png"

    with open(
        resolved_path,
        "rb"
    ) as f:
        encoded = base64.b64encode(
            f.read()
        ).decode(
            "ascii"
        )

    return (
        f"data:{mime_type};base64,"
        f"{encoded}"
    )


def copy_image_to_browser_clipboard(
    page,
    image_path
):
    """
    Copy một ảnh local vào clipboard của Chrome.

    Ảnh được decode trong browser bằng Image(),
    vẽ lên canvas, sau đó convert thành image/png Blob
    và ghi bằng navigator.clipboard.write().
    """

    data_url = image_file_to_data_url(
        image_path
    )

    page.evaluate(
        """
        async (dataUrl) => {
            const image = new Image();

            await new Promise((resolve, reject) => {
                image.onload = resolve;
                image.onerror = reject;
                image.src = dataUrl;
            });

            const canvas = document.createElement("canvas");
            canvas.width = image.naturalWidth;
            canvas.height = image.naturalHeight;

            const context = canvas.getContext("2d");

            if (!context) {
                throw new Error(
                    "Could not create 2D canvas context."
                );
            }

            context.drawImage(
                image,
                0,
                0
            );

            const pngBlob = await new Promise(
                (resolve, reject) => {
                    canvas.toBlob(
                        (blob) => {
                            if (blob) {
                                resolve(blob);
                            } else {
                                reject(
                                    new Error(
                                        "Could not convert image to PNG blob."
                                    )
                                );
                            }
                        },
                        "image/png"
                    );
                }
            );

            const clipboardItem = new ClipboardItem({
                "image/png": pngBlob
            });

            await navigator.clipboard.write([
                clipboardItem
            ]);
        }
        """,
        data_url
    )


def paste_images_into_prompt(
    page,
    image_paths
):
    """
    Paste trực tiếp 1 hoặc 2 ảnh vào prompt Gemini.

    Flow mới:
    1. Prompt text đã được điền trước.
    2. Copy từng ảnh vào clipboard của Chrome.
    3. Focus lại prompt box.
    4. Ctrl+V để paste ảnh trực tiếp vào composer.
    5. Không click Upload & tools / Files nữa.

    Pipeline ảnh:
    - lipstick: 2 ảnh
    - sandal: 1 ảnh 01_hand_holding.png
    - keychain: 1 ảnh 03_hand_holding.png
    - phone_case: 1 ảnh 01_clip_01_first_frame.png
    - mask: 1 ảnh RAW PRODUCT từ script_queue.csv
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
            "No image selected for paste."
        )

    for path in resolved_images:
        if not file_exists_and_not_empty(
            path
        ):
            raise FileNotFoundError(
                f"Image not found or empty: "
                f"{path}"
            )

    for index, image_path in enumerate(
        resolved_images,
        start=1
    ):
        print(
            f"Copying image {index} to browser clipboard:",
            image_path
        )

        copy_image_to_browser_clipboard(
            page,
            image_path
        )

        prompt_box = get_gemini_prompt_box(
            page
        )

        prompt_box.scroll_into_view_if_needed()

        prompt_box.click(
            force=True
        )

        time.sleep(0.5)

        page.keyboard.press(
            "Control+V"
        )

        print(
            f"Pasted image {index} directly into Gemini composer"
        )

        # Cho Gemini thời gian tạo attachment preview.
        time.sleep(4)

    print(
        "Finished pasting images directly into prompt."
    )


# =========================
# GET GEMINI RESPONSE
# =========================

def get_gemini_response_count(page):
    return page.locator(
        "structured-content-container"
        ".model-response-text"
    ).count()


def normalize_response_text(value):
    return " ".join(
        str(value or "")
        .strip()
        .lower()
        .split()
    )


def is_temporary_gemini_status(text):
    normalized = normalize_response_text(
        text
    )

    if not normalized:
        return True

    temporary_phrases = [
        "thinking",
        "analyzing",
        "analysing",
        "processing",
        "working on it",
        "đang suy nghĩ",
        "đang phân tích",
    ]

    return any(
        normalized == phrase
        or normalized.startswith(
            phrase + " "
        )
        for phrase in temporary_phrases
    )


def get_latest_gemini_text(
    page,
    before_count,
    timeout=MAX_WAIT_SCRIPT_SECONDS
):
    """
    Chỉ lấy response Gemini mới của job hiện tại.

    Response hoàn tất khi:
    - có structured-content-container mới;
    - text đủ dài;
    - aria-busy không còn true;
    - text ổn định liên tục nhiều vòng.
    """

    start_time = time.time()
    new_response_detected = False
    last_final_candidate = ""
    stable_count = 0

    while time.time() - start_time < timeout:
        responses = page.locator(
            "structured-content-container"
            ".model-response-text"
        )

        current_count = responses.count()

        print(
            "Gemini responses:",
            current_count,
            "| Before send:",
            before_count
        )

        if current_count <= before_count:
            time.sleep(
                RESPONSE_POLL_SECONDS
            )
            continue

        if not new_response_detected:
            print(
                "New Gemini response detected."
            )
            new_response_detected = True

        response = responses.nth(
            before_count
        )

        markdown = response.locator(
            "message-content div.markdown"
        ).first

        try:
            markdown.wait_for(
                state="visible",
                timeout=10000
            )

            current_text = (
                markdown
                .inner_text(
                    timeout=10000
                )
                .strip()
            )

        except Exception:
            try:
                current_text = (
                    response
                    .inner_text(
                        timeout=10000
                    )
                    .strip()
                )
            except Exception:
                time.sleep(
                    RESPONSE_POLL_SECONDS
                )
                continue

        if is_temporary_gemini_status(
            current_text
        ):
            print(
                "Temporary Gemini status:",
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

        try:
            aria_busy = markdown.get_attribute(
                "aria-busy"
            )
        except Exception:
            aria_busy = None

        if aria_busy == "true":
            print(
                "Gemini is still generating. "
                "Not saving yet."
            )

            last_final_candidate = current_text
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
            RESPONSE_STABLE_ROUNDS,
            "| aria-busy:",
            aria_busy
        )

        if stable_count >= RESPONSE_STABLE_ROUNDS:
            try:
                final_text = (
                    markdown
                    .inner_text(
                        timeout=10000
                    )
                    .strip()
                )
            except Exception:
                final_text = current_text

            if final_text != current_text:
                last_final_candidate = final_text
                stable_count = 0

                time.sleep(
                    RESPONSE_POLL_SECONDS
                )
                continue

            print(
                "Final Gemini script response confirmed."
            )

            return final_text

        time.sleep(
            RESPONSE_POLL_SECONDS
        )

    if not new_response_detected:
        raise TimeoutError(
            "Không phát hiện Gemini response mới "
            f"trong {timeout} giây."
        )

    raise TimeoutError(
        "Gemini chưa tạo xong script hợp lệ "
        f"trong {timeout} giây."
    )


def send_gemini_prompt(page):
    """
    Tìm và click nút Send của Gemini theo DOM mới.

    Ưu tiên:
    - data-test-id="send-button-container"
    - button chứa icon arrow_upward

    Fallback:
    - aria-label tiếng Việt: "Gửi tin nhắn"
    - aria-label tiếng Anh: "Send message"
    """

    candidates = [
        page.locator(
            'div[data-test-id="send-button-container"] '
            'button:has(mat-icon[data-mat-icon-name="arrow_upward"])'
        ).first,

        page.locator(
            'div[data-test-id="send-button-container"] '
            'button[aria-label="Gửi tin nhắn"]'
        ).first,

        page.locator(
            'button[aria-label="Gửi tin nhắn"]'
        ).first,

        page.locator(
            'button[aria-label="Send message"]'
        ).first,
    ]

    send_button = None
    last_error = None

    for index, candidate in enumerate(
        candidates,
        start=1
    ):
        try:
            candidate.wait_for(
                state="visible",
                timeout=12000
            )

            send_button = candidate

            print(
                "Gemini send button found "
                f"with selector fallback #{index}"
            )

            break

        except Exception as error:
            last_error = error
            continue

    if send_button is None:
        raise RuntimeError(
            "Could not find Gemini send button "
            "with current DOM selectors. "
            f"Last error: {last_error}"
        )

    start_time = time.time()

    while True:
        try:
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

            is_enabled = send_button.is_enabled()

            if (
                is_enabled
                and aria_disabled != "true"
                and disabled_attribute is None
            ):
                break

        except Exception:
            pass

        if time.time() - start_time > 120:
            raise TimeoutError(
                "Gemini send button did not become "
                "enabled within 120 seconds."
            )

        print(
            "Waiting Gemini send button..."
        )

        time.sleep(2)

    send_button.click(
        force=True
    )

    print(
        "Sent prompt to Gemini"
    )


# =========================
# BROWSER SESSION
# =========================

def open_gemini_browser(playwright):
    browser = (
        playwright.chromium
        .launch_persistent_context(
            user_data_dir=GEMINI_PROFILE_DIR,
            headless=False,
            executable_path=CHROME_EXECUTABLE,
            args=[
                "--window-size=1600,1000",
                "--window-position=0,0",
            ]
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

    try:
        browser.grant_permissions(
            [
                "clipboard-read",
                "clipboard-write",
            ],
            origin="https://gemini.google.com"
        )

        print(
            "Granted clipboard permissions for Gemini."
        )

    except Exception as permission_error:
        print(
            "Could not pre-grant clipboard permissions:",
            permission_error
        )

    page.goto(
        GEMINI_URL,
        wait_until="domcontentloaded",
        timeout=120000
    )

    print(
        "Waiting Gemini..."
    )

    time.sleep(7)

    get_gemini_prompt_box(
        page
    )

    print(
        "Gemini composer is ready."
    )

    return browser, page


def close_gemini_browser(browser):
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
    browser, page = open_gemini_browser(
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
        # Không giới hạn riêng lipstick/sandal.
        # keychain, phone_case và mask dùng cùng core worker.
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
            "lipstick / sandal / keychain / phone_case / mask"
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
            # FILL PROMPT FIRST
            # =========================

            fill_gemini_prompt(
                page,
                prompt
            )

            time.sleep(1)

            # =========================
            # PASTE IMAGES DIRECTLY
            # =========================

            paste_images_into_prompt(
                page,
                selected_images
            )

            time.sleep(3)

            # =========================
            # SEND
            # =========================

            response_count_before_send = (
                get_gemini_response_count(
                    page
                )
            )

            print(
                "Gemini responses before send:",
                response_count_before_send
            )

            send_gemini_prompt(
                page
            )

            # =========================
            # WAIT + GET RESPONSE
            # =========================

            latest_text = (
                get_latest_gemini_text(
                    page,
                    before_count=(
                        response_count_before_send
                    ),
                    timeout=MAX_WAIT_SCRIPT_SECONDS
                )
            )

            print(
                "Got Gemini response"
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

            # FIX chống tạo lặp:
            # reload script_queue.csv và xác nhận job đã thực sự
            # được persist thành done trước khi lấy job tiếp theo.
            verify_job_status(
                job_id,
                "done"
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
            close_gemini_browser(
                browser
            )

            browser = None
            page = None

            time.sleep(
                BROWSER_RESTART_DELAY_SECONDS
            )

            if job is not None:
                print(
                    "Opening a fresh Gemini browser "
                    "for the next script job..."
                )

                browser, page = (
                    open_gemini_browser(
                        p
                    )
                )

    if browser is not None:
        close_gemini_browser(
            browser
        )