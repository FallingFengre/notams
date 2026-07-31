"""
FAA NOTAM 浏览器会话管理器。

背景：FAA 网站 (notams.aim.faa.gov) 启用了 Akamai Bot Manager。只有有窗口的
真实 Chrome 能通过 JS challenge。同一浏览器 context 下多个 page/tab 共享 cookie。

方案：
  1. 启动有窗口 Chrome（最小化），完成一次 Akamai challenge；
  2. 查询用 page.evaluate() 在浏览器 JS 中 fetch（真实网络栈+TLS指纹）；
  3. 批量查询用 Promise.all() 在浏览器内部并行，避免 Playwright greenlet 跨线程问题；

关于 xvfb：无图形环境的 Linux 服务器可先启动 Xvfb 虚拟显示：
    Xvfb :99 -screen 0 1920x1080x24 &
    export DISPLAY=:99
然后正常运行。macOS 不需要 Xvfb，应用启动后自动最小化窗口。
"""

import os
import sys
import threading
import time

import config

NSAPP_URL = 'https://notams.aim.faa.gov/notamSearch/'

# 页面内 fetch 脚本：单次查询
FETCH_JS = r"""
async (payload) => {
    const body = new URLSearchParams();
    for (const [k, v] of Object.entries(payload)) {
        body.append(k, v);
    }
    const r = await fetch('/notamSearch/search', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
        body: body.toString()
    });
    if (r.status === 200) return {status: r.status, data: await r.json()};
    return {status: r.status, data: null};
}
"""

# 页面内批量 fetch 脚本：多个查询在浏览器 JS 中并行执行
BATCH_FETCH_JS = r"""
async (queries) => {
    const results = {};
    const promises = [];
    for (const [key, payload] of Object.entries(queries)) {
        promises.push((async (k, p) => {
            const body = new URLSearchParams();
            for (const [kv, v] of Object.entries(p)) {
                body.append(kv, v);
            }
            const r = await fetch('/notamSearch/search', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
                body: body.toString()
            });
            if (r.status === 200) {
                results[k] = {status: 200, data: await r.json()};
            } else {
                results[k] = {status: r.status, data: null};
            }
        })(key, payload));
    }
    await Promise.all(promises);
    return results;
}
"""


def _candidate_channels():
    cfg = getattr(config, 'PW_CHANNEL', 'auto')
    if cfg and cfg != 'auto':
        return [cfg]
    if sys.platform == 'darwin':
        candidates = []
        if os.path.exists('/Applications/Google Chrome.app'):
            candidates.append('chrome')
        if os.path.exists('/Applications/Microsoft Edge.app'):
            candidates.append('msedge')
        if os.path.exists('/Applications/Chromium.app'):
            candidates.append('chromium')
        return candidates or ['chrome']
    if sys.platform.startswith('win'):
        return ['chrome', 'msedge']
    return ['chrome', 'msedge', 'chromium']


class FaaBrowserSession:
    """FAA NOTAM 浏览器会话。

    所有 Playwright 操作在同一个线程（创建线程）中执行，通过线程锁保证。
    批量查询在浏览器 JS 层面并行（Promise.all），不跨 greenlet 边界。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None       # 主 page，用于单个/批量查询
        self._challenge_page = None  # 专门保持 challenge 连接的 page
        self._initialized = False
        self._owner_thread = None

    # ========== 初始化 ==========

    def _launch(self):
        """启动浏览器，完成 Akamai challenge。必须在同一线程调用。"""
        self._close_unsafe()

        if not os.environ.get('DISPLAY'):
            if sys.platform == 'darwin':
                os.environ['DISPLAY'] = ':0'
            elif sys.platform.startswith('linux'):
                raise RuntimeError(
                    '无可用的图形显示。请先启动 Xvfb:\n'
                    '  Xvfb :99 -screen 0 1920x1080x24 &\n'
                    '  export DISPLAY=:99\n然后重新运行。')

        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        args = [
            '--disable-blink-features=AutomationControlled',
            '--no-first-run',
            '--disable-default-apps',
            '--disable-extensions',
            '--disable-background-networking',
            '--disable-sync',
        ]

        # Windows/Linux: 窗口移到屏幕外隐藏
        if sys.platform != 'darwin':
            args.append(f'--window-position={config.PW_WINDOW_X},{config.PW_WINDOW_Y}')

        browser = None
        last_err = None
        for ch in _candidate_channels():
            try:
                browser = self._pw.chromium.launch(channel=ch, headless=False, args=args)
                print(f'[FAA] 浏览器已启动 (channel={ch})')
                break
            except Exception as e:
                last_err = e
                continue

        if browser is None:
            try:
                browser = self._pw.chromium.launch(headless=False, args=args)
                print('[FAA] 已启动 playwright bundled Chromium')
            except Exception as e:
                raise RuntimeError(
                    f'无法启动浏览器: {last_err} / {e}\n'
                    '请安装 Chrome/Edge，或执行 `playwright install chromium`。')

        try:
            context = browser.new_context(
                locale='en-US',
                timezone_id='America/New_York',
                viewport={'width': 1400, 'height': 900},
            )
            page = context.new_page()

            page.goto(NSAPP_URL, timeout=60000, wait_until='domcontentloaded')
            page.wait_for_timeout(config.PW_PAGE_WAIT * 1000)
            content = page.content()
            if 'Access Denied' in content:
                browser.close()
                raise RuntimeError('页面仍被 Akamai 拒绝，可能需要更换网络出口')

            print('[FAA] Akamai challenge 通过，会话已就绪')

        except Exception:
            browser.close()
            raise

        self._browser = browser
        self._context = context
        self._page = page
        self._initialized = True
        self._owner_thread = threading.current_thread()

        # macOS: 用 AppleScript 最小化 Chrome 窗口（Xvfb 不适用 macOS）
        if sys.platform == 'darwin':
            import subprocess
            try:
                subprocess.run(
                    ['osascript', '-e',
                     'tell application "System Events" to set visible of process "Google Chrome" to false'],
                    capture_output=True, timeout=5)
            except Exception:
                pass

    # ========== 查询 ==========

    def _do_single(self, payload):
        """执行单次查询（必须在持有 lock 的 owner thread 中调用）。"""
        for attempt in range(1, config.PW_MAX_RETRIES + 1):
            try:
                result = self._page.evaluate(FETCH_JS, payload)
                if result is None:
                    raise Exception('page.evaluate 返回 None')

                if result.get('status') == 200:
                    return result['data']

                if result.get('status') == 403:
                    print(f'[FAA] 403 (第{attempt}次)，重新过 challenge...')
                    self._rechallenge()
                    continue

                raise RuntimeError(f'FAA 服务端错误 status={result.get("status")}')

            except RuntimeError:
                raise
            except Exception as e:
                if self._is_network_error(str(e)):
                    if attempt < config.PW_MAX_RETRIES:
                        print(f'[FAA] 网络异常 (第{attempt}次)，重启重试...')
                        self._restart()
                        continue
                if attempt >= config.PW_MAX_RETRIES:
                    raise RuntimeError(
                        f'FAA 请求在 {config.PW_MAX_RETRIES} 次尝试后仍失败: {e}')
                continue

        raise RuntimeError('FAA 请求失败')

    def _do_batch(self, queries):
        """执行批量查询。queries = {key: payload}。

        浏览器 JS 中用 Promise.all() 并行所有 fetch。
        必须在同一线程调用。
        """
        # 分批（每批最多 6 个并行，避免浏览器限流）
        batch_size = 6
        keys = list(queries.keys())
        all_results = {}

        for batch_start in range(0, len(keys), batch_size):
            batch_keys = keys[batch_start:batch_start + batch_size]
            batch = {k: queries[k] for k in batch_keys}

            for attempt in range(1, config.PW_MAX_RETRIES + 1):
                try:
                    results = self._page.evaluate(BATCH_FETCH_JS, batch)
                    if results is None:
                        raise Exception('batch evaluate 返回 None')

                    batch_ok = True
                    for k in batch_keys:
                        r = results.get(k)
                        if r and r.get('status') == 200:
                            all_results[k] = r['data']
                        elif r and r.get('status') == 403:
                            batch_ok = False
                            break
                        else:
                            # 单个失败
                            all_results[k] = None

                    if batch_ok:
                        break

                    print(f'[FAA] 批量请求 403 (第{attempt}次)，重新过 challenge...')
                    self._rechallenge()
                    continue

                except Exception as e:
                    if self._is_network_error(str(e)):
                        if attempt < config.PW_MAX_RETRIES:
                            print(f'[FAA] 批量网络异常 (第{attempt}次)，重启重试...')
                            self._restart()
                            continue
                    if attempt >= config.PW_MAX_RETRIES:
                        raise RuntimeError(f'批量请求在 {config.PW_MAX_RETRIES} 次尝试后仍失败: {e}')
                    continue

        return all_results

    # ========== 内部辅助 ==========

    def _ensure_ready(self):
        """确保浏览器就绪。"""
        if not self._initialized or self._browser is None or not self._browser.is_connected():
            self._restart()
            return
        try:
            content = self._page.content()
            if 'Access Denied' in content:
                print('[FAA] 会话过期，重新 challenge...')
                self._rechallenge()
        except Exception:
            self._restart()

    def _restart(self):
        """重启浏览器。"""
        print('[FAA] 重启浏览器会话...')
        self._launch()

    def _rechallenge(self):
        """重新过 Akamai challenge。"""
        try:
            self._page.goto(NSAPP_URL, timeout=60000, wait_until='domcontentloaded')
            self._page.wait_for_timeout(config.PW_PAGE_WAIT * 1000)
            if 'Access Denied' in self._page.content():
                print('[FAA] challenge 仍然失败，完整重启...')
                self._restart()
            else:
                print('[FAA] challenge 重新通过')
        except Exception:
            self._restart()

    def _is_network_error(self, msg):
        msg_lower = msg.lower()
        return any(kw in msg_lower for kw in [
            'connection', 'timeout', 'protocol', 'network',
            'target closed', 'browser has been closed', 'websocket',
            'eof', 'reset', 'refused', 'tunneling',
            'page crashed', 'target crashed',
        ])

    def _close_unsafe(self):
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._browser = self._context = self._page = self._pw = None
        self._initialized = False

    def close(self):
        with self._lock:
            self._close_unsafe()

    # ========== 公开接口 ==========

    def search(self, payload):
        """单次 FAA search API 调用。线程安全（排队等锁）。"""
        with self._lock:
            self._ensure_ready()
            data = self._do_single(payload)
        time.sleep(0.1)  # 轻微降频
        return data

    def batch_search(self, queries):
        """批量 FAA search API 调用。

        queries: {label: payload} dict
        返回: {label: data} dict（data 为 JSON dict，失败的为 None）

        浏览器 JS 中用 Promise.all() 并行所有 fetch，速度快且不跨 greenlet。
        """
        with self._lock:
            self._ensure_ready()
            results = self._do_batch(queries)
        return results

    def search_with_pagination(self, payload, max_pages=100):
        """带分页的查询，返回聚合结果列表。

        适配现有 fetch_one 的分页逻辑：每页 30 条，持续到 num < 30。
        返回与原来兼容的 JSON data dict（含 notamList）。
        """
        with self._lock:
            self._ensure_ready()
            all_notams = []
            num = 30
            page = 0
            while num == 30 and page < max_pages:
                p = dict(payload)
                p['offset'] = str(page * 30)
                data = self._do_single(p)
                notams = data.get('notamList', [])
                num = len(notams)
                all_notams.extend(notams)
                page += 1
            return {'notamList': all_notams}


# ---------- 全局单例 ----------

_session = None
_session_lock = threading.Lock()


def get_session():
    """获取全局单例会话。"""
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = FaaBrowserSession()
    return _session


def reset_session():
    """关闭并重置全局会话。"""
    global _session
    with _session_lock:
        if _session is not None:
            _session.close()
            _session = None
