import json
import os
import random


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

PRODUCTS_ROOT = os.path.join(
    BASE_DIR,
    "products"
)

ASSETS_DIR = os.path.join(
    BASE_DIR,
    "assets"
)

MUSIC_DIR = os.path.join(
    ASSETS_DIR,
    "music"
)

SFX_DIR = os.path.join(
    ASSETS_DIR,
    "sfx"
)

TEMPLATE_DIR = os.path.join(
    ASSETS_DIR,
    "templates"
)


# =====================================
# CATEGORIES
# =====================================

ENABLED_CATEGORIES = [
    "snack",
    "keychain",
    "phone_case",
]


CATEGORY_CONFIG = {
    "snack": {
        "clips": [
            {
                "clip_index": 1,
                "template_name": "clip_01",
            },
        ],
    },

    "keychain": {
        "clips": [
            {
                # Pipeline mới chỉ còn 1 clip.
                # Giữ nguyên semantics clip 02 để đồng bộ
                # với render worker và output video.
                "clip_index": 2,
                "template_name": "clip_02",
            },
        ],
    },

    "phone_case": {
        "clips": [
            {
                # Pipeline hiện tại chỉ còn Clip 01:
                # 01_clip_01_first_frame
                # -> 02_clip_01_last_frame.
                "clip_index": 1,
                "template_name": "clip_01",
            },
        ],
    },
}


# =====================================
# MUSIC
# =====================================

def get_random_music():
    if not os.path.isdir(
        MUSIC_DIR
    ):
        raise Exception(
            f"Music folder not found: {MUSIC_DIR}"
        )

    files = [
        filename
        for filename in os.listdir(
            MUSIC_DIR
        )
        if filename.lower().endswith(
            (
                ".mp3",
                ".wav",
            )
        )
    ]

    if not files:
        raise Exception(
            "No background music found."
        )

    selected_file = random.choice(
        files
    )

    return os.path.join(
        "assets",
        "music",
        selected_file
    ).replace(
        "\\",
        "/"
    )


# =====================================
# SFX
# =====================================

def get_random_sfx(sfx_category):
    """
    sfx_category là category của hiệu ứng âm thanh
    được khai báo trong file template.

    Ví dụ:

    assets/sfx/click/
    assets/sfx/whoosh/
    assets/sfx/footstep/
    assets/sfx/fabric/
    assets/sfx/metal/
    assets/sfx/swing/

    Phone case và mask có thể dùng các category SFX
    được khai báo trực tiếp trong template tương ứng:

    assets/templates/phone_case/clip_01.json
    assets/templates/mask/clip_01.json

    Keychain hiện chỉ dùng:
    assets/templates/keychain/clip_02.json
    """

    folder = os.path.join(
        SFX_DIR,
        sfx_category
    )

    if not os.path.isdir(
        folder
    ):
        raise Exception(
            f"SFX folder not found: {folder}"
        )

    files = [
        filename
        for filename in os.listdir(
            folder
        )
        if filename.lower().endswith(
            (
                ".mp3",
                ".wav",
            )
        )
    ]

    if not files:
        raise Exception(
            f"No SFX found in {sfx_category}"
        )

    selected_file = random.choice(
        files
    )

    return os.path.join(
        "assets",
        "sfx",
        sfx_category,
        selected_file
    ).replace(
        "\\",
        "/"
    )


# =====================================
# TEMPLATE
# =====================================

def find_template_path(
    category,
    template_name
):
    """
    Ưu tiên template riêng theo category.

    Thứ tự tìm:

    1. assets/templates/{category}/{template_name}.json
    2. assets/templates/{category}_{template_name}.json
    3. assets/templates/{template_name}.json

    Cách thứ 3 giúp template cũ của son vẫn tiếp tục chạy.
    """

    possible_paths = [
        os.path.join(
            TEMPLATE_DIR,
            category,
            f"{template_name}.json"
        ),

        os.path.join(
            TEMPLATE_DIR,
            f"{category}_{template_name}.json"
        ),

        os.path.join(
            TEMPLATE_DIR,
            f"{template_name}.json"
        ),
    ]

    for path in possible_paths:
        if os.path.isfile(
            path
        ):
            return path

    searched_paths = "\n".join(
        possible_paths
    )

    raise FileNotFoundError(
        "Audio template not found.\n"
        f"Category: {category}\n"
        f"Template: {template_name}\n"
        f"Searched:\n{searched_paths}"
    )


def load_template(
    category,
    template_name
):
    path = find_template_path(
        category,
        template_name
    )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:
        template = json.load(
            file
        )

    if "events" not in template:
        raise ValueError(
            f"Template missing events: {path}"
        )

    return template, path


# =====================================
# BUILD ONE CLIP
# =====================================

def build_clip(
    category,
    template_name,
    clip_index
):
    template, template_path = load_template(
        category,
        template_name
    )

    events = []

    # =====================================
    # TARGET SFX PER CLIP
    # =====================================

    # Giữ nguyên logic cũ:
    # mỗi clip chọn tối đa 2 SFX.
    TARGET_SFX = 2

    # =====================================
    # FILTER AVAILABLE EVENTS
    # =====================================

    candidates = []

    for event in template["events"]:
        importance = event.get(
            "importance",
            "medium"
        )

        # Giữ nguyên cách tính trọng số.
        if importance == "high":
            weight = 3

        elif importance == "medium":
            weight = 2

        else:
            weight = 1

        candidates.append({
            "time": float(
                event["time"]
            ),

            "category": event[
                "category"
            ],

            "volume": event.get(
                "volume",
                0.3
            ),

            "weight": weight,
        })

    # =====================================
    # SORT BY IMPORTANCE
    # =====================================

    candidates.sort(
        key=lambda item: item["weight"],
        reverse=True
    )

    # =====================================
    # PICK 2 IMPORTANT EVENTS
    # =====================================

    selected = []

    for item in candidates:
        # Giữ nguyên khoảng cách tối thiểu
        # giữa hai hiệu ứng là 1.5 giây.
        too_close = False

        for selected_item in selected:
            if abs(
                item["time"]
                - selected_item["time"]
            ) < 1.5:
                too_close = True

        if too_close:
            continue

        selected.append(
            item
        )

        if len(selected) == TARGET_SFX:
            break

    # =====================================
    # FALLBACK
    # =====================================

    if len(selected) < TARGET_SFX:
        remaining = [
            item
            for item in candidates
            if item not in selected
        ]

        random.shuffle(
            remaining
        )

        while (
            len(selected) < TARGET_SFX
            and remaining
        ):
            selected.append(
                remaining.pop()
            )

    # =====================================
    # CREATE FINAL EVENTS
    # =====================================

    for item in selected:
        events.append({
            "time": item["time"],

            "file": get_random_sfx(
                item["category"]
            ),

            "volume": item["volume"],
        })

    events.sort(
        key=lambda item: item["time"]
    )

    template_relative_path = (
        os.path.relpath(
            template_path,
            BASE_DIR
        )
        .replace(
            "\\",
            "/"
        )
    )

    return {
        "clip": clip_index,
        "template": template_relative_path,
        "events": events,
    }


# =====================================
# BUILD PRODUCT
# =====================================

def build_audio_plan(
    category,
    product_id
):
    category_config = CATEGORY_CONFIG.get(
        category
    )

    if category_config is None:
        raise ValueError(
            f"Category config not found: {category}"
        )

    clips = []

    for clip_config in category_config[
        "clips"
    ]:
        clips.append(
            build_clip(
                category=category,
                template_name=clip_config[
                    "template_name"
                ],
                clip_index=clip_config[
                    "clip_index"
                ],
            )
        )

    plan = {
        "category": category,

        "product_id": product_id,

        "background_music": {
            "file": get_random_music(),
            "volume": 0.5,
        },

        "clips": clips,
    }

    output_dir = os.path.join(
        PRODUCTS_ROOT,
        category,
        product_id,
        "output",
        "audio_plan"
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    output_path = os.path.join(
        output_dir,
        f"{product_id}.json"
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            plan,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("=" * 60)
    print(
        "Audio plan created:"
    )
    print(
        f"Category: {category}"
    )
    print(
        f"Product: {product_id}"
    )
    print(
        f"Output: {output_path}"
    )

    for clip in clips:
        print(
            f"Clip {clip['clip']} "
            f"SFX events: "
            f"{len(clip['events'])}"
        )

        for event in clip[
            "events"
        ]:
            print(
                f" - {event['time']:.2f}s | "
                f"{event['file']}"
            )

    print("=" * 60)


# =====================================
# GET PRODUCTS
# =====================================

def get_products(
    category
):
    category_dir = os.path.join(
        PRODUCTS_ROOT,
        category
    )

    if not os.path.isdir(
        category_dir
    ):
        return []

    products = [
        name
        for name in os.listdir(
            category_dir
        )
        if os.path.isdir(
            os.path.join(
                category_dir,
                name
            )
        )
    ]

    products.sort(
        key=str.lower
    )

    return products


# =====================================
# BUILD ALL
# =====================================

def build_all_products():
    total_products = 0
    success_count = 0
    failed_count = 0

    for category in ENABLED_CATEGORIES:
        products = get_products(
            category
        )

        total_products += len(
            products
        )

        print("=" * 60)
        print(
            "Category:",
            category
        )
        print(
            "Products:",
            products
        )

        if not products:
            print(
                "No products found."
            )

            continue

        for product_id in products:
            try:
                build_audio_plan(
                    category=category,
                    product_id=product_id
                )

                success_count += 1

            except Exception as error:
                failed_count += 1

                print(
                    "FAILED:",
                    f"{category}/{product_id}"
                )

                print(
                    error
                )

    print("=" * 60)
    print(
        "AUDIO PLANNER FINISHED"
    )
    print(
        "Products scanned:",
        total_products
    )
    print(
        "Success:",
        success_count
    )
    print(
        "Failed:",
        failed_count
    )
    print("=" * 60)


# =====================================
# RUN
# =====================================

if __name__ == "__main__":
    build_all_products()
