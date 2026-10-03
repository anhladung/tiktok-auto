from __future__ import annotations

from playwright.sync_api import sync_playwright

from PIL import (
    Image,
    ImageOps,
    UnidentifiedImageError,
)

import csv
import hashlib
import os
import re
import time

from pathlib import Path


# ============================================================
# PROJECT ROOT
# ============================================================

def find_project_root() -> Path:

    current = Path(__file__).resolve()

    for parent in current.parents:

        if (
            (parent / "queue").exists()
            and
            (parent / "prompts").exists()
        ):
            return parent

    raise RuntimeError(
        "Could not find PROJECT_ROOT."
    )


PROJECT_ROOT = find_project_root()


# ============================================================
# PATHS
# ============================================================

CHATGPT_URL = (
    "https://chatgpt.com/"
    "g/g-p-6a59ccfe43208191a8a880795664b046/project"
)


CHATGPT_PROFILE_DIR = (
    r"C:\chatgpt_auto_profile"
)


MOMENT_QUEUE_FILE = (
    PROJECT_ROOT
    / "queue"
    / "moment_queue.csv"
)


GENERATED_ASSETS_ROOT = (
    PROJECT_ROOT
    / "generated_assets"
)


DEBUG_DIR = (
    PROJECT_ROOT
    / "debug"
    / "pov_remaster_worker"
)


UPLOAD_CACHE_DIR = (
    DEBUG_DIR
    / "upload_cache"
)


DEBUG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


UPLOAD_CACHE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# SETTINGS
# ============================================================

MAX_ATTEMPTS = 3

MAX_RENDER_TIME = 450

MAX_UPLOAD_WAIT = 180

UPLOAD_READY_STABLE_SECONDS = 3

RESTART_AFTER_EACH_IMAGE = True

BROWSER_RESTART_DELAY = 10


# ============================================================
# SAFE UPLOAD SETTINGS
# ============================================================

NORMALIZE_IMAGES_BEFORE_UPLOAD = True

MAX_UPLOAD_IMAGE_EDGE = 2560

UPLOAD_JPEG_QUALITY = 92


# ============================================================
# REMASTER PROMPT
# ============================================================

REMASTER_PROMPT = """
Remaster this exact uploaded frame into a polished cinematic Hero Frame.

CRITICAL PRESERVATION RULE:

Preserve the exact same moment.

Preserve exactly:
- first-person POV
- camera position
- camera angle
- framing
- composition
- viewer body position
- hand and arm positions
- object positions
- environment
- architecture
- landscape
- historical clothing
- historical props
- subject placement
- action state
- overall geometry of the scene

Do NOT redesign the scene.

Do NOT create a different composition.

Do NOT change the camera perspective.

Do NOT move the viewer to another location.

Do NOT add or remove important objects.

Do NOT change the historical moment.

Do NOT turn the image into third-person view.

Do NOT show the viewer's face.

The output should clearly look like the exact final frame of the original video,
only significantly more polished and cinematic.

Improve only:
- photorealism
- realistic human anatomy
- natural skin and fabric detail
- realistic materials
- cinematic lighting
- atmospheric depth
- dynamic range
- subtle contrast
- clarity
- fine texture detail
- realistic shadows
- realistic highlights
- depth separation
- historical authenticity
- high-budget film quality

Maintain natural lighting appropriate to the original scene.

Avoid artificial AI glow.
Avoid oversaturation.
Avoid fantasy styling unless already present in the source.
Avoid excessive sharpening.
Avoid changing facial identity of any visible secondary people.
Avoid adding text.

No text.
No subtitles.
No watermark.

Ultra photorealistic cinematic Hero Frame.
"""


# ============================================================
# GENERAL HELPERS
# ============================================================

def sanitize_filename(
    value,
):

    return re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        str(value),
    )


def resolve_project_path(
    raw_path,
):

    raw_path = (
        str(
            raw_path or ""
        )
        .strip()
    )

    if not raw_path:
        return ""

    raw_path = os.path.expandvars(
        os.path.expanduser(
            raw_path
        )
    )

    raw_path = raw_path.replace(
        "/",
        os.sep,
    )

    if os.path.isabs(
        raw_path
    ):

        return os.path.normpath(
            raw_path
        )

    return os.path.normpath(
        os.path.join(
            PROJECT_ROOT,
            raw_path,
        )
    )


def image_has_transparency(
    image,
):

    if (
        "A"
        in image.getbands()
    ):
        return True

    return (
        "transparency"
        in image.info
    )


# ============================================================
# SAFE IMAGE UPLOAD
# ============================================================

def build_upload_cache_path(
    source_path,
):

    stat = os.stat(
        source_path
    )

    cache_key = "|".join(
        [
            os.path.abspath(
                source_path
            ),
            str(
                stat.st_size
            ),
            str(
                stat.st_mtime_ns
            ),
            str(
                MAX_UPLOAD_IMAGE_EDGE
            ),
            str(
                UPLOAD_JPEG_QUALITY
            ),
        ]
    )

    digest = hashlib.sha256(
        cache_key.encode(
            "utf-8"
        )
    ).hexdigest()[:16]

    source_name = (
        Path(
            source_path
        )
        .stem
    )

    safe_name = (
        sanitize_filename(
            source_name
        )[:50]
    )

    return (
        UPLOAD_CACHE_DIR
        / f"{safe_name}_{digest}"
    )


def normalize_image_for_upload(
    source_path,
):

    source_path = os.path.abspath(
        source_path
    )

    if not os.path.isfile(
        source_path
    ):

        raise FileNotFoundError(
            "Input image not found:\n"
            f"{source_path}"
        )

    try:

        with Image.open(
            source_path
        ) as probe:

            probe.verify()

    except UnidentifiedImageError as error:

        raise ValueError(
            "Input is not a valid image:\n"
            f"{source_path}"
        ) from error

    except Exception as error:

        raise ValueError(
            "Could not read input image:\n"
            f"{source_path}\n"
            f"{error}"
        ) from error

    with Image.open(
        source_path
    ) as image:

        if getattr(
            image,
            "is_animated",
            False,
        ):

            image.seek(
                0
            )

        image = ImageOps.exif_transpose(
            image
        )

        if (
            image.width <= 0
            or image.height <= 0
        ):

            raise ValueError(
                "Invalid image dimensions."
            )

        transparency = (
            image_has_transparency(
                image
            )
        )

        if transparency:

            prepared = (
                image.convert(
                    "RGBA"
                )
            )

            extension = ".png"

        else:

            prepared = (
                image.convert(
                    "RGB"
                )
            )

            extension = ".jpg"

        longest_edge = max(
            prepared.size
        )

        if (
            longest_edge
            > MAX_UPLOAD_IMAGE_EDGE
        ):

            scale = (
                MAX_UPLOAD_IMAGE_EDGE
                / longest_edge
            )

            new_size = (
                max(
                    1,
                    round(
                        prepared.width
                        * scale
                    ),
                ),
                max(
                    1,
                    round(
                        prepared.height
                        * scale
                    ),
                ),
            )

            prepared = (
                prepared.resize(
                    new_size,
                    Image.Resampling.LANCZOS,
                )
            )

        cache_base = (
            build_upload_cache_path(
                source_path
            )
        )

        upload_path = Path(
            str(
                cache_base
            )
            + extension
        )

        if (
            upload_path.is_file()
            and
            upload_path.stat().st_size
            > 0
        ):

            print(
                "Using cached upload image:",
                upload_path,
            )

            prepared.close()

            return str(
                upload_path
            )

        temporary_path = Path(
            str(
                upload_path
            )
            + ".temporary"
        )

        try:

            if (
                extension
                == ".png"
            ):

                prepared.save(
                    temporary_path,
                    format="PNG",
                    optimize=True,
                )

            else:

                prepared.save(
                    temporary_path,
                    format="JPEG",
                    quality=
                        UPLOAD_JPEG_QUALITY,
                    optimize=True,
                    progressive=False,
                    subsampling=0,
                )

            os.replace(
                temporary_path,
                upload_path,
            )

        finally:

            prepared.close()

            if (
                temporary_path.exists()
            ):

                try:

                    temporary_path.unlink()

                except OSError:

                    pass

    print(
        "Prepared upload image:"
    )

    print(
        "  Source:",
        source_path,
    )

    print(
        "  Upload:",
        upload_path,
    )

    return str(
        upload_path
    )


# ============================================================
# QUEUE
# ============================================================

def load_queue():

    if not MOMENT_QUEUE_FILE.exists():

        raise FileNotFoundError(
            "Moment queue not found:\n"
            f"{MOMENT_QUEUE_FILE}"
        )

    with open(
        MOMENT_QUEUE_FILE,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        return list(
            csv.DictReader(
                file
            )
        )


def get_fieldnames(
    rows,
):

    fields = []

    for row in rows:

        for key in row.keys():

            if (
                key
                and key not in fields
            ):

                fields.append(
                    key
                )

    additional = [
        "remaster_attempts",
        "hero_frame_file",
        "error",
    ]

    for field in additional:

        if (
            field
            not in fields
        ):

            fields.append(
                field
            )

    return fields


def save_queue(
    rows,
):

    if not rows:
        return

    fields = (
        get_fieldnames(
            rows
        )
    )

    temporary_file = Path(
        str(
            MOMENT_QUEUE_FILE
        )
        + ".temporary"
    )

    with open(
        temporary_file,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fields,
            extrasaction="ignore",
        )

        writer.writeheader()

        writer.writerows(
            rows
        )

    os.replace(
        temporary_file,
        MOMENT_QUEUE_FILE,
    )


def update_job(
    moment_id,
    **updates,
):

    rows = load_queue()

    found = False

    for row in rows:

        if (
            row.get(
                "moment_id",
                ""
            ).strip()
            != moment_id
        ):

            continue

        for key, value in updates.items():

            row[key] = str(
                value
            )

        found = True

        break

    if not found:

        raise KeyError(
            "Moment not found: "
            f"{moment_id}"
        )

    save_queue(
        rows
    )


# ============================================================
# RESET INTERRUPTED
# ============================================================

def reset_interrupted(
    rows,
):

    changed = False

    for row in rows:

        status = (
            row.get(
                "status",
                ""
            )
            .strip()
            .lower()
        )

        if (
            status
            == "processing_remaster"
        ):

            row["status"] = (
                "last_frame_extracted"
            )

            row["error"] = ""

            changed = True

    if changed:

        save_queue(
            rows
        )


# ============================================================
# OUTPUT
# ============================================================

def get_hero_output_path(
    row,
):

    topic_id = (
        row.get(
            "topic_id",
            ""
        )
        .strip()
    )

    moment_id = (
        row.get(
            "moment_id",
            ""
        )
        .strip()
    )

    if not topic_id:

        raise ValueError(
            "Missing topic_id."
        )

    if not moment_id:

        raise ValueError(
            "Missing moment_id."
        )

    output_dir = (
        GENERATED_ASSETS_ROOT
        / topic_id
        / moment_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    return (
        output_dir
        / "hero_frame.png"
    )


# ============================================================
# GET PENDING JOB
# ============================================================

def get_pending_jobs(
    rows,
):

    pending = []

    for row in rows:

        status = (
            row.get(
                "status",
                ""
            )
            .strip()
            .lower()
        )

        if (
            status
            != "last_frame_extracted"
        ):

            continue

        last_frame_raw = (
            row.get(
                "last_frame_file",
                ""
            )
            .strip()
        )

        # --------------------------------------------
        # FALLBACK PATH
        # --------------------------------------------

        if not last_frame_raw:

            topic_id = (
                row.get(
                    "topic_id",
                    ""
                )
                .strip()
            )

            moment_id = (
                row.get(
                    "moment_id",
                    ""
                )
                .strip()
            )

            fallback = (
                GENERATED_ASSETS_ROOT
                / topic_id
                / moment_id
                / "last_frame_raw.png"
            )

            if fallback.is_file():

                row[
                    "last_frame_file"
                ] = str(
                    fallback
                )

                last_frame_raw = str(
                    fallback
                )

        resolved = (
            resolve_project_path(
                last_frame_raw
            )
        )

        if not os.path.isfile(
            resolved
        ):

            print(
                "[SKIP] Missing last frame:",
                row.get(
                    "moment_id",
                    "",
                ),
            )

            continue

        pending.append(
            row
        )

    pending.sort(
        key=lambda row: (
            row.get(
                "topic_id",
                "",
            ),
            int(
                row.get(
                    "moment_order",
                    ""
                )
                or 0
            ),
        )
    )

    return pending


# ============================================================
# CHATGPT BROWSER
# ============================================================

def open_chatgpt(
    playwright,
):

    browser = (
        playwright.chromium
        .launch_persistent_context(
            user_data_dir=
                CHATGPT_PROFILE_DIR,

            headless=False,

            channel="chrome",

            accept_downloads=True,

            args=[
                "--window-size=1600,1000",
                "--window-position=0,0",
            ],
        )
    )

    if browser.pages:

        page = (
            browser.pages[0]
        )

    else:

        page = (
            browser.new_page()
        )

    page.goto(
        CHATGPT_URL,
        wait_until="domcontentloaded",
        timeout=120000,
    )

    print(
        "Waiting ChatGPT load..."
    )

    time.sleep(
        8
    )

    page.locator(
        "#prompt-textarea"
    ).wait_for(
        state="visible",
        timeout=30000,
    )

    print(
        "ChatGPT ready."
    )

    return (
        browser,
        page,
    )


# ============================================================
# UPLOAD
# ============================================================

def upload_input_image(
    page,
    input_path,
):

    absolute_path = (
        os.path.abspath(
            input_path
        )
    )

    page.locator(
        'button[data-testid="composer-plus-btn"]'
    ).click(
        force=True
    )

    print(
        "Clicked plus button"
    )

    time.sleep(
        2
    )

    with page.expect_file_chooser(
        timeout=30000,
    ) as chooser_info:

        page.get_by_text(
            "Add photos & files",
            exact=True,
        ).click(
            force=True
        )

    chooser = (
        chooser_info.value
    )

    chooser.set_files(
        [
            absolute_path
        ]
    )

    print(
        "Uploaded input image:",
        absolute_path,
    )

    time.sleep(
        8
    )


# ============================================================
# PROMPT
# ============================================================

def fill_prompt(
    page,
    prompt,
):

    prompt_box = (
        page.locator(
            "#prompt-textarea"
        )
    )

    prompt_box.wait_for(
        state="visible",
        timeout=30000,
    )

    prompt_box.click(
        force=True
    )

    prompt_box.fill(
        prompt
    )

    print(
        "Filled remaster prompt"
    )

    time.sleep(
        2
    )


# ============================================================
# WAIT UPLOAD READY
# ============================================================

def wait_for_upload_ready(
    page,
):

    print(
        "Waiting input image upload complete..."
    )

    send_button = (
        page.locator(
            'button[data-testid="send-button"]'
        )
    )

    send_button.wait_for(
        state="visible",
        timeout=
            MAX_UPLOAD_WAIT
            * 1000,
    )

    start_time = (
        time.time()
    )

    ready_since = None

    while True:

        try:

            enabled = (
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

            ready = (
                enabled
                and
                aria_disabled != "true"
                and
                disabled_attribute is None
            )

        except Exception:

            ready = False

        if ready:

            if (
                ready_since
                is None
            ):

                ready_since = (
                    time.time()
                )

                print(
                    "Send button enabled. "
                    "Checking upload stability..."
                )

            if (
                time.time()
                - ready_since
                >=
                UPLOAD_READY_STABLE_SECONDS
            ):

                print(
                    "Input upload complete."
                )

                return

        else:

            ready_since = None

            print(
                "Input image still uploading..."
            )

        if (
            time.time()
            - start_time
            > MAX_UPLOAD_WAIT
        ):

            raise TimeoutError(
                "Timeout waiting for "
                "input image upload."
            )

        time.sleep(
            2
        )


# ============================================================
# WAIT GENERATED IMAGE
# ============================================================

def wait_for_generated_image(
    page,
    before_count,
):

    print(
        "Waiting remastered image..."
    )

    start_time = (
        time.time()
    )

    while True:

        current_count = (
            page.locator(
                'img[alt^="Generated image"]'
            )
            .count()
        )

        print(
            "Generated image count:",
            current_count,
        )

        if (
            current_count
            > before_count
        ):

            print(
                "New generated image detected."
            )

            return

        if (
            time.time()
            - start_time
            > MAX_RENDER_TIME
        ):

            raise TimeoutError(
                "Remaster timeout > "
                f"{MAX_RENDER_TIME}s"
            )

        time.sleep(
            10
        )


# ============================================================
# NORMALIZE OUTPUT PNG
# ============================================================

def normalize_downloaded_output_to_png(
    downloaded_path,
):

    if not os.path.isfile(
        downloaded_path
    ):

        raise FileNotFoundError(
            "Downloaded image not found:\n"
            f"{downloaded_path}"
        )

    temporary_path = (
        downloaded_path
        + ".real_png.temporary"
    )

    try:

        with Image.open(
            downloaded_path
        ) as image:

            detected_format = (
                image.format
                or "UNKNOWN"
            )

            if getattr(
                image,
                "is_animated",
                False,
            ):

                image.seek(
                    0
                )

            image = ImageOps.exif_transpose(
                image
            )

            if image_has_transparency(
                image
            ):

                normalized = (
                    image.convert(
                        "RGBA"
                    )
                )

            else:

                normalized = (
                    image.convert(
                        "RGB"
                    )
                )

            normalized.save(
                temporary_path,
                format="PNG",
                optimize=True,
            )

            normalized.close()

        os.replace(
            temporary_path,
            downloaded_path,
        )

        with Image.open(
            downloaded_path
        ) as verified:

            if (
                verified.format
                != "PNG"
            ):

                raise ValueError(
                    "Final hero frame "
                    "is not a real PNG."
                )

            width, height = (
                verified.size
            )

        print(
            "Normalized hero frame:"
        )

        print(
            "  Source format:",
            detected_format,
        )

        print(
            "  Final:",
            f"{width}x{height} PNG",
        )

    finally:

        if os.path.exists(
            temporary_path
        ):

            try:

                os.remove(
                    temporary_path
                )

            except OSError:

                pass


# ============================================================
# SAVE GENERATED IMAGE
# ============================================================

def save_latest_generated_image(
    page,
    output_path,
):

    generated_image = (
        page.locator(
            'img[alt^="Generated image"]'
        )
        .last
    )

    generated_image.scroll_into_view_if_needed()

    time.sleep(
        2
    )

    generated_image.click(
        force=True
    )

    print(
        "Clicked generated image"
    )

    time.sleep(
        3
    )

    output_path = str(
        output_path
    )

    os.makedirs(
        os.path.dirname(
            output_path
        ),
        exist_ok=True,
    )

    with page.expect_download(
        timeout=180000,
    ) as download_info:

        page.locator(
            'button[aria-label="Save"]'
        ).click(
            force=True
        )

    download = (
        download_info.value
    )

    download.save_as(
        output_path
    )

    if not os.path.isfile(
        output_path
    ):

        raise FileNotFoundError(
            "Hero-frame download completed "
            "but file was not found:\n"
            f"{output_path}"
        )

    normalize_downloaded_output_to_png(
        output_path
    )

    print(
        "Saved hero frame:",
        output_path,
    )

    close_button = (
        page.locator(
            'button[aria-label="Close fullscreen view"]'
        )
    )

    try:

        if (
            close_button.count()
            > 0
            and
            close_button.first.is_visible()
        ):

            close_button.first.click(
                force=True
            )

            print(
                "Closed fullscreen view"
            )

    except Exception:

        pass

    time.sleep(
        3
    )


# ============================================================
# DEBUG
# ============================================================

def safe_screenshot(
    page,
    moment_id,
):

    if page is None:
        return

    try:

        if page.is_closed():
            return

        screenshot_path = (
            DEBUG_DIR
            / (
                "remaster_"
                f"{sanitize_filename(moment_id)}.png"
            )
        )

        page.screenshot(
            path=str(
                screenshot_path
            ),
            full_page=True,
        )

        print(
            "Debug screenshot:",
            screenshot_path,
        )

    except Exception as error:

        print(
            "Could not save debug screenshot:",
            error,
        )


# ============================================================
# CLOSE BROWSER
# ============================================================

def close_browser(
    browser,
):

    if browser is None:
        return

    try:

        print(
            "Closing ChatGPT browser..."
        )

        browser.close()

        print(
            "Browser closed."
        )

    except Exception as error:

        print(
            "Could not close browser:",
            error,
        )


# ============================================================
# MAIN
# ============================================================

def main():

    rows = (
        load_queue()
    )

    reset_interrupted(
        rows
    )

    rows = (
        load_queue()
    )

    first_jobs = (
        get_pending_jobs(
            rows
        )
    )

    if not first_jobs:

        print(
            "=" * 60
        )

        print(
            "No pending remaster jobs."
        )

        return

    with sync_playwright() as playwright:

        browser = None
        page = None

        while True:

            rows = (
                load_queue()
            )

            pending_jobs = (
                get_pending_jobs(
                    rows
                )
            )

            if not pending_jobs:

                print(
                    "=" * 60
                )

                print(
                    "No pending remaster jobs left."
                )

                break

            job = (
                pending_jobs[0]
            )

            moment_id = (
                job.get(
                    "moment_id",
                    ""
                )
                .strip()
            )

            topic_id = (
                job.get(
                    "topic_id",
                    ""
                )
                .strip()
            )

            person = (
                job.get(
                    "person",
                    ""
                )
                .strip()
            )

            moment_order = (
                job.get(
                    "moment_order",
                    ""
                )
                .strip()
            )

            last_frame = (
                resolve_project_path(
                    job.get(
                        "last_frame_file",
                        ""
                    )
                )
            )

            hero_output = str(
                get_hero_output_path(
                    job
                )
            )

            try:

                attempts = int(
                    job.get(
                        "remaster_attempts",
                        ""
                    )
                    or 0
                )

            except ValueError:

                attempts = 0

            print(
                "=" * 60
            )

            print(
                "POV REMASTER JOB"
            )

            print(
                "Moment:",
                moment_id,
            )

            print(
                "Topic:",
                topic_id,
            )

            print(
                "Person:",
                person,
            )

            print(
                "Moment order:",
                moment_order,
            )

            print(
                "Input:",
                last_frame,
            )

            print(
                "Output:",
                hero_output,
            )

            update_job(
                moment_id,

                status=
                    "processing_remaster",

                error="",
            )

            try:

                if not os.path.isfile(
                    last_frame
                ):

                    raise FileNotFoundError(
                        "Last frame not found:\n"
                        f"{last_frame}"
                    )

                # --------------------------------------------
                # Existing output
                # --------------------------------------------

                if (
                    os.path.isfile(
                        hero_output
                    )
                    and
                    os.path.getsize(
                        hero_output
                    )
                    > 0
                ):

                    print(
                        "Existing hero frame found."
                    )

                    print(
                        "Skipping generation."
                    )

                else:

                    # ----------------------------------------
                    # OPEN BROWSER
                    # ----------------------------------------

                    if (
                        browser is None
                        or page is None
                    ):

                        (
                            browser,
                            page,
                        ) = open_chatgpt(
                            playwright
                        )

                    # ----------------------------------------
                    # PREPARE INPUT
                    # ----------------------------------------

                    if (
                        NORMALIZE_IMAGES_BEFORE_UPLOAD
                    ):

                        upload_image = (
                            normalize_image_for_upload(
                                last_frame
                            )
                        )

                    else:

                        upload_image = (
                            last_frame
                        )

                    # ----------------------------------------
                    # COUNT BEFORE
                    # ----------------------------------------

                    before_count = (
                        page.locator(
                            'img[alt^="Generated image"]'
                        )
                        .count()
                    )

                    print(
                        "Generated images before:",
                        before_count,
                    )

                    # ----------------------------------------
                    # UPLOAD
                    # ----------------------------------------

                    upload_input_image(
                        page,
                        upload_image,
                    )

                    # ----------------------------------------
                    # PROMPT
                    # ----------------------------------------

                    fill_prompt(
                        page,
                        REMASTER_PROMPT,
                    )

                    # ----------------------------------------
                    # WAIT UPLOAD
                    # ----------------------------------------

                    wait_for_upload_ready(
                        page
                    )

                    # ----------------------------------------
                    # SEND
                    # ----------------------------------------

                    page.locator(
                        'button[data-testid="send-button"]'
                    ).click(
                        force=True
                    )

                    print(
                        "Sent remaster request"
                    )

                    time.sleep(
                        2
                    )

                    # ----------------------------------------
                    # WAIT GENERATION
                    # ----------------------------------------

                    wait_for_generated_image(
                        page,
                        before_count,
                    )

                    # Chờ ảnh + nút Save ổn định.
                    time.sleep(
                        12
                    )

                    # ----------------------------------------
                    # SAVE
                    # ----------------------------------------

                    save_latest_generated_image(
                        page,
                        hero_output,
                    )

                # ============================================
                # SUCCESS
                # ============================================

                update_job(
                    moment_id,

                    status=
                        "hero_frame_generated",

                    remaster_attempts=
                        str(
                            attempts + 1
                        ),

                    hero_frame_file=
                        hero_output,

                    error="",
                )

                print(
                    "[OK] Hero frame generated:",
                    moment_id,
                )

                # --------------------------------------------
                # Restart browser after each image
                # --------------------------------------------

                if (
                    RESTART_AFTER_EACH_IMAGE
                    and
                    browser is not None
                ):

                    close_browser(
                        browser
                    )

                    browser = None
                    page = None

                    time.sleep(
                        BROWSER_RESTART_DELAY
                    )

            except Exception as error:

                error_text = str(
                    error
                )

                print(
                    "[ERROR] Remaster failed:",
                    moment_id,
                )

                print(
                    "Error:",
                    error_text,
                )

                attempts += 1

                if (
                    attempts
                    >= MAX_ATTEMPTS
                ):

                    next_status = (
                        "hero_frame_failed"
                    )

                else:

                    next_status = (
                        "last_frame_extracted"
                    )

                update_job(
                    moment_id,

                    status=
                        next_status,

                    remaster_attempts=
                        str(
                            attempts
                        ),

                    error=
                        error_text,
                )

                safe_screenshot(
                    page,
                    moment_id,
                )

                if (
                    browser is not None
                ):

                    close_browser(
                        browser
                    )

                    browser = None
                    page = None

                time.sleep(
                    5
                )

        if (
            browser is not None
        ):

            close_browser(
                browser
            )

    print(
        "=" * 60
    )

    print(
        "POV remaster batch finished."
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    main()