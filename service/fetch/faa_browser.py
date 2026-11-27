"""
FAA NOTAM 浏览器会话管理器。

背景：FAA 网站 (notams.aim.faa.gov) 启用了 Akamai Bot Manager。普通无头
Chrome（含 stealth 补丁、Patchright）都会被拦截，只有真实浏览器能过。

方案（Camoufox）：
  1. Camoufox 是基于 Firefox 的反检测浏览器，headless=True 时既无窗口、
     又能通过 Akamai challenge（已实测）；
  2. 查询用 page.evaluate() 在浏览器 JS 中 fetch（真实网络栈+TLS指纹）；
  3. 批量查询用 Promise.all() 在浏览器内部并行，避免 Playwright greenlet
     跨线程问题；
  4. 无头模式跨平台（Windows/macOS/Linux），无需 Xvfb / AppleScript / 移窗。

依赖：
    pip install camoufox
    python -m camoufox fetch   # 首次下载 Firefox 内核（约 300MB）
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

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


class FaaBrowserSession:
    """FAA NOTAM 浏览器会话。

    所有 Playwright 操作由同一个工作线程执行。
    批量查询在浏览器 JS 层面并行（Promise.all），不跨 greenlet 边界。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._executor = None
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None       # 主 page，用于单个/批量查询
        self._initialized = False

    def _submit(self, operation, *args):
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='faa-browser')
            return self._executor.submit(operation, *args)

    def warm_up(self):
        """在后台打开查询页，随后由同一工作线程处理查询。"""
        self._submit(self._warm_up)

    def _warm_up(self):
        try:
            self._ensure_ready()
        except Exception as exc:
            print(f'[FAA] 后台初始化失败，历史查询时将重试：{exc}')

    # ========== 初始化 ==========

    def _launch(self):
        """启动 Camoufox 无头浏览器，完成 Akamai challenge。必须在同一线程调用。"""
        launch_started = time.perf_counter()
        self._close_unsafe()

        from playwright.sync_api import sync_playwright
        from camoufox.utils import launch_options

        self._pw = sync_playwright().start()

        # Camoufox：无窗口 + 反检测指纹，能过 Akamai
        try:
            opts = launch_options(headless=True)
            self._browser = self._pw.firefox.launch(**opts)
            print('[FAA] 已启动 Camoufox 无头浏览器')
        except Exception as e:
            self._close_unsafe()
            raise RuntimeError(
                f'无法启动 Camoufox: {e}\n'
                '请先执行: pip install camoufox  然后  python -m camoufox fetch。')

        try:
            context = self._browser.new_context()
            page = context.new_page()

            page.goto(NSAPP_URL, timeout=60000, wait_until='domcontentloaded')
            self._wait_for_page_idle(page)
            content = page.content()
            if 'Access Denied' in content:
                raise RuntimeError('页面仍被 Akamai 拒绝，可能需要更换网络出口')

            print(f'[FAA] 查询页就绪，浏览器启动耗时 {time.perf_counter() - launch_started:.1f}s')

        except Exception:
            self._close_unsafe()
            raise

        self._context = context
        self._page = page
        self._initialized = True

    # ========== 查询 ==========

    def _do_single(self, payload):
        """在浏览器工作线程上执行单次查询。"""
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
        # 并行批大小。全文搜索（searchType=4，如 AEROSPACE/ROCKET LAUNCH）
        # 服务端单次约 5s，是主要耗时；实测 14 个并行无 403，故一次并行全部。
        batch_size = 15
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
            self._wait_for_page_idle(self._page)
            if 'Access Denied' in self._page.content():
                print('[FAA] challenge 仍然失败，完整重启...')
                self._restart()
            else:
                print('[FAA] challenge 重新通过')
        except Exception:
            self._restart()

    @staticmethod
    def _wait_for_page_idle(page):
        """等页面自行进入 network-idle，超过配置时限后交由真实查询验证会话。"""
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        try:
            page.wait_for_load_state(
                'networkidle',
                timeout=max(1, config.PW_PAGE_WAIT * 1000),
            )
        except PlaywrightTimeoutError:
            # 部分页面持续发送后台请求。真正的 FAA 查询会继续验证 challenge 状态。
            pass

    def _is_network_error(self, msg):
        msg_lower = msg.lower()
        return any(kw in msg_lower for kw in [
            'connection', 'timeout', 'protocol', 'network',
            'target closed', 'browser has been closed', 'websocket',
            'eof', 'reset', 'refused', 'tunneling',
            'page crashed', 'target crashed', 'ns_error',
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
            if self._executor is not None:
                self._executor.submit(self._close_unsafe)
                self._executor.shutdown(wait=True)
                self._executor = None

    # ========== 公开接口 ==========

    def search(self, payload):
        """单次 FAA search API 调用。"""
        data = self._submit(self._search, payload).result()
        time.sleep(0.1)  # 轻微降频
        return data

    def _search(self, payload):
        self._ensure_ready()
        return self._do_single(payload)

    def batch_search(self, queries):
        """批量 FAA search API 调用。

        queries: {label: payload} dict
        返回: {label: data} dict（data 为 JSON dict，失败的为 None）

        浏览器 JS 中用 Promise.all() 并行所有 fetch，速度快且不跨 greenlet。
        """
        return self._submit(self._batch_search, queries).result()

    def _batch_search(self, queries):
        self._ensure_ready()
        return self._do_batch(queries)

    def search_with_pagination(self, payload, max_pages=100):
        """带分页的查询，返回聚合结果列表。

        适配现有 fetch_one 的分页逻辑：每页 30 条，持续到 num < 30。
        返回与原来兼容的 JSON data dict（含 notamList）。
        """
        return self._submit(self._search_with_pagination, payload, max_pages).result()

    def _search_with_pagination(self, payload, max_pages):
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
