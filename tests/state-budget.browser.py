"""Browser checks for state-budget.html. Needs playwright and a Chromium build.

python tests/state-budget.browser.py [screenshot-dir]
Set CHROMIUM_EXECUTABLE if Chromium is not at /opt/google/chrome/chrome.
"""
import csv
import io
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp")
SHOTS.mkdir(parents=True, exist_ok=True)


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(ROOT)))
Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}"
failures = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_EXECUTABLE", "/opt/google/chrome/chrome"))
    for name, viewport in [("desktop", {"width": 1366, "height": 900}), ("mobile", {"width": 390, "height": 844})]:
        ctx = browser.new_context(viewport=viewport, accept_downloads=True, has_touch=name == "mobile", is_mobile=name == "mobile")
        # Fonts and the Bootstrap CDN may be unreachable; the page must work without them.
        ctx.route("**/*", lambda route: route.abort() if not route.request.url.startswith(base) else route.continue_())
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "net::ERR" not in m.text and "Failed to load resource" not in m.text else None)
        page.goto(f"{base}/state-budget.html", wait_until="load")
        page.wait_for_selector("#tool:not([hidden])")
        check(page.locator("#j-name").inner_text() == "New South Wales", f"{name}: opens on NSW")
        check(page.locator("#chips .chip").count() == 8, f"{name}: eight jurisdiction buttons")
        check("$" in page.locator("#b-revenue").inner_text(), f"{name}: baseline revenue shown")
        verdict0 = page.locator("#verdict").inner_text()
        check("With no shocks" in verdict0, f"{name}: zero-shock verdict explains the published budget")

        # Every jurisdiction renders, with every preset, without script errors.
        presets = page.locator(".preset")
        for jid in ["nsw", "vic", "qld", "wa", "sa", "tas", "act", "nt"]:
            page.locator(f'#chips .chip[data-id="{jid}"]').click()
            for i in range(presets.count()):
                presets.nth(i).click()
            check(page.locator("#compare-rows tr").count() == 8, f"{name}: {jid} compare table has eight rows")
            check(page.locator("#nob-chart rect").count() >= 8, f"{name}: {jid} operating balance chart drawn")
        check(page.locator(".preset.on").inner_text() == "Mild downturn", f"{name}: last preset is highlighted")
        check("Under this scenario" in page.locator("#verdict").inner_text(), f"{name}: verdict describes the scenario")

        # Glossary pop-up opens on click/tap and closes with Escape.
        term = page.locator('.how-to .term[data-term="forward-estimates"]')
        term.click()
        pop = page.locator("#term-pop")
        check(pop.is_visible() and "three years" in pop.inner_text(), f"{name}: glossary pop-up opens")
        box = pop.bounding_box()
        check(box is not None and box["x"] >= 0 and box["x"] + box["width"] <= viewport["width"] + 1, f"{name}: pop-up stays on screen")
        page.keyboard.press("Escape")
        check(not pop.is_visible(), f"{name}: Escape closes the pop-up")
        check(page.locator(".term").count() >= 30, f"{name}: glossary terms present")
        page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
        missing = page.evaluate("""() => [...document.querySelectorAll('.term')].map(t => t.dataset.term).filter((v, i, a) => a.indexOf(v) === i)""")
        for t in missing:
            page.locator(f'.term[data-term="{t}"]').first.scroll_into_view_if_needed()
            page.locator(f'.term[data-term="{t}"]').first.click()
            ok = pop.is_visible() and len(pop.inner_text()) > 40
            page.keyboard.press("Escape")
            check(ok, f"{name}: definition for '{t}'")

        # Sliders update results; URL keeps the scenario.
        page.locator('#chips .chip[data-id="qld"]').click()
        page.locator("#reset").click()
        page.locator("#s-royalties").fill("-40")
        page.locator("#s-royalties").dispatch_event("change")
        check(page.locator("#o-royalties").inner_text() == "−40%", f"{name}: slider label shows −40%")
        check("royalties=-40" in page.url and "j=qld" in page.url, f"{name}: URL records the scenario")
        page.goto(page.url)
        page.wait_for_selector("#tool:not([hidden])")
        check(page.locator("#j-name").inner_text() == "Queensland" and page.locator("#s-royalties").input_value() == "-40", f"{name}: scenario restored from URL")

        # Download works and contains four years.
        with page.expect_download() as dl:
            page.locator("#download").click()
        text = Path(dl.value.path()).read_text(encoding="utf-8")
        rows = list(csv.reader(io.StringIO(text)))
        check(len(rows) == 5 and rows[1][0] == "Queensland", f"{name}: CSV download has four years")

        # No horizontal scrolling on the page itself.
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(overflow <= 1, f"{name}: no sideways scroll ({overflow}px)")
        page.locator("#reset").click()
        page.screenshot(path=str(SHOTS / f"state-budget-{name}.png"), full_page=True)
        page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
        page.locator('.preset[data-id="downturn"]').click()
        page.screenshot(path=str(SHOTS / f"state-budget-{name}-dark.png"), full_page=True)
        check(not errors, f"{name}: no script errors {errors[:3]}")
        ctx.close()

    # The old council address forwards to the new tool.
    page = browser.new_page()
    page.goto(f"{base}/council-stress.html")
    page.wait_for_url("**/state-budget.html")
    check(page.url.endswith("state-budget.html"), "old council address redirects")
    browser.close()
server.shutdown()
print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
