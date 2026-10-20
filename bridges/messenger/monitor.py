import asyncio
import os
import sys
import argparse
import httpx
from datetime import datetime

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import settings

SESSION_DIR = os.path.join(os.path.dirname(__file__), "session")
BACKEND_WEBHOOK = f"http://localhost:{settings.APP_PORT}/api/messenger/incoming"
BACKEND_IMAGE_WEBHOOK = f"http://localhost:{settings.APP_PORT}/api/messenger/incoming-image"

async def run_login():
    """Interactive headed login to save Facebook/Messenger session cookies."""
    from playwright.async_api import async_playwright
    os.makedirs(SESSION_DIR, exist_ok=True)

    print("🌐 Opening Chromium for Facebook/Messenger Login...")
    print("👉 Please log into your Facebook account in the browser window.")
    print("👉 Once you are logged in and can view your Messenger chats, return here and press ENTER.\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=False,
            args=["--disable-notifications"]
        )
        page = await browser.new_page()
        try:
            await page.goto("https://www.facebook.com/messages", wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass

        input("Press [ENTER] after logging in successfully to save your session...")
        await browser.close()
        print("✅ Session successfully saved! You can now start the background monitor.")

async def run_monitor():
    """Headless background listener for incoming Messenger CR group messages and image notices."""
    import base64
    import hashlib
    from playwright.async_api import async_playwright

    if not os.path.exists(SESSION_DIR):
        print("⚠️ No saved session found! Please run login first:")
        print("   ./run.sh messenger-login")
        return

    thread_url = settings.MESSENGER_CR_GROUP_URL
    print(f"🚀 Starting Headless Messenger Monitor on: {thread_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=True,
            args=["--disable-notifications", "--disable-gpu"]
        )
        page = await browser.new_page()
        try:
            await page.goto(thread_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"Navigation warning: {e}. Proceeding with loaded DOM...")

        await page.wait_for_timeout(4000)
        print("✔ Messenger group thread opened. Establishing baseline of existing messages...")

        seen_messages = set()
        seen_image_hashes = set()
        loop_count = 0

        # Baseline Initialization Pass: Cache already rendered messages and images so they are NOT re-broadcasted!
        try:
            initial_msgs = await page.query_selector_all('[role="row"] [dir="auto"], [role="gridcell"] [dir="auto"], div[dir="auto"]')
            for el in initial_msgs:
                try:
                    t = (await el.inner_text()).strip()
                    if t:
                        seen_messages.add(t)
                except Exception:
                    pass

            initial_imgs = await page.query_selector_all(
                '[role="row"] img, [role="gridcell"] img, div[data-scope="messages_table"] img, img[src*="fbcdn.net"], img[src*="scontent"]'
            )
            for img_el in initial_imgs:
                try:
                    src = (await img_el.get_attribute("src")) or ""
                    if src:
                        seen_image_hashes.add(src[:120])
                    b = await img_el.screenshot(type="png")
                    if b:
                        seen_image_hashes.add(hashlib.md5(b).hexdigest())
                except Exception:
                    pass
            print(f"✔ Baseline established ({len(seen_messages)} messages, {len(seen_image_hashes)} images cached). Listening strictly for NEW incoming notices...")
        except Exception as e:
            print(f"⚠️ Warning during initial baseline cache: {e}")

        while True:
            try:
                loop_count += 1
                if loop_count % 10 == 0:
                    print(f"💓 [Active Monitor] Listening to Messenger CR Group (Thread: {settings.MESSENGER_CR_THREAD_ID})...")

                # 1. Check recent text message elements
                messages = await page.query_selector_all('[role="row"] [dir="auto"], [role="gridcell"] [dir="auto"], div[dir="auto"]')
                for el in messages[-5:]:
                    try:
                        text = (await el.inner_text()).strip()
                        if text and text not in seen_messages and len(text) > 4:
                            seen_messages.add(text)
                            print(f"\n📩 New Messenger Text Message Detected: {text[:70]}...")

                            async with httpx.AsyncClient(timeout=10.0) as client:
                                try:
                                    headers = {"X-Bridge-Token": settings.SECRET_KEY}
                                    resp = await client.post(BACKEND_WEBHOOK, json={
                                        "sender_name": "CR Group Member",
                                        "message_text": text
                                    }, headers=headers)
                                    print(f"✔ Relayed to Backend -> {resp.json().get('status', 'ok')}")
                                except Exception as err:
                                    print(f"⚠️ Warning: FastAPI server not reachable: {err}")
                    except Exception:
                        pass

                # 2. Check recent photo/image notice elements
                image_elements = await page.query_selector_all(
                    '[role="row"] img, [role="gridcell"] img, div[data-scope="messages_table"] img, img[src*="fbcdn.net"], img[src*="scontent"], img[alt*="photo" i], img[alt*="image" i]'
                )
                for img_el in image_elements[-8:]:
                    try:
                        box = await img_el.bounding_box()
                        if not box or box["width"] < 75 or box["height"] < 75:
                            continue

                        src = (await img_el.get_attribute("src")) or ""
                        if "rsrc.php" in src or "data:image/svg" in src or "emoji" in src.lower():
                            continue

                        img_bytes = await img_el.screenshot(type="png")
                        if not img_bytes or len(img_bytes) < 200:
                            continue

                        img_hash = hashlib.md5(img_bytes).hexdigest()
                        if img_hash in seen_image_hashes:
                            continue

                        seen_image_hashes.add(img_hash)
                        print(f"\n📸 New Messenger Photo/Notice Detected! (Size: {int(box['width'])}x{int(box['height'])}, Hash: {img_hash[:8]})")

                        # Extract any accompanying caption from message bubble
                        caption = ""
                        try:
                            caption = await img_el.evaluate('el => { const row = el.closest("[role=\'row\']") || el.closest("[role=\'gridcell\']"); return row ? row.innerText : ""; }') or ""
                        except Exception:
                            pass

                        b64_str = base64.b64encode(img_bytes).decode("utf-8")

                        async with httpx.AsyncClient(timeout=60.0) as client:
                            try:
                                print("🤖 Passing photo notice to Gemini Vision backend for OCR & verification...")
                                headers = {"X-Bridge-Token": settings.SECRET_KEY}
                                resp = await client.post(BACKEND_IMAGE_WEBHOOK, json={
                                    "image_base64": b64_str,
                                    "caption": caption.strip(),
                                    "sender_name": "Coordinator / CR Group"
                                }, headers=headers)
                                res_data = resp.json()
                                if res_data.get("was_relayed"):
                                    print(f"✅ Photo Notice Processed & Relayed to WhatsApp: {res_data.get('details', '')[:60]}...")
                                else:
                                    print(f"ℹ️ Image evaluated: {res_data.get('details', 'Not an academic notice')}")
                            except Exception as err:
                                print(f"⚠️ Warning: FastAPI server error on incoming-image: {repr(err)}")
                    except Exception:
                        pass

                await asyncio.sleep(4)
            except (asyncio.CancelledError, KeyboardInterrupt):
                break
            except Exception as e:
                await asyncio.sleep(5)

        await browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Messenger CR Group Monitor")
    parser.add_argument("--login", action="store_true", help="Launch browser to log in and save session")
    args = parser.parse_args()

    if args.login:
        asyncio.run(run_login())
    else:
        asyncio.run(run_monitor())
