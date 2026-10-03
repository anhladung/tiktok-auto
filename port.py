from pathlib import Path
from playwright.sync_api import sync_playwright

# 1. Đường dẫn thư mục cache của profile AdsPower
PROFILE_DIR = Path(r"C:\.ADSPOWER_GLOBAL\cache\k1h5ng5w_i7ek1s")
devtools_file = PROFILE_DIR / "DevToolsActivePort"

def connect_adspower_profile():
    if not devtools_file.exists():
        raise RuntimeError(
            "\n[!] Không tìm thấy file DevToolsActivePort!\n"
            "--> Bạn vui lòng bấm nút [Open] profile trong phần mềm AdsPower trước, sau đó chạy lại script."
        )

    # Đọc port ngẫu nhiên và endpoint do AdsPower sinh ra
    lines = devtools_file.read_text().splitlines()
    port = int(lines[0].strip())
    browser_endpoint = lines[1].strip()
    ws_endpoint = f"ws://127.0.0.1:{port}{browser_endpoint}"

    print(f"[*] DevTools Port: {port}")
    print(f"[*] WS Endpoint: {ws_endpoint}")

    with sync_playwright() as p:
        # Kết nối trực tiếp qua WebSocket CDP (Miễn phí 100%, không cần gói Local API)
        browser = p.chromium.connect_over_cdp(ws_endpoint)
        context = browser.contexts[0]

        print(f"[+] Kết nối thành công! Tổng số tab đang mở: {len(context.pages)}")

        # Lọc bỏ tab mặc định của AdsPower dashboard nếu có
        work_pages = [page for page in context.pages if "start.adspower.net" not in page.url]
        page = work_pages[-1] if work_pages else context.new_page()

        print(f"[+] Tab làm việc hiện tại: {page.url}")

        # ========================================================
        # CODE AUTOMATION CỦA BẠN BẮT ĐẦU TỪ ĐÂY
        # ========================================================
        # Ví dụ:
        # page.goto("https://www.tiktok.com")
        # print("Tiêu đề:", page.title())

        input("\nNhấn Enter để Playwright ngắt kết nối (Trình duyệt AdsPower vẫn giữ nguyên)...")

if __name__ == "__main__":
    connect_adspower_profile()