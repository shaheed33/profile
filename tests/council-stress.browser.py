"""Optional browser checks. Requires playwright and a local Chromium install.

python tests/council-stress.browser.py
Set CHROMIUM_EXECUTABLE if Chromium is not at /usr/bin/chromium.
Runs an isolated temporary HTTP server; screenshots are written to /tmp.
"""
import csv
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import os
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT)))
Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_port}'
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_EXECUTABLE', '/usr/bin/chromium'),
                                    headless=True, args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1100}, accept_downloads=True)
        # The tool must remain functional without third-party fonts or CSS.
        context.route('**/*', lambda route: route.continue_() if urlsplit(route.request.url).hostname == '127.0.0.1' else route.abort())
        page = context.new_page()
        errors, failed_local = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('response', lambda r: failed_local.append((r.url, r.status)) if r.status >= 400 else None)
        page.goto(base + '/council-stress.html', wait_until='networkidle')
        assert page.locator('#council').input_value() == 'Kiama'
        assert page.locator('#council option').count() == 128
        assert page.locator('#scenario-balance').inner_text() == '−$5.1m'
        assert page.locator('#scenario-rows tr').count() == 3
        assert page.locator('#history-rows tr').count() == 3
        assert 'Not collected' in page.locator('#history-rows tr').last.inner_text()
        assert 'Insufficient history' in page.locator('#model-rows').inner_text()
        page.screenshot(path='/tmp/council-stress-desktop.png', full_page=True)

        with page.expect_download() as downloaded:
            page.locator('#download').click()
        download = downloaded.value
        rows = list(csv.DictReader(io.StringIO(Path(download.path()).read_text())))
        assert len(rows) == 3 and rows[0]['council'] == 'Kiama'
        assert float(rows[0]['assumed_payroll_share']) == .35
        assert float(rows[2]['scenario_balance_aud']) < float(rows[0]['scenario_balance_aud'])
        assert 'not a forecast' in rows[0]['interpretation']

        page.locator('#reset').click()
        assert page.locator('#scenario-balance').inner_text() == '−$0.7m'
        assert page.locator('#funding-pressure').inner_text() == '$0.0m'
        page.locator('#horizon').select_option('2')
        assert page.locator('#scenario-rows tr').count() == 2
        page.locator('#grant-cut').focus()
        page.keyboard.press('ArrowRight')
        assert page.locator('#grant-value').inner_text() == '1%'
        assert page.locator('#funding-pressure').inner_text() != '$0.0m'

        names = page.locator('#council option').all_text_contents()
        missing = []
        for name in names:
            page.locator('#council').select_option(name)
            assert page.locator('#council-name').inner_text() == name
            if page.locator('#missing-data').is_visible():
                missing.append(name)
                assert page.locator('#grant-cut').is_disabled()
                assert page.locator('#results').is_hidden()
            else:
                assert page.locator('#grant-cut').is_enabled()
                assert 'NaN' not in page.locator('#results').inner_text()
        assert len(missing) == 1, missing
        page.goto(base + '/council-stress.html?council=Albury', wait_until='networkidle')
        assert page.locator('#council').input_value() == 'Albury'
        page.goto(base + '/council-stress.html?council=%3Cscript%3E', wait_until='networkidle')
        assert page.locator('#council').input_value() == 'Kiama'

        for width in (320, 390, 768):
            page.set_viewport_size({'width': width, 'height': 900})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            for selector in ['#council', '#scenario-form', '#results', '#scenario-chart']:
                box = page.locator(selector).bounding_box()
                assert box['x'] >= 0 and box['x'] + box['width'] <= width + 1, (width, selector, box)
            if width == 390:
                page.screenshot(path='/tmp/council-stress-mobile.png', full_page=True)
        page.locator('.theme-toggle').click()
        assert page.locator('html').get_attribute('data-theme') == 'dark'
        page.reload(wait_until='networkidle')
        assert page.locator('html').get_attribute('data-theme') == 'dark'
        assert page.locator('#results').is_visible()
        page.screenshot(path='/tmp/council-stress-dark.png', full_page=True)
        page.goto(base + '/index.html', wait_until='networkidle')
        page.locator('a.tool[href="council-stress.html"]').click()
        page.locator('#results').wait_for(state='visible')
        assert page.locator('#results').is_visible()
        assert not errors, errors
        assert not failed_local, failed_local

        # Missing payload must display a useful error and keep the tool disabled.
        page.route('**/data/council_stress.js', lambda route: route.abort())
        page.reload(wait_until='networkidle')
        assert page.locator('#load-error').is_visible()
        assert page.locator('#tool').is_hidden()
        assert page.locator('#council').is_disabled()
        assert not errors, errors
        print(f'PASS: {len(names)} councils, {len(missing)} unavailable-data state, scenario controls, CSV export, deep links, 3 viewport widths, dark theme, homepage navigation and missing-payload fallback; no JavaScript errors.')
        browser.close()
finally:
    server.shutdown()
    server.server_close()
