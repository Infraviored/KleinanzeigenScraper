#!/usr/bin/env python3
"""Log in and photograph the interface.

Every screen in this app sits behind a login, so until now the only way to know
what a change looked like was to ask the owner. Things shipped because of that
which nobody building them could see: a type scale too small to read, a dropdown
too narrow to show the town it was listing.

This starts a throwaway backend against a copy of the database, with a user whose
password is known, and walks the interface taking pictures. It touches nothing
that is running: its own port, its own database file, removed afterwards. The
backend serves the built frontend itself, so /api is same-origin and there is
nothing to proxy.

    ./venv/bin/python scripts/ui_shots.py
    ./venv/bin/python scripts/ui_shots.py --width 480      # phone width
    ./venv/bin/python scripts/ui_shots.py --keep           # leave it up to click
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMAIL = "ui-shots@localhost"
PASSWORD = "ui-shots-only"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(url, timeout=45):
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except urllib.error.HTTPError:
            return True  # an answer of any kind means it is listening
        except Exception:
            time.sleep(0.4)
    return False


def make_test_user(db_path):
    """Hashed by the backend's own bcrypt, so the login it performs will match."""
    modules = os.path.join(ROOT, "backend", "node_modules")
    script = f"""
      const bcrypt = require({os.path.join(modules, "bcrypt")!r});
      const sqlite3 = require({os.path.join(modules, "sqlite3")!r}).verbose();
      const db = new sqlite3.Database({db_path!r});
      bcrypt.hash({PASSWORD!r}, 10, (err, hash) => {{
        if (err) {{ console.error(err); process.exit(1); }}
        db.run("DELETE FROM users WHERE email = ?", [{EMAIL!r}], () => {{
          db.run("INSERT INTO users (email, password_hash, role) VALUES (?, ?, 'admin')",
            [{EMAIL!r}, hash],
            (err) => {{ if (err) {{ console.error(err); process.exit(1); }} process.exit(0); }});
        }});
      }});
    """
    subprocess.run(
        ["node", "-e", script], check=True, cwd=os.path.join(ROOT, "backend")
    )


def _find(root, name):
    for base, _dirs, files in os.walk(root):
        if name in files and os.access(os.path.join(base, name), os.X_OK):
            return os.path.join(base, name)
    return None


def build_driver(width, height):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    options = Options()
    for flag in (
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--hide-scrollbars",
    ):
        options.add_argument(flag)
    options.add_argument(f"--window-size={width},{height}")

    chrome = _find(os.path.expanduser("~/.cache/selenium/chrome"), "chrome")
    if chrome:
        options.binary_location = chrome
    driver_path = _find(
        os.path.expanduser("~/.cache/selenium/chromedriver"), "chromedriver"
    )
    service = Service(executable_path=driver_path) if driver_path else Service()
    return webdriver.Chrome(service=service, options=options)


def shoot(driver, out_dir, name, settle=1.0):
    """The whole page, not just what happens to fit above the fold."""
    time.sleep(settle)
    width = driver.get_window_size()["width"]
    height = driver.execute_script(
        "return Math.max(document.body.scrollHeight,"
        " document.documentElement.scrollHeight, 700)"
    )
    driver.set_window_size(width, min(int(height) + 100, 4000))
    time.sleep(0.35)
    path = os.path.join(out_dir, f"{name}.png")
    driver.save_screenshot(path)
    print(f"  {name}.png")


def walk(driver, base, out_dir, width, height):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    wait = WebDriverWait(driver, 20)

    driver.get(base)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input")))
    print("Photographing:")
    shoot(driver, out_dir, "01-login")

    email = driver.find_element(By.CSS_SELECTOR, "input[type='email'], input")
    password = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
    email.clear()
    email.send_keys(EMAIL)
    password.clear()
    password.send_keys(PASSWORD)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

    # Wait for the session: password input disappears and app header appears.
    try:
        wait.until(
            EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, "input[type='password']")
            )
        )
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "header")))
    except Exception:
        print("  ! still unauthenticated - the shots below are the logged-out view")
    driver.set_window_size(width, height)

    shoot(driver, out_dir, "02-landing")

    campaigns = driver.execute_script(
        "return fetch('/api/campaigns').then(r => r.json()).catch(() => [])"
    )
    if not isinstance(campaigns, list) or not campaigns:
        print("  (no campaigns in the database; stopping after the landing view)")
        return

    for campaign in campaigns:
        identifier = campaign.get("id")
        has_route = bool(campaign.get("route_id"))

        driver.get(f"{base}/#edit?campaignId={identifier}")
        time.sleep(2)
        shoot(driver, out_dir, f"03-campaign-{identifier}")

        if has_route:
            # Also capture the corridor dashboard view
            driver.get(f"{base}/#dashboard?campaignId={identifier}")
            time.sleep(2)
            shoot(driver, out_dir, f"04-corridor-dashboard-{identifier}")

            # Click "Evaluate these with AI ->" to show that the wizard is a deliberate choice
            eval_btn = None
            try:
                eval_btn = driver.find_element(By.ID, "btn-evaluate-ai")
            except Exception:
                for btn in driver.find_elements(By.CSS_SELECTOR, "button"):
                    txt = (btn.text or "").lower()
                    if (
                        ("evaluate" in txt or " ai" in txt or "ki" in txt)
                        and "campaign" not in txt
                        and btn.is_displayed()
                    ):
                        eval_btn = btn
                        break
            if eval_btn and eval_btn.is_displayed():
                eval_btn.click()
                time.sleep(1.5)
                shoot(driver, out_dir, f"05-corridor-ai-wizard-{identifier}")

            # Return to results view
            for btn in driver.find_elements(By.CSS_SELECTOR, "button"):
                txt = (btn.text or "").lower()
                if ("results" in txt or "ergebnisse" in txt) and btn.is_displayed():
                    btn.click()
                    time.sleep(1.5)
                    shoot(driver, out_dir, f"06-corridor-back-to-results-{identifier}")
                    break

            # Capture mobile portrait view (~400px wide)
            driver.set_window_size(420, 840)
            time.sleep(1)
            shoot(driver, out_dir, f"07-corridor-mobile-{identifier}")
            driver.set_window_size(width, height)
            time.sleep(0.5)

        # Check if route planner panel can be opened (for campaigns without targets)
        for button in driver.find_elements(By.CSS_SELECTOR, "button"):
            if "route" in (button.text or "").lower() and button.is_displayed():
                button.click()
                shoot(driver, out_dir, f"08-route-panel-{identifier}")
                boxes = driver.find_elements(By.CSS_SELECTOR, "input[role='combobox']")
                if boxes:
                    boxes[0].send_keys("Landsberg")
                    shoot(
                        driver, out_dir, f"09-route-dropdown-{identifier}", settle=1.6
                    )
                break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--out", default=os.path.join(ROOT, "logs", "ui-shots"))
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    db_path = f"/tmp/ui_shots_{os.getpid()}.db"
    port = free_port()
    server = None

    src_db = os.path.join(ROOT, "data", "scraper.db")
    wal_file = os.path.join(ROOT, "data", "scraper.db-wal")
    if os.path.exists(wal_file):
        try:
            subprocess.run(
                ["sqlite3", src_db, "PRAGMA wal_checkpoint(TRUNCATE);"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    try:
        shutil.copy(src_db, db_path)
        if os.path.exists(wal_file) and os.path.getsize(wal_file) > 0:
            shutil.copy(wal_file, f"{db_path}-wal")
        make_test_user(db_path)

        server = subprocess.Popen(
            ["node", os.path.join(ROOT, "backend", "server.js")],
            env=dict(os.environ, PRISMDEALS_DB=db_path, PRISMDEALS_PORT=str(port)),
            cwd=os.path.join(ROOT, "backend"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        base = f"http://127.0.0.1:{port}"
        if not wait_for(base):
            sys.exit("The throwaway backend did not come up.")

        driver = build_driver(args.width, args.height)
        try:
            walk(driver, base, args.out, args.width, args.height)
        finally:
            driver.quit()

        print(f"\n-> {args.out}")
        if args.keep:
            print(f"Still up: {base}   login {EMAIL} / {PASSWORD}")
            input("Enter to stop... ")
    finally:
        if server:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
        for ext in ("", "-wal", "-shm"):
            p = f"{db_path}{ext}"
            if os.path.exists(p):
                os.remove(p)


if __name__ == "__main__":
    main()
