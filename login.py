from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:

    browser = p.chromium.launch_persistent_context(
        user_data_dir=r"C:\capcut_auto_profile",
        headless=False,
        channel="chrome",
        viewport={"width": 1400, "height": 900},
        args=[
            "--profile-directory=Default",
            "--window-size=1400,900",
            "--window-position=0,0"
        ]
    )

    page = browser.new_page()

    page.goto(
        "https://www.capcut.com/ai-creator/start?from_page=work_space&enter_from=new_homepage_agent",
        wait_until="domcontentloaded",
        timeout=120000
    )

    print("CapCut opened with real Chrome profile.")

    time.sleep(999999)