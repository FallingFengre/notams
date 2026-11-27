"""Browser regressions using local fixtures (requires Playwright Chromium)."""
import threading

import pytest
from flask import Flask, jsonify, send_from_directory
from pathlib import Path
from werkzeug.serving import make_server

pw = pytest.importorskip('playwright.sync_api')
WEB = Path(__file__).resolve().parents[1] / 'web'
RAW = 'A6096/26 NOTAMN\nQ)ZLHW/QRTCA/IV/BO/W/000/999/4115N10034E055\nA)ZLHW\n' + (
    'E) TEST LINE <sample> & coordinates\n' * 24) + 'F)SFC G)UNL\nCREATED: 20 NOV 2026 03:03\nSOURCE: ZBBBYNYX'
RING = [[35, 102], [35, 104], [37, 104], [37, 102]]


@pytest.fixture(scope='module')
def local_map():
    site = Flask(__name__)
    site.add_url_rule('/', view_func=lambda: send_from_directory(WEB / 'templates', 'index.html'))
    site.add_url_rule('/scripts/<path:f>', 'scripts', lambda f: send_from_directory(WEB / 'scripts', f))
    site.add_url_rule('/statics/<path:f>', 'statics', lambda f: send_from_directory(WEB / 'static', f))
    site.add_url_rule('/fetch', 'fetch', lambda: jsonify({
        'NUM': 1, 'CODE': ['A6096/26'], 'CLASSIFY': {}, 'TIME': [''], 'ALTITUDE': ['UNL'],
        'COORDINATES': [''], 'GEOMETRY': [{'type': 'polygon', 'points': RING}], 'RAWMESSAGE': [RAW]
    }))
    server = make_server('127.0.0.1', 0, site, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        thread.join()


@pytest.mark.parametrize('touch', [False, True], ids=['desktop', 'portrait-touch'])
def test_map_tools_and_copies(local_map, touch):
    with pw.sync_playwright() as runtime:
        if not Path(runtime.chromium.executable_path).exists():
            pytest.skip('Chromium is not installed')
        browser = runtime.chromium.launch(executable_path=runtime.chromium.executable_path)
        context = browser.new_context(viewport={'width': 390 if touch else 1280, 'height': 820},
                                      has_touch=touch, is_mobile=touch, permissions=['clipboard-read', 'clipboard-write'])
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.route('**/*', lambda r: r.continue_() if r.request.url.startswith(local_map) else r.abort())
        page.goto(local_map)
        page.wait_for_function('typeof polygonAuto !== "undefined" && polygonAuto[0]')
        button = lambda name: page.get_by_role('button', name=name, exact=True)
        def click_geo(lat, lng, offset=0):
            x, y = page.evaluate('p => {const v = map.latLngToContainerPoint(p); return [v.x, v.y]}', [lat, lng])
            (page.touchscreen.tap if touch else page.mouse.click)(x + offset, y)

        page.evaluate('map.setView([36, 823], 6, {animate:false})')
        click_geo(36, 823)
        popup = page.locator('.notam-popup')
        assert popup.get_by_text('ZLHW', exact=True).is_visible()
        assert popup.bounding_box()['width'] == 240
        button('固定弹窗').click()
        button('查看原始航警').click()
        original = popup.locator('pre')
        assert original.inner_text() == RAW
        assert original.evaluate('e => e.scrollHeight > e.clientHeight')
        assert not popup.get_by_text('飞航情报区', exact=True).is_visible()
        popup.get_by_role('button', name='复制原始航警').click()
        assert page.evaluate('navigator.clipboard.readText()').replace('\r\n', '\n') == RAW
        page.mouse.click(105, 570)
        assert original.is_visible()
        button('返回').click()
        button('取消固定').click()
        page.mouse.click(105, 570)
        popup.wait_for(state='detached', timeout=2000)

        button('显示经纬度').click()
        button('测距').click()
        page.evaluate('map.setView([36, -617], 6, {animate:false})')
        assert page.locator('.measure-target, .measure-point, .leaflet-snap-guides-pane').count() == 0
        click_geo(35, -618, 5)
        if not touch:
            pos = page.evaluate('() => map.latLngToContainerPoint([36,-617])')
            page.mouse.move(pos['x'] + 5, pos['y'])
            page.wait_for_selector('.measure-preview-line', state='attached')
            assert page.locator('.measure-target').count() == 1
            assert page.locator('.measure-preview-line').first.get_attribute('stroke-dasharray')
        click_geo(36, -617, 5)
        popup.wait_for(state='detached', timeout=2000)
        rows = page.locator('.measure-segment-row')
        assert rows.count() == 1
        assert page.locator('.measure-preview-line').count() == 0
        center = page.evaluate('polygonAuto[0].getCenter()')
        expected = page.evaluate('p => geodesic.Geodesic.WGS84.Inverse(35,102,p.lat,p.lng).s12 / 1000', center)
        assert abs(float(rows.first.inner_text().split()[-2]) - expected) < .006
        assert rows.first.inner_text() == page.locator('.measure-label span').first.inner_text()
        label = page.locator('.measure-label span').first
        assert label.evaluate('''el => {
            const pane = map.getPane('measureLabels');
            return pane.contains(el) && Number(getComputedStyle(pane).zIndex) >
                Number(getComputedStyle(map.getPane('measurement')).zIndex);
        }''')
        assert label.evaluate('el => getComputedStyle(el).backgroundColor') == 'rgb(255, 255, 255)'
        coords = page.locator('.map-coordinate-tooltip')
        assert 'E' in coords.inner_text() and coords.is_visible()
        box = coords.bounding_box()
        if touch:
            assert 460 < box['y'] < 720
        else:
            assert abs(box['x'] - pos['x']) < 35 and abs(box['y'] - pos['y']) < 30
        click_geo(37, -616, 5)
        assert rows.count() == 2
        assert rows.first.get_attribute('style') != rows.last.get_attribute('style')
        button('撤销上一点').click()
        assert rows.count() == 1
        page.keyboard.press('Escape')
        resume = button('继续测量')
        assert resume.is_visible()
        before = rows.all_text_contents()
        count = page.locator('.measure-point').count()
        click_geo(33, -618)
        assert rows.all_text_contents() == before and page.locator('.measure-point').count() == count
        pos = page.evaluate('map.latLngToContainerPoint([35,-618])')
        x, y = pos['x'], pos['y']
        destination = page.evaluate('map.latLngToContainerPoint([37,-618])')
        dx, dy = destination['x'] + 5, destination['y']
        if touch:
            cdp = context.new_cdp_session(page)
            center_before = page.evaluate('map.getCenter()')
            def finger(kind, px=None, py=None):
                pts = [] if px is None else [{'x': px, 'y': py, 'id': 1}]
                cdp.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': pts})
            finger('touchStart', x, y)
            finger('touchMove', dx, dy)
            assert page.locator('.measure-point.editing').count() > 0
            finger('touchEnd')
            assert page.locator('.measure-point.editing').count() == 0
            assert center_before == page.evaluate('map.getCenter()')
            assert page.evaluate('map.dragging.enabled() && map.touchZoom.enabled()')
            moved = page.locator('.measure-point').evaluate_all('els => els.map(e => e.getBoundingClientRect().toJSON())')
            assert any(abs(r['x'] + r['width'] / 2 - (dx - 5)) < 2 and
                       abs(r['y'] + r['height'] / 2 - dy) < 2 for r in moved)
        else:
            page.mouse.click(x, y)
            page.mouse.move(dx, dy)
            assert page.locator('.measure-point.editing').count() == 0
            assert rows.all_text_contents() == before
            center_before = page.evaluate('map.getCenter()')
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(dx, dy, steps=4)
            page.wait_for_function("document.querySelector('.measure-segment-row span').textContent !== "
                                   + repr(before[0]))
            page.keyboard.press('Escape')
            page.mouse.up()
            assert rows.all_text_contents() == before
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(dx, dy, steps=4)
            page.mouse.up()
            assert rows.all_text_contents() != before
            assert page.locator('.measure-point.editing').count() == 0
            assert center_before == page.evaluate('map.getCenter()')
            assert page.evaluate('map.dragging.enabled()')
            moved = page.locator('.measure-point').evaluate_all('els => els.map(e => e.getBoundingClientRect().toJSON())')
            assert any(abs(r['x'] + r['width'] / 2 - (dx - 5)) < 2 and
                       abs(r['y'] + r['height'] / 2 - dy) < 2 for r in moved)
        assert resume.is_visible()
        resume.click()
        assert page.locator('#allmap').evaluate("e => e.classList.contains('measure-picking')")
        for lat in [34, 35, 36, 37]:
            click_geo(lat, -615)
        page.keyboard.press('Escape')
        assert rows.count() == 4
        lengths = [text.split('·')[-1] for text in rows.all_text_contents()]
        button('删除第 3 段').click()
        assert [text.split('·')[-1] for text in rows.all_text_contents()] == lengths[:2] + lengths[3:]
        button('显示经纬网').click()
        canvas = page.locator('.leaflet-graticule-pane canvas')
        assert canvas.evaluate('c => c.getContext("2d").getImageData(0,0,c.width,c.height).data.some(x=>x)')
        button('显示经纬网').click()
        assert canvas.count() == 0
        button('清除测距').click()
        button('测距').click()
        click_geo(36, -617)
        button('关闭弹窗').click()
        popup.wait_for(state='detached', timeout=2000)
        # Open an archive polygon straddling the date line from a different world.
        page.evaluate('''() => {
            map.setView([0, 540], 6, {animate:false});
            drawArchiveNotam('', '', 'TEST/26', 0, '#934', 'Q)EGTT/QRTCA', {
                type:'polygon', points:[[-1,179],[-1,-179],[1,-179],[1,179]]
            });
        }''')
        click_geo(0, 540)
        assert popup.get_by_text('历史NOTAM信息').is_visible()
        button('固定弹窗').click()
        click_geo(2, 540)
        assert popup.get_by_text('EGTT', exact=True).is_visible()
        page.evaluate('clearArchiveNotams()')
        popup.wait_for(state='detached')

        # Marker popups remain clickable where a repeated world is visible.
        lat, lng = page.evaluate('''() => {
            const p = landingZoneMarkers[0].getLatLng();
            map.setView([p.lat, p.lng + 1080], 8, {animate:false});
            return [p.lat, p.lng + 1080];
        }''')
        click_geo(lat, lng)
        assert page.locator('.launch-site-popup').is_visible()
        route = page.evaluate('''() => {
            const seg = measureGeodesic(L.latLng(60,150), L.latLng(60,-150));
            return [seg.meters, seg.anchor.lat, seg.parts[0].map(p => p.lng)];
        }''')
        assert route[0] == pytest.approx(3231376.13, abs=1)
        assert route[1] > 63 and len(route[2]) > 3
        assert route[2][0] == 150 and abs(route[2][-1] - 210) < 1e-8
        assert not errors
        browser.close()
