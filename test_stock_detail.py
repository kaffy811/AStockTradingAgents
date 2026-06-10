#!/usr/bin/env python3
"""
Playwright tests for StockDetailView page.
"""
import os
import sys
import time
import re
import subprocess
import json

# Clear proxy settings before importing playwright
os.environ.pop("http_proxy", None)
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("https_proxy", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"

from playwright.sync_api import sync_playwright, Page

BASE_URL = "http://localhost:3002"
BACKEND_URL = "http://localhost:8000"
USERNAME = "testuser"
PASSWORD = "testpass123"

results = []


def log(msg):
    print(msg, flush=True)


def record(test_name, passed, details=""):
    status = "PASS" if passed else "FAIL"
    results.append((test_name, status, details))
    log(f"  [{status}] {test_name}" + (f": {details}" if details else ""))


def get_auth_token():
    """Get auth token from backend API via curl (bypasses proxy)."""
    result = subprocess.run(
        [
            "curl", "-s",
            "-X", "POST",
            f"{BACKEND_URL}/api/v1/auth/login",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"username": USERNAME, "password": PASSWORD}),
        ],
        env={**os.environ, "NO_PROXY": "localhost,127.0.0.1", "no_proxy": "localhost,127.0.0.1"},
        capture_output=True,
        text=True,
        timeout=10,
    )
    data = json.loads(result.stdout)
    return data.get("access_token", "")


def inject_auth(page: Page, token: str):
    """Inject auth token into localStorage and reload page."""
    page.evaluate(f"""
        localStorage.setItem('ta_token', '{token}');
        localStorage.setItem('ta_user', '{USERNAME}');
    """)


def setup_auth(page: Page, token: str):
    """Navigate to base URL and inject token."""
    # First navigate to the site to get origin, then inject token
    page.goto(f"{BASE_URL}/")
    page.wait_for_load_state("domcontentloaded", timeout=10000)
    inject_auth(page, token)
    # Reload to let Vue pick up the token
    page.reload()
    page.wait_for_load_state("networkidle", timeout=10000)


def test_login(page: Page, token: str):
    log("\n=== TEST 1: Login ===")
    try:
        setup_auth(page, token)
        current_url = page.url
        page_text = page.evaluate("document.body.innerText")
        # If still showing login card, auth failed
        is_logged_in = "登录" not in page_text or "登出" in page_text or "watchlist" in current_url.lower()
        # Check that login form is NOT the main content
        login_form_visible = page.query_selector("input[placeholder='username']")
        if not login_form_visible:
            record("Login: token injected, login form hidden", True, f"URL: {current_url}")
        else:
            record("Login: token injected, login form hidden", False,
                   "Login form still visible after token injection")
        page.screenshot(path="/tmp/after_login.png")
        log("  Screenshot saved to /tmp/after_login.png")
        return True
    except Exception as e:
        record("Login: token injected, login form hidden", False, str(e))
        return False


def test_cn_stock(page: Page, token: str):
    log("\n=== TEST 2: /stocks/CN/000001 ===")
    console_msgs = []

    def handle_console(msg):
        console_msgs.append(msg)

    page.on("console", handle_console)

    # Navigate with auth already set
    page.goto(f"{BASE_URL}/stocks/CN/000001")

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        log("  WARNING: networkidle timeout, continuing")

    # Wait for h2 or main content
    try:
        page.wait_for_selector("h2, h1, .stock-name, [class*='title'], [class*='badge']", timeout=15000)
    except Exception:
        log("  WARNING: No h2/h1/badge found within 15s")

    page.screenshot(path="/tmp/cn_stock_000001.png")
    log("  Screenshot saved to /tmp/cn_stock_000001.png")

    page_text = page.evaluate("document.body.innerText")
    log(f"  Page text snippet (first 300): {page_text[:300]}")

    # Check stock name / title
    if "平安银行" in page_text or "000001" in page_text:
        record("Stock name/code visible (平安银行 or 000001)", True)
    else:
        record("Stock name/code visible (平安银行 or 000001)", False,
               "Neither found in page")

    # Check market badge "CN"
    if "CN" in page_text:
        record("Market badge shows CN", True)
    else:
        record("Market badge shows CN", False, "CN not found in page text")

    # Check no JS errors
    errors = [m for m in console_msgs if m.type == "error"]
    js_errors = [e.text for e in errors if "favicon" not in e.text.lower()]
    if not js_errors:
        record("No JS errors in console", True)
    else:
        record("No JS errors in console", False, f"Errors: {js_errors[:3]}")

    # Log Vue warnings
    warnings = [m for m in console_msgs if m.type == "warning"]
    vue_warnings = [w.text for w in warnings if "[Vue" in w.text or "vue warn" in w.text.lower()]
    if vue_warnings:
        log(f"  Vue warnings: {vue_warnings[:5]}")

    # Check 返回 button
    back_btn = page.query_selector("button:has-text('返回'), a:has-text('返回')")
    record("返回 button exists", back_btn is not None)

    # Check cards
    cards_to_check = [
        ("技术图表", "技术面图表"),  # actual UI text is "技术面图表"
        ("最近 72 小时相关新闻", "72"),
        ("本 APP 综合分析", "综合分析"),
        ("历史报告", "历史报告"),
        ("同行业热门股票", "同行业热门"),
    ]

    for card_name, search_text in cards_to_check:
        found = search_text in page_text
        record(f"Card '{card_name}' exists", found)

    # Check no "undefined" or "null" text in visible content
    undefined_matches = re.findall(r'\bundefined\b', page_text)
    null_matches = re.findall(r'\bnull\b', page_text)

    record("No 'undefined' text visible", not bool(undefined_matches),
           f"{len(undefined_matches)} occurrences" if undefined_matches else "")
    record("No 'null' text visible", not bool(null_matches),
           f"{len(null_matches)} occurrences: {null_matches[:3]}" if null_matches else "")

    # Wait additional 5 seconds and check hot stocks section
    time.sleep(5)
    page_text2 = page.evaluate("document.body.innerText")

    hot_section_present = "同行业热门" in page_text2
    has_error = "加载失败" in page_text2
    # 500 from API is OK if it shows EmptyState, check for raw "500" in visible text
    has_500_visible = re.search(r'\b500\b', page_text2) is not None

    if hot_section_present and not has_error:
        record("Hot stocks section: no error after 5s wait", True,
               "Section present, no load failure")
    elif hot_section_present and has_error:
        record("Hot stocks section: no error after 5s wait", False, "Section shows 加载失败")
    else:
        record("Hot stocks section: no error after 5s wait", False, "Section not found in page")

    page.screenshot(path="/tmp/cn_stock_000001_after_wait.png")
    log("  Screenshot (after 5s wait) saved to /tmp/cn_stock_000001_after_wait.png")

    return console_msgs


def test_hk_stock(page: Page, token: str):
    log("\n=== TEST 3: /stocks/HK/00700 ===")
    console_msgs = []
    page.on("console", lambda msg: console_msgs.append(msg))

    page.goto(f"{BASE_URL}/stocks/HK/00700")

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    time.sleep(8)

    page.screenshot(path="/tmp/hk_stock_00700.png")
    log("  Screenshot saved to /tmp/hk_stock_00700.png")

    page_text = page.evaluate("document.body.innerText")
    log(f"  Page text snippet: {page_text[:300]}")

    # Check market badge "HK"
    if "HK" in page_text:
        record("HK: market badge shows HK", True)
    else:
        record("HK: market badge shows HK", False, "HK not found in page text")

    # Check hot stocks section shows unsupported or EmptyState (not 500 error)
    hot_unsupported = "暂不支持" in page_text or "暂无" in page_text or "当前市场" in page_text
    has_500 = "500" in page_text and "Internal Server Error" in page_text

    if not has_500:
        record("HK: hot stocks section no 500 error", True,
               "暂不支持/EmptyState" if hot_unsupported else "No 500 error found")
    else:
        record("HK: hot stocks section no 500 error", False, "Found 500 error in page")

    # Check no undefined/null
    undefined_matches = re.findall(r'\bundefined\b', page_text)
    null_matches = re.findall(r'\bnull\b', page_text)

    record("HK: No 'undefined' text visible", not bool(undefined_matches),
           f"{len(undefined_matches)} occurrences" if undefined_matches else "")
    record("HK: No 'null' text visible", not bool(null_matches),
           f"{len(null_matches)} occurrences" if null_matches else "")


def test_watchlist_navigation(page: Page):
    log("\n=== TEST 4: Watchlist Navigation ===")

    page.goto(f"{BASE_URL}/watchlist")

    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    time.sleep(5)

    page.screenshot(path="/tmp/watchlist.png")
    log("  Screenshot saved to /tmp/watchlist.png")

    page_text = page.evaluate("document.body.innerText")
    log(f"  Watchlist page text (first 400): {page_text[:400]}")

    # Check for 详情 button
    detail_btn = page.query_selector("button:has-text('详情'), a:has-text('详情')")
    record("Watchlist: 详情 button exists", detail_btn is not None)

    if detail_btn:
        detail_btn.click()
        # Wait for Vue Router navigation (SPA navigation, URL may update asynchronously)
        try:
            page.wait_for_url(lambda url: "/stocks/" in url, timeout=8000)
        except Exception:
            time.sleep(3)

        time.sleep(3)
        current_url = page.url
        page_text2 = page.evaluate("document.body.innerText")

        # Also check page content as fallback (Vue Router may have navigated)
        navigated_by_url = "/stocks/" in current_url
        navigated_by_content = "技术面图表" in page_text2 or "平安银行" in page_text2 or "000001" in page_text2

        if navigated_by_url or navigated_by_content:
            record("Watchlist: navigates to /stocks/ URL", True,
                   f"URL: {current_url}" + (" (content confirms nav)" if not navigated_by_url else ""))
        else:
            record("Watchlist: navigates to /stocks/ URL", False,
                   f"URL: {current_url}, no stock content found")

        # Check page renders without errors
        has_error = "500" in page_text2 and "Error" in page_text2
        record("Watchlist: stock page renders without errors", not has_error)

        page.screenshot(path="/tmp/watchlist_to_stock.png")
        log("  Screenshot saved to /tmp/watchlist_to_stock.png")
    else:
        record("Watchlist: navigates to /stocks/ URL", False, "No 详情 button to click")
        record("Watchlist: stock page renders without errors", False, "No 详情 button found")


def test_industry_hot_navigation(page: Page):
    log("\n=== TEST 5: IndustryHot Navigation ===")

    page.goto(f"{BASE_URL}/industries")

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    time.sleep(5)

    page.screenshot(path="/tmp/industries.png")
    log("  Screenshot saved to /tmp/industries.png")

    page_text = page.evaluate("document.body.innerText")
    log(f"  Industries page text (first 400): {page_text[:400]}")

    # Check for 详情 button in table
    detail_btn = page.query_selector("button:has-text('详情'), a:has-text('详情')")
    record("Industries: 详情 button exists", detail_btn is not None)

    if detail_btn:
        detail_btn.click()
        # Wait for Vue Router navigation (SPA navigation)
        try:
            page.wait_for_url(lambda url: "/stocks/" in url, timeout=8000)
        except Exception:
            time.sleep(3)

        time.sleep(3)
        current_url = page.url
        page_text2 = page.evaluate("document.body.innerText")

        # Check URL or page content for navigation confirmation
        navigated_by_url = "/stocks/" in current_url
        navigated_by_content = "技术面图表" in page_text2 or "← 返回" in page_text2

        if navigated_by_url or navigated_by_content:
            record("Industries: navigates to /stocks/ URL", True,
                   f"URL: {current_url}" + (" (content confirms nav)" if not navigated_by_url else ""))
        else:
            record("Industries: navigates to /stocks/ URL", False,
                   f"URL: {current_url}, no stock content found")

        page.screenshot(path="/tmp/industry_to_stock.png")
        log("  Screenshot saved to /tmp/industry_to_stock.png")
    else:
        record("Industries: navigates to /stocks/ URL", False, "No 详情 button to click")


def test_mobile_viewport(page: Page):
    log("\n=== TEST 6: Mobile Viewport (375px) ===")

    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{BASE_URL}/stocks/CN/000001")

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    time.sleep(3)

    page.screenshot(path="/tmp/mobile_375.png")
    log("  Screenshot saved to /tmp/mobile_375.png")

    # Check for horizontal overflow
    result = page.evaluate("""
        () => ({
            scrollWidth: document.body.scrollWidth,
            clientWidth: document.body.clientWidth,
            documentScrollWidth: document.documentElement.scrollWidth,
            documentClientWidth: document.documentElement.clientWidth
        })
    """)

    log(f"  body.scrollWidth={result['scrollWidth']}, body.clientWidth={result['clientWidth']}")
    log(f"  document.scrollWidth={result['documentScrollWidth']}, document.clientWidth={result['documentClientWidth']}")

    no_body_overflow = result['scrollWidth'] <= result['clientWidth']
    no_doc_overflow = result['documentScrollWidth'] <= result['documentClientWidth']

    record("Mobile 375px: no horizontal scroll (body)", no_body_overflow,
           f"scrollWidth={result['scrollWidth']}, clientWidth={result['clientWidth']}")
    record("Mobile 375px: no horizontal scroll (document)", no_doc_overflow,
           f"scrollWidth={result['documentScrollWidth']}, clientWidth={result['documentClientWidth']}")


def main():
    log("=" * 60)
    log("StockDetailView Playwright Tests")
    log("=" * 60)

    # Get auth token via curl (proxy-bypassed)
    log("\nGetting auth token from backend...")
    try:
        token = get_auth_token()
        log(f"  Got token: {token[:30]}...")
    except Exception as e:
        log(f"  FATAL: Could not get auth token: {e}")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )

        # Use direct proxy to bypass system proxy for localhost
        context = browser.new_context(
            proxy={"server": "direct://", "bypass": "localhost,127.0.0.1"},
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        # Test 1: Login via token injection
        try:
            test_login(page, token)
        except Exception as e:
            record("Login: token injected", False, str(e))
            log(f"  Login error: {e}")

        # Test 2: CN Stock
        try:
            test_cn_stock(page, token)
        except Exception as e:
            record("CN Stock test (exception)", False, str(e))
            log(f"  CN Stock error: {e}")
            try:
                page.screenshot(path="/tmp/cn_stock_error.png")
            except Exception:
                pass

        # Test 3: HK Stock
        try:
            test_hk_stock(page, token)
        except Exception as e:
            record("HK Stock test (exception)", False, str(e))
            log(f"  HK Stock error: {e}")

        # Test 4: Watchlist Navigation
        try:
            test_watchlist_navigation(page)
        except Exception as e:
            record("Watchlist navigation (exception)", False, str(e))
            log(f"  Watchlist error: {e}")

        # Test 5: Industry Hot Navigation
        try:
            test_industry_hot_navigation(page)
        except Exception as e:
            record("Industry hot navigation (exception)", False, str(e))
            log(f"  Industry hot error: {e}")

        # Test 6: Mobile Viewport
        page.set_viewport_size({"width": 1280, "height": 800})  # reset
        try:
            test_mobile_viewport(page)
        except Exception as e:
            record("Mobile viewport (exception)", False, str(e))
            log(f"  Mobile viewport error: {e}")

        browser.close()

    # Print summary
    log("\n" + "=" * 60)
    log("TEST SUMMARY")
    log("=" * 60)

    passed = 0
    failed = 0
    for test_name, status, details in results:
        detail_str = f" ({details})" if details else ""
        log(f"  [{status}] {test_name}{detail_str}")
        if status == "PASS":
            passed += 1
        else:
            failed += 1

    log(f"\nTotal: {passed + failed} tests | {passed} PASSED | {failed} FAILED")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
