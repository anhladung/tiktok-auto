from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir="capcut_profile",
        headless=False,
        viewport={"width": 1400, "height": 900},
        args=[
            "--window-size=1400,900",
            "--window-position=0,0"
        ]
    )

    page = browser.new_page()
    page.goto("https://www.capcut.com/my-edit?from_page=landing_page")
    time.sleep(6)

    page.evaluate("""
    () => {
        const box = document.createElement('div');
        box.style.position = 'fixed';
        box.style.top = '10px';
        box.style.left = '10px';
        box.style.zIndex = '999999999';
        box.style.background = 'black';
        box.style.color = 'lime';
        box.style.padding = '8px 12px';
        box.style.fontSize = '18px';
        box.style.fontFamily = 'monospace';
        box.style.borderRadius = '6px';
        box.innerText = 'X: 0 Y: 0';
        document.body.appendChild(box);

        window.addEventListener('mousemove', e => {
            box.innerText = `X: ${e.clientX} Y: ${e.clientY}`;
        }, true);
    }
    """)

    print("Rê chuột trên CapCut, góc trái sẽ hiện X/Y.")
    print("Ghi lại tọa độ dấu + và Upload from device.")

    time.sleep(999999)