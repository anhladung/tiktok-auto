from __future__ import annotations

import csv
import os
import shutil
import subprocess

from pathlib import Path
from collections import defaultdict


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

MOMENT_QUEUE_FILE = (
    PROJECT_ROOT
    / "queue"
    / "moment_queue.csv"
)


TOPIC_QUEUE_FILE = (
    PROJECT_ROOT
    / "queue"
    / "topic_queue.csv"
)


GENERATED_ASSETS_ROOT = (
    PROJECT_ROOT
    / "generated_assets"
)


FINAL_OUTPUT_ROOT = (
    PROJECT_ROOT
    / "final_videos"
)


MUSIC_ROOT = (
    PROJECT_ROOT
    / "music"
)


DEBUG_DIR = (
    PROJECT_ROOT
    / "debug"
    / "final_render_worker"
)


FINAL_OUTPUT_ROOT.mkdir(
    parents=True,
    exist_ok=True,
)


DEBUG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# FFMPEG
# ============================================================

FFMPEG_DIR = (
    r"C:\Users\Thinkbook 14G2\Downloads"
    r"\ffmpeg-2026-06-29-git-de6bcf5c05-full_build"
    r"\ffmpeg-2026-06-29-git-de6bcf5c05-full_build"
    r"\bin"
)


FFMPEG = os.path.join(
    FFMPEG_DIR,
    "ffmpeg.exe"
)


FFPROBE = os.path.join(
    FFMPEG_DIR,
    "ffprobe.exe"
)


if not os.path.isfile(
    FFMPEG
):

    raise FileNotFoundError(
        f"FFmpeg not found:\n{FFMPEG}"
    )


if not os.path.isfile(
    FFPROBE
):

    raise FileNotFoundError(
        f"FFprobe not found:\n{FFPROBE}"
    )


# ============================================================
# FONT
# ============================================================

FONT_FILE = (
    r"C:\Windows\Fonts\arialbd.ttf"
)


if not os.path.isfile(
    FONT_FILE
):

    FONT_FILE = (
        r"C:\Windows\Fonts\arial.ttf"
    )


if not os.path.isfile(
    FONT_FILE
):

    raise FileNotFoundError(
        "Arial font not found."
    )


# ============================================================
# OUTPUT VIDEO
# ============================================================

OUTPUT_WIDTH = 1080

OUTPUT_HEIGHT = 1920

FPS = 30


CRF = 18

PRESET = "medium"


# ============================================================
# MUSIC / VISUAL TIMELINE
# ============================================================

TIMELINE = {

    1: {

        "clip_start": 0.0,
        "clip_end": 2.3,

        "hero_start": 2.3,
        "hero_end": 4.4,
    },

    2: {

        "clip_start": 4.4,
        "clip_end": 6.2,

        "hero_start": 6.2,
        "hero_end": 8.1,
    },

    3: {

        "clip_start": 8.1,
        "clip_end": 10.3,

        "hero_start": 10.3,
        "hero_end": 12.5,
    },
}


FINAL_DURATION = 12.5


MINIMUM_MOMENTS = 3


# ============================================================
# MUSIC
# ============================================================

ENABLE_MUSIC = True


MUSIC_VOLUME = 0.90


# ============================================================
# TITLE STYLE
# ============================================================

TITLE_FONT_SIZE = 60


TITLE_Y = 190


TITLE_BOX_ALPHA = 0.24


# IMPORTANT:
#
# Title không còn TITLE_DURATION.
# Nó xuất hiện SUỐT segment.


# ============================================================
# PHONK / CINEMATIC LOOK
# ============================================================

# ------------------------------------------------------------
# DARK COLOR GRADE
# ------------------------------------------------------------

GRADE_BRIGHTNESS = 0.0
GRADE_CONTRAST = 1.05
GRADE_SATURATION = 0.96
GRADE_GAMMA = 1.00


# ------------------------------------------------------------
# FILM GRAIN
# ------------------------------------------------------------

GRAIN_STRENGTH = 1


# ------------------------------------------------------------
# VIGNETTE
# ------------------------------------------------------------

VIGNETTE_ANGLE = "PI/9"


# ------------------------------------------------------------
# CLIP MICRO SHAKE
# ------------------------------------------------------------

# Scale video lớn hơn 1080x1920,
# sau đó crop rung bên trong vùng dư.

SHAKE_SCALE_WIDTH = 1120

SHAKE_SCALE_HEIGHT = 1992


# Pixel shake liên tục.

CLIP_SHAKE_X = 2
CLIP_SHAKE_Y = 3

# ------------------------------------------------------------
# HERO PUSH IN
# ------------------------------------------------------------

HERO_ZOOM_START = 1.00

HERO_ZOOM_MAX = 1.035


# Mỗi frame tăng bao nhiêu zoom.

HERO_ZOOM_SPEED = 0.00055


# ------------------------------------------------------------
# HERO IMPACT
# ------------------------------------------------------------

IMPACT_SHAKE_X = 4
IMPACT_SHAKE_Y = 5
IMPACT_DURATION = 0.10

# Flash brightness ở đầu Hero.

FLASH_DURATION = 0.045
FLASH_BRIGHTNESS = 0.055

HERO_MAIN_FLASH_DURATION = 0.045
HERO_MAIN_FLASH_BRIGHTNESS = 0.055

HERO_MICRO_FLASH_1_TIME = 0.34
HERO_MICRO_FLASH_2_TIME = 0.78
HERO_MICRO_FLASH_3_TIME = 1.28
HERO_MICRO_FLASH_4_TIME = 1.68

HERO_MICRO_FLASH_DURATION = 0.028
HERO_MICRO_FLASH_BRIGHTNESS = 0.022

# ============================================================
# HERO PHOTO FLICKER
# ============================================================


HERO_FLICKER_SPEED = 18

# ============================================================
# CSV
# ============================================================

def load_csv(
    file_path,
):

    if not file_path.exists():

        return []

    with open(
        file_path,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        return list(
            csv.DictReader(
                file
            )
        )


def save_csv(
    file_path,
    rows,
):

    if not rows:

        return

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

    temporary = Path(
        str(
            file_path
        )
        + ".temporary"
    )

    with open(
        temporary,
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
        temporary,
        file_path,
    )


# ============================================================
# UPDATE MOMENTS
# ============================================================

def update_topic_moments(
    topic_id,
    **updates,
):

    rows = load_csv(
        MOMENT_QUEUE_FILE
    )

    changed = False

    for row in rows:

        if (
            row.get(
                "topic_id",
                ""
            ).strip()
            != topic_id
        ):

            continue

        for key, value in updates.items():

            row[key] = str(
                value
            )

        changed = True

    if changed:

        save_csv(
            MOMENT_QUEUE_FILE,
            rows,
        )


# ============================================================
# UPDATE TOPIC
# ============================================================

def update_topic_queue(
    topic_id,
    **updates,
):

    if not TOPIC_QUEUE_FILE.exists():

        return

    rows = load_csv(
        TOPIC_QUEUE_FILE
    )

    changed = False

    for row in rows:

        if (
            row.get(
                "topic_id",
                ""
            ).strip()
            != topic_id
        ):

            continue

        for key, value in updates.items():

            row[key] = str(
                value
            )

        changed = True

    if changed:

        save_csv(
            TOPIC_QUEUE_FILE,
            rows,
        )


# ============================================================
# PATH
# ============================================================

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


def ffmpeg_filter_path(
    path,
):

    path = os.path.abspath(
        str(
            path
        )
    )

    path = path.replace(
        "\\",
        "/",
    )

    path = path.replace(
        ":",
        "\\:",
    )

    path = path.replace(
        "'",
        "\\'",
    )

    return path


# ============================================================
# VIDEO DURATION
# ============================================================

def get_video_duration(
    video_path,
):

    command = [

        FFPROBE,

        "-v",
        "error",

        "-show_entries",
        "format=duration",

        "-of",
        (
            "default="
            "noprint_wrappers=1:"
            "nokey=1"
        ),

        video_path,
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if (
        result.returncode
        != 0
    ):

        raise RuntimeError(
            "FFprobe failed:\n"
            f"{result.stderr}"
        )

    text = (
        result.stdout
        .strip()
    )

    if not text:

        raise RuntimeError(
            "Could not read video duration."
        )

    return float(
        text
    )


# ============================================================
# MOMENT TIMING
# ============================================================

def get_moment_timing(
    moment_order,
):

    if (
        moment_order
        not in TIMELINE
    ):

        raise ValueError(
            f"No timeline for Moment "
            f"{moment_order}"
        )

    timing = (
        TIMELINE[
            moment_order
        ]
    )

    clip_duration = (

        timing[
            "clip_end"
        ]

        -

        timing[
            "clip_start"
        ]
    )

    hero_duration = (

        timing[
            "hero_end"
        ]

        -

        timing[
            "hero_start"
        ]
    )

    return (
        clip_duration,
        hero_duration,
    )


# ============================================================
# TITLE
# ============================================================

def build_title(
    row,
):

    moment_order = int(
        row.get(
            "moment_order",
            "0"
        )
        or 0
    )

    person = (
        row.get(
            "person",
            ""
        )
        .strip()
    )

    short_title = (
        row.get(
            "short_title",
            ""
        )
        .strip()
    )

    # --------------------------------------------------------
    # MOMENT 1
    # --------------------------------------------------------

    if (
        moment_order
        == 1
    ):

        return (
            f"POV: You are {person}"
        )

    # --------------------------------------------------------
    # MOMENT 2+
    # --------------------------------------------------------

    if short_title:

        return short_title

    moment = (
        row.get(
            "moment",
            ""
        )
        .strip()
    )

    if (
        len(
            moment
        )
        > 40
    ):

        moment = (
            moment[:37]
            + "..."
        )

    return moment


# ============================================================
# CLIP PATH
# ============================================================

def get_clip_path(
    row,
):

    saved_path = (
        resolve_project_path(
            row.get(
                "video_file",
                ""
            )
        )
    )

    if (
        saved_path
        and
        os.path.isfile(
            saved_path
        )
    ):

        return saved_path

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
        / "clip.mp4"
    )

    if fallback.is_file():

        return str(
            fallback
        )

    return ""


# ============================================================
# HERO PATH
# ============================================================

def get_hero_path(
    row,
):

    saved_path = (
        resolve_project_path(
            row.get(
                "hero_frame_file",
                ""
            )
        )
    )

    if (
        saved_path
        and
        os.path.isfile(
            saved_path
        )
    ):

        return saved_path

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
        / "hero_frame.png"
    )

    if fallback.is_file():

        return str(
            fallback
        )

    return ""


# ============================================================
# MUSIC
# ============================================================

def find_music(
    topic_id,
):

    if not ENABLE_MUSIC:

        return ""

    extensions = [

        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
    ]

    # --------------------------------------------------------
    # TOPIC MUSIC
    # --------------------------------------------------------

    for extension in extensions:

        path = (
            MUSIC_ROOT
            / (
                topic_id
                + extension
            )
        )

        if path.is_file():

            return str(
                path
            )

    # --------------------------------------------------------
    # DEFAULT MUSIC
    # --------------------------------------------------------

    for extension in extensions:

        path = (
            MUSIC_ROOT
            / (
                "default"
                + extension
            )
        )

        if path.is_file():

            return str(
                path
            )

    return ""


# ============================================================
# BUILD MOMENT SEGMENT
# ============================================================

def build_moment_segment(
    row,
    segment_output,
    work_dir,
):

    moment_id = (
        row.get(
            "moment_id",
            ""
        )
        .strip()
    )

    moment_order = int(
        row.get(
            "moment_order",
            "0"
        )
        or 0
    )

    clip_file = (
        get_clip_path(
            row
        )
    )

    hero_file = (
        get_hero_path(
            row
        )
    )

    if not clip_file:

        raise FileNotFoundError(
            f"Missing clip: {moment_id}"
        )

    if not hero_file:

        raise FileNotFoundError(
            f"Missing hero: {moment_id}"
        )

    (
        target_clip_duration,
        hero_duration,
    ) = (
        get_moment_timing(
            moment_order
        )
    )

    original_clip_duration = (
        get_video_duration(
            clip_file
        )
    )

    if (
        original_clip_duration
        < target_clip_duration
    ):

        raise RuntimeError(

            f"{moment_id}: clip "
            f"{original_clip_duration:.2f}s "
            f"is shorter than required "
            f"{target_clip_duration:.2f}s."
        )

    title = (
        build_title(
            row
        )
    )

    total_segment_duration = (

        target_clip_duration
        +
        hero_duration
    )

    # ========================================================
    # LOG
    # ========================================================

    print()

    print(
        "=" * 60
    )

    print(
        "Building:",
        moment_id,
    )

    print(
        "Title:",
        title,
    )

    print(
        "Original clip:",
        round(
            original_clip_duration,
            3,
        ),
    )

    print(
        "Using clip:",
        round(
            target_clip_duration,
            3,
        ),
    )

    print(
        "Hero:",
        round(
            hero_duration,
            3,
        ),
    )

    # ========================================================
    # TITLE FILE
    # ========================================================

    title_file = (

        Path(
            work_dir
        )

        / (

            moment_id
            + "_title.txt"
        )
    )

    title_file.write_text(
        title,
        encoding="utf-8",
    )


    font_filter = (
        ffmpeg_filter_path(
            FONT_FILE
        )
    )


    title_filter = (
        ffmpeg_filter_path(
            title_file
        )
    )


    # ========================================================
    # CLIP SHAKE
    # ========================================================

    clip_crop_x = (
        f"(iw-ow)/2"
        f"+{CLIP_SHAKE_X}*sin(11*t)"
        f"+0.8*sin(27*t)"
    )

    clip_crop_y = (
        f"(ih-oh)/2"
        f"+{CLIP_SHAKE_Y}*sin(13*t)"
        f"+0.8*sin(31*t)"
    )


    # ========================================================
    # HERO IMPACT SHAKE
    # ========================================================

    hero_crop_x = (

        f"(iw-ow)/2"

        f"+if("
        f"lt(t,{IMPACT_DURATION}),"

        f"{IMPACT_SHAKE_X}"
        f"*sin(78*t),"

        f"0)"
    )


    hero_crop_y = (

        f"(ih-oh)/2"

        f"+if("
        f"lt(t,{IMPACT_DURATION}),"

        f"{IMPACT_SHAKE_Y}"
        f"*sin(91*t),"

        f"0)"
    )


    # ========================================================
    # FILTER
    # ========================================================

    filter_complex = (

        # ====================================================
        # CLIP
        # ====================================================

        f"[0:v]"

        # Cut source clip.
        f"trim="
        f"start=0:"
        f"duration="
        f"{target_clip_duration},"

        f"setpts="
        f"PTS-STARTPTS,"

        # Slightly overscale for shake.
        f"scale="
        f"{SHAKE_SCALE_WIDTH}:"
        f"{SHAKE_SCALE_HEIGHT}:"
        f"force_original_aspect_ratio="
        f"increase,"

        # Dynamic crop = camera shake.
        f"crop="
        f"{OUTPUT_WIDTH}:"
        f"{OUTPUT_HEIGHT}:"
        f"x='{clip_crop_x}':"
        f"y='{clip_crop_y}',"

        f"fps="
        f"{FPS},"

        f"setsar=1,"

        # --------------------------------------------
        # DARK CINEMATIC GRADE
        # --------------------------------------------

        f"eq="
        f"brightness="
        f"{GRADE_BRIGHTNESS}:"
        f"contrast="
        f"{GRADE_CONTRAST}:"
        f"saturation="
        f"{GRADE_SATURATION}:"
        f"gamma="
        f"{GRADE_GAMMA},"

        # --------------------------------------------
        # VIGNETTE
        # --------------------------------------------

        f"vignette="
        f"{VIGNETTE_ANGLE},"

        # --------------------------------------------
        # FILM GRAIN
        # --------------------------------------------

        f"noise="
        f"alls="
        f"{GRAIN_STRENGTH}:"
        f"allf=t+u,"

        f"format="
        f"yuv420p"

        f"[clip];"


        # ====================================================
        # HERO — BASE PUSH IN
        # ====================================================

        f"[1:v]"

        # Large enough for push-in.
        f"scale="
        f"1200:"
        f"2134:"
        f"force_original_aspect_ratio="
        f"increase,"

        # Slow cinematic zoom.
        f"zoompan="

        f"z='"
        f"min("
        f"zoom+"
        f"{HERO_ZOOM_SPEED},"
        f"{HERO_ZOOM_MAX}"
        f")':"

        f"x='"
        f"iw/2-"
        f"(iw/zoom/2)"
        f"':"

        f"y='"
        f"ih/2-"
        f"(ih/zoom/2)"
        f"':"

        f"d=1:"

        f"s="
        f"{OUTPUT_WIDTH}x"
        f"{OUTPUT_HEIGHT}:"

        f"fps="
        f"{FPS},"

        # Slight overscale again for impact shake.
        f"scale="
        f"1120:"
        f"1992,"

        # --------------------------------------------
        # IMPACT SHAKE
        # only first ~0.20 sec.
        # --------------------------------------------

        f"crop="
        f"{OUTPUT_WIDTH}:"
        f"{OUTPUT_HEIGHT}:"
        f"x='{hero_crop_x}':"
        f"y='{hero_crop_y}',"

        f"fps="
        f"{FPS},"

        f"setsar=1,"

        # --------------------------------------------
        # HERO FLASH PATTERN
        #
        # 1 main flash ở đầu Hero
        # + vài micro flash rất ngắn sau đó
        # --------------------------------------------

        f"eq="

        f"brightness='"

        # ========================================================
        # MAIN FLASH
        # ========================================================

        f"if("
        f"lt(t,{HERO_MAIN_FLASH_DURATION}),"
        f"{HERO_MAIN_FLASH_BRIGHTNESS},"

        # ========================================================
        # MICRO FLASH 1
        # ========================================================

        f"if("
        f"between("
        f"t,"
        f"{HERO_MICRO_FLASH_1_TIME},"
        f"{HERO_MICRO_FLASH_1_TIME + HERO_MICRO_FLASH_DURATION}"
        f"),"
        f"{HERO_MICRO_FLASH_BRIGHTNESS},"

        # ========================================================
        # MICRO FLASH 2
        # ========================================================

        f"if("
        f"between("
        f"t,"
        f"{HERO_MICRO_FLASH_2_TIME},"
        f"{HERO_MICRO_FLASH_2_TIME + HERO_MICRO_FLASH_DURATION}"
        f"),"
        f"{HERO_MICRO_FLASH_BRIGHTNESS * 0.80},"

        # ========================================================
        # MICRO FLASH 3
        # ========================================================

        f"if("
        f"between("
        f"t,"
        f"{HERO_MICRO_FLASH_3_TIME},"
        f"{HERO_MICRO_FLASH_3_TIME + HERO_MICRO_FLASH_DURATION}"
        f"),"
        f"{HERO_MICRO_FLASH_BRIGHTNESS},"

        # ========================================================
        # MICRO FLASH 4
        # ========================================================

        f"if("
        f"between("
        f"t,"
        f"{HERO_MICRO_FLASH_4_TIME},"
        f"{HERO_MICRO_FLASH_4_TIME + HERO_MICRO_FLASH_DURATION}"
        f"),"
        f"{HERO_MICRO_FLASH_BRIGHTNESS * 0.65},"

        # ========================================================
        # NORMAL FRAME
        # ========================================================

        f"0"

        # Close nested ifs.
        f")"
        f")"
        f")"
        f")"
        f")"

        f"':"

        f"contrast="
        f"1.05:"

        f"saturation="
        f"0.96:"

        f"gamma="
        f"1.00:"

        f"eval=frame,"

        # --------------------------------------------
        # VIGNETTE
        # --------------------------------------------

        f"vignette="
        f"{VIGNETTE_ANGLE},"

        # --------------------------------------------
        # GRAIN
        # --------------------------------------------

        f"noise="
        f"alls="
        f"{GRAIN_STRENGTH}:"
        f"allf=t+u,"

        # Exact Hero duration.
        f"trim="
        f"duration="
        f"{hero_duration},"

        f"setpts="
        f"PTS-STARTPTS,"

        f"format="
        f"yuv420p"

        f"[hero];"


        # ====================================================
        # CONCAT CLIP + HERO
        # ====================================================

        f"[clip]"
        f"[hero]"

        f"concat="
        f"n=2:"
        f"v=1:"
        f"a=0"

        f"[joined];"


        # ====================================================
        # TITLE
        #
        # IMPORTANT:
        # No enable=between(...)
        #
        # → TITLE STAYS FOR ENTIRE MOMENT.
        # ====================================================

        f"[joined]"

        f"drawtext="

        f"fontfile="
        f"'{font_filter}':"

        f"textfile="
        f"'{title_filter}':"

        f"fontcolor="
        f"white:"

        f"fontsize="
        f"{TITLE_FONT_SIZE}:"

        f"x="
        f"(w-text_w)/2:"

        f"y="
        f"{TITLE_Y}:"

        f"box=1:"

        f"boxcolor="
        f"black@"
        f"{TITLE_BOX_ALPHA}:"

        f"boxborderw="
        f"18:"

        f"shadowcolor="
        f"black@0.75:"

        f"shadowx=2:"

        f"shadowy=3"

        f"[outv]"
    )


    # ========================================================
    # FFMPEG COMMAND
    # ========================================================

    command = [

        FFMPEG,

        "-y",

        # ----------------------------------------------------
        # SOURCE VIDEO
        # ----------------------------------------------------

        "-i",
        clip_file,

        # ----------------------------------------------------
        # HERO IMAGE
        # ----------------------------------------------------

        "-loop",
        "1",

        "-framerate",
        str(
            FPS
        ),

        "-i",
        hero_file,

        # ----------------------------------------------------
        # FILTER
        # ----------------------------------------------------

        "-filter_complex",
        filter_complex,

        "-map",
        "[outv]",

        "-an",

        # ----------------------------------------------------
        # ENCODING
        # ----------------------------------------------------

        "-c:v",
        "libx264",

        "-preset",
        PRESET,

        "-crf",
        str(
            CRF
        ),

        "-pix_fmt",
        "yuv420p",

        "-r",
        str(
            FPS
        ),

        "-movflags",
        "+faststart",

        # Important because hero input loops infinitely.
        "-t",
        str(
            total_segment_duration
        ),

        segment_output,
    ]


    print(
        "Running FFmpeg effects..."
    )


    result = subprocess.run(

        command,

        stdout=
            subprocess.PIPE,

        stderr=
            subprocess.PIPE,

        text=True,

        encoding=
            "utf-8",

        errors=
            "replace",
    )


    if (
        result.returncode
        != 0
    ):

        print()

        print(
            "FFmpeg error:"
        )

        print(
            result.stderr[
                -8000:
            ]
        )

        raise RuntimeError(
            f"FFmpeg segment failed: "
            f"{moment_id}"
        )


    if not os.path.isfile(
        segment_output
    ):

        raise RuntimeError(
            "Segment was not created:\n"
            f"{segment_output}"
        )


    actual_duration = (
        get_video_duration(
            segment_output
        )
    )


    print(
        "Segment created:",
        segment_output,
    )

    print(
        "Actual duration:",
        round(
            actual_duration,
            3,
        ),
    )


# ============================================================
# CONCAT
# ============================================================

def concat_segments(
    segment_files,
    output_file,
    work_dir,
):

    concat_file = (
        Path(
            work_dir
        )
        / "concat.txt"
    )


    lines = []


    for segment in segment_files:

        normalized = (

            os.path.abspath(
                segment
            )

            .replace(
                "\\",
                "/",
            )
        )


        normalized = (
            normalized.replace(
                "'",
                "'\\''",
            )
        )


        lines.append(
            f"file '{normalized}'"
        )


    concat_file.write_text(

        "\n".join(
            lines
        ),

        encoding=
            "utf-8",
    )


    command = [

        FFMPEG,

        "-y",

        "-f",
        "concat",

        "-safe",
        "0",

        "-i",
        str(
            concat_file
        ),

        "-c",
        "copy",

        output_file,
    ]


    print()

    print(
        "Concatenating segments..."
    )


    result = subprocess.run(

        command,

        stdout=
            subprocess.PIPE,

        stderr=
            subprocess.PIPE,

        text=True,

        encoding=
            "utf-8",

        errors=
            "replace",
    )


    if (
        result.returncode
        != 0
    ):

        print(
            result.stderr[
                -5000:
            ]
        )

        raise RuntimeError(
            "FFmpeg concat failed."
        )


    if not os.path.isfile(
        output_file
    ):

        raise RuntimeError(
            "Visual output was not created."
        )


# ============================================================
# MUSIC
# ============================================================

def add_music(
    visual_video,
    music_file,
    output_file,
):

    command = [

        FFMPEG,

        "-y",

        "-i",
        visual_video,

        # Loop music if needed.
        "-stream_loop",
        "-1",

        "-i",
        music_file,

        "-filter:a",
        (
            f"volume="
            f"{MUSIC_VOLUME}"
        ),

        "-map",
        "0:v:0",

        "-map",
        "1:a:0",

        "-c:v",
        "copy",

        "-c:a",
        "aac",

        "-b:a",
        "192k",

        "-t",
        str(
            FINAL_DURATION
        ),

        "-movflags",
        "+faststart",

        output_file,
    ]


    print()

    print(
        "Adding music:"
    )

    print(
        music_file
    )


    result = subprocess.run(

        command,

        stdout=
            subprocess.PIPE,

        stderr=
            subprocess.PIPE,

        text=True,

        encoding=
            "utf-8",

        errors=
            "replace",
    )


    if (
        result.returncode
        != 0
    ):

        print(
            result.stderr[
                -5000:
            ]
        )

        raise RuntimeError(
            "Could not add music."
        )


    if not os.path.isfile(
        output_file
    ):

        raise RuntimeError(
            "Final music video "
            "was not created."
        )


# ============================================================
# VALIDATE TOPIC
# ============================================================

def validate_topic(
    topic_id,
    rows,
):

    if (
        len(
            rows
        )
        < MINIMUM_MOMENTS
    ):

        return False


    required_orders = {
        1,
        2,
        3,
    }


    available_orders = {

        int(
            row.get(
                "moment_order",
                "0"
            )
            or 0
        )

        for row in rows
    }


    if not (
        required_orders
        .issubset(
            available_orders
        )
    ):

        print(
            "[WAIT] Missing moments:",
            topic_id,
        )

        return False


    for row in rows:

        moment_order = int(
            row.get(
                "moment_order",
                "0"
            )
            or 0
        )


        if (
            moment_order
            not in TIMELINE
        ):

            continue


        moment_id = (
            row.get(
                "moment_id",
                ""
            )
            .strip()
        )


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
            not in {
                "hero_frame_generated",
                "final_rendered",
            }
        ):

            print(
                "[WAIT]",
                moment_id,
                "status:",
                status,
            )

            return False


        if not get_clip_path(
            row
        ):

            print(
                "[WAIT] Missing clip:",
                moment_id,
            )

            return False


        if not get_hero_path(
            row
        ):

            print(
                "[WAIT] Missing hero:",
                moment_id,
            )

            return False


    return True


# ============================================================
# READY TOPICS
# ============================================================

def get_ready_topics():

    rows = load_csv(
        MOMENT_QUEUE_FILE
    )


    grouped = defaultdict(
        list
    )


    for row in rows:

        topic_id = (
            row.get(
                "topic_id",
                ""
            )
            .strip()
        )


        if not topic_id:

            continue


        grouped[
            topic_id
        ].append(
            row
        )


    ready = []


    for (
        topic_id,
        topic_rows,
    ) in grouped.items():


        if not validate_topic(
            topic_id,
            topic_rows,
        ):

            continue


        relevant = [

            row

            for row in topic_rows

            if (

                int(
                    row.get(
                        "moment_order",
                        "0"
                    )
                    or 0
                )

                in TIMELINE
            )
        ]


        relevant.sort(

            key=lambda row:

                int(
                    row.get(
                        "moment_order",
                        "0"
                    )
                    or 0
                )
        )


        ready.append(
            (
                topic_id,
                relevant,
            )
        )


    ready.sort(
        key=lambda item:
            item[0]
    )


    return ready


# ============================================================
# RENDER TOPIC
# ============================================================

def render_topic(
    topic_id,
    rows,
):

    print()

    print(
        "=" * 70
    )

    print(
        "PHONK FINAL RENDER:",
        topic_id,
    )

    print(
        "=" * 70
    )


    output_file = (
        FINAL_OUTPUT_ROOT
        / (
            topic_id
            + ".mp4"
        )
    )


    # Always regenerate when testing effects.

    if output_file.exists():

        output_file.unlink()


    update_topic_moments(

        topic_id,

        status=
            "processing_final_render",

        error="",
    )


    update_topic_queue(

        topic_id,

        status=
            "processing_final_render",
    )


    work_dir = (

        DEBUG_DIR
        / topic_id
        / "render_temp"
    )


    if work_dir.exists():

        shutil.rmtree(
            work_dir,
            ignore_errors=True,
        )


    work_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


    try:

        segment_files = []


        # ====================================================
        # BUILD SEGMENTS
        # ====================================================

        for row in rows:

            order = int(
                row.get(
                    "moment_order",
                    "0"
                )
                or 0
            )


            segment_output = (

                work_dir
                / (
                    f"segment_"
                    f"{order:02d}.mp4"
                )
            )


            build_moment_segment(

                row=
                    row,

                segment_output=
                    str(
                        segment_output
                    ),

                work_dir=
                    work_dir,
            )


            segment_files.append(
                str(
                    segment_output
                )
            )


        # ====================================================
        # CONCAT
        # ====================================================

        visual_output = (

            work_dir
            / "visual_only.mp4"
        )


        concat_segments(

            segment_files=
                segment_files,

            output_file=
                str(
                    visual_output
                ),

            work_dir=
                work_dir,
        )


        # ====================================================
        # MUSIC
        # ====================================================

        music_file = (
            find_music(
                topic_id
            )
        )


        if music_file:

            add_music(

                visual_video=
                    str(
                        visual_output
                    ),

                music_file=
                    music_file,

                output_file=
                    str(
                        output_file
                    ),
            )

        else:

            print(
                "No music found."
            )


            shutil.copy2(
                visual_output,
                output_file,
            )


        # ====================================================
        # VERIFY
        # ====================================================

        if not output_file.is_file():

            raise RuntimeError(
                "Final output missing."
            )


        duration = (
            get_video_duration(
                str(
                    output_file
                )
            )
        )


        print()

        print(
            "=" * 70
        )

        print(
            "FINAL VIDEO READY"
        )

        print(
            "Duration:",
            round(
                duration,
                3,
            ),
        )

        print(
            "Output:"
        )

        print(
            output_file
        )

        print(
            "=" * 70
        )


        # ====================================================
        # SUCCESS
        # ====================================================

        update_topic_moments(

            topic_id,

            status=
                "final_rendered",

            final_video_file=
                str(
                    output_file
                ),

            error="",
        )


        update_topic_queue(

            topic_id,

            status=
                "final_rendered",

            final_video_file=
                str(
                    output_file
                ),
        )


    except Exception as error:

        error_text = str(
            error
        )


        print(
            "[ERROR]",
            error_text,
        )


        update_topic_moments(

            topic_id,

            status=
                "hero_frame_generated",

            error=
                error_text,
        )


        update_topic_queue(

            topic_id,

            status=
                "final_render_error",
        )


        raise


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=" * 70
    )

    print(
        "YOUTUBE POV — PHONK FINAL RENDER"
    )

    print(
        "=" * 70
    )


    print()

    print(
        "TIMELINE:"
    )


    for order in sorted(
        TIMELINE.keys()
    ):

        timing = (
            TIMELINE[
                order
            ]
        )


        print(

            f"M{order}: "

            f"CLIP "
            f"{timing['clip_start']}"
            f"-"
            f"{timing['clip_end']}"

            f" | HERO "
            f"{timing['hero_start']}"
            f"-"
            f"{timing['hero_end']}"
        )


    print()

    print(
        "EFFECTS:"
    )

    print(
        "- Dark cinematic grade"
    )

    print(
        "- Micro camera shake"
    )

    print(
        "- Film grain"
    )

    print(
        "- Vignette"
    )

    print(
        "- Hero slow push-in"
    )

    print(
        "- Drop impact shake"
    )

    print(
        "- Drop exposure flash"
    )

    print(
        "- Persistent titles"
    )


    ready_topics = (
        get_ready_topics()
    )


    print()

    print(
        "Ready topics:",
        len(
            ready_topics
        ),
    )


    if not ready_topics:

        print(
            "No topics ready."
        )

        return


    for (
        topic_id,
        rows,
    ) in ready_topics:

        try:

            render_topic(
                topic_id,
                rows,
            )

        except Exception as error:

            print(
                "[FAILED]",
                topic_id,
                error,
            )


    print()

    print(
        "=" * 70
    )

    print(
        "Phonk render batch finished."
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    main()