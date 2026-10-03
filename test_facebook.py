from playwright.sync_api import sync_playwright
import time

PROFILE = r"C:\facebook_auto_profile_01"

with sync_playwright() as p:
    print("Starting Chrome...")

    context = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE,
        channel="chrome",
        headless=False,
        viewport={
            "width": 1400,
            "height": 900,
        },
    )

    print("Chrome started")
    print("Pages:", len(context.pages))

    if context.pages:
        page = context.pages[0]
    else:
        page = context.new_page()

    print("Current URL:", page.url)

    print("Opening Facebook...")
    page.goto(
        "https://www.facebook.com/",
        wait_until="domcontentloaded",
        timeout=120000,
    )

    print("Facebook URL:", page.url)
    print("Title:", page.title())

    time.sleep(120)