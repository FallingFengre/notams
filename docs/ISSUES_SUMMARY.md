# 问题处理与维护记录 (Issues & Fixes Summary)

本文档汇总 `notams` 项目在 GitHub Issues 及版本维护过程中遇到的典型问题、社区反馈处理与技术闭环记录，方便开发者和评审查阅。

---

## 1. 社区 Issue 跟踪与处理台账

| Issue 编号 | 提出时间 | 提出者 | 状态 | 问题/建议摘要 | 处理方式与关联提交/说明 |
|---|---|---|---|---|---|
| [#1](https://github.com/FallingFengre/notams/issues/1) | 2025-01-14 | `@Joey0609` | 已关闭 | 航警时间及弹窗信息全部显示为 `NaN` | 修复日期字符串解析与空值兼容逻辑，已于 `v1.4` 版本发布修复 |
| [#12](https://github.com/FallingFengre/notams/issues/12) | 2025-12-09 | `@festoney8` | 已关闭 | 单击发射场与着陆场图标后信息弹窗立即消失 | 排查并修复 Leaflet 标记点击事件冒泡问题，已于提交 `833c29a`（`v1.9`）修复 |
| [#14](https://github.com/FallingFengre/notams/issues/14) | 2025-12-16 | `@winner0zkx` | 开放（已回复） | 询问自动抓取海事航行警告（MSA/MSI）的数据合规性风险 | 主创团队明确界定合规边界：仅解析中国海事局政务公开网公开 HTML 及美国 NGA MSI 公开海事通告，并按航天发射关键词与 `EXCLUDE_RECTS` 严格过滤，与 NOTAM 重叠时自动去重；用户也可在 `config.py` 中关闭 `FETCH_MSA` |
| [#17](https://github.com/FallingFengre/notams/issues/17) | 2026-05-25 | `@xiaoshumiwm` | 已关闭 | 提议将 `notams` 落区解析与外部项目“发射轨迹观测（[CZ-2FLaunchObserve](https://cnb.cool/wmopensource/CZ-2FLaunchObserve)）”结合，实现地面火箭观测星图与型号关联 | 双方完成技术方案交流；仓库维护者明确安全原则——本工具不内置和展示具体火箭型号识别逻辑，仅作为落区公共数据可视化基础设施开放复用 |
| [#18](https://github.com/FallingFengre/notams/issues/18) | 2026-07-06 | `@mackurt18` | 开放（规划中） | 反馈已基于本项目扩展了距离测量与 KML 导出功能，并建议加入自定义海外发射场图标及手动落区历史快照 | 维护者已将其纳入后续架构规划，并欢迎通过 Pull Request 方式回馈合并到主干分支 |

---

## 2. 重大工程缺陷修复记录

### 2.1 上游航警查询网站架构升级导致采集失效（2025-10 & 2026-07）
- **背景与现象**：
  1. 2025 年 10 月，早期使用的 `dinsQueryWeb` 站点停服，导致自动拉取全面失效；
  2. 2026 年 7 月，FAA `FNS NOTAM Search` 站点升级访问防护机制，普通 `requests` 会话触发 `403 Access Denied`。
- **根因分析**：上游门户要求完整浏览器环境与 TLS/JS 会话上下文，传统单线程 HTTP 客户端无法维持有效会话。
- **解决方案**：
  - 2025-10（`v1.7`）：将核心采集迁至 FNS 接口并引入 10 分钟本地缓存；
  - 2026-07（`ce2e64d`）：构建 `service/fetch/faa_browser.py` 会话管理模块与 `self_test.py` 独立连通性自测脚本；
  - 2026-08（`7350dc6`）：进一步重构为 **Camoufox 无头浏览器 + 页面内 `Promise.all` 并发批查询**，消除平台桌面窗口弹窗干扰，同时将完整抓取耗时从 `27.2s` 缩短至 `21.4s`。

### 2.2 非标准航警文本与跨区坐标错连（2025-03 ~ 2026-06）
- **背景与现象**：不同国家和地区的 NOTAM 文本在坐标精度（DMS/DM/D）、半球标识符位置（前置 `N` 与后置 `N` 混用）、分隔符及拼写上存在大量不规范情况（例如 2026 年 6 月 FAA 报文中曾出现 `AER0SPACE` 拼写笔误）。
- **解决方案**：
  - 在 `service/fetch/FNS_NOTAM_SEARCH.py` 中基于字符间距聚类分组坐标（`max_gap=20`），避免多落区错误连线，并增加 `AER0SPACE` 关键词兼容（提交 `04783e7`）；
  - 在 `service/notam.py` 中沉淀通用 `NotamParser` 解析器，结合 `Shapely` 极角重排修复多边形自交并支持跨 180° 国际日界线几何相交计算（PR `#15`）。

### 2.3 商业地图 API 配额受限（2025-11）
- **背景与现象**：随着用户量增长，早期采用的商业地图 JavaScript API 调用量超出个人免费额度，导致用户端地图无法正常加载。
- **解决方案**：于 `v1.8` 版本全面重构前端，替换为开源 **Leaflet v1.9.4** 渲染框架及免费公开的高德/天地图瓦片源，从根本上消除商业配额限制。

### 2.4 跨平台启动兼容、导出回退与 Python 3.10/3.11 语法适配修复（2026-11）
- **背景与现象**：
  1. `service/notam.py` 的 `parse()` 校验非 ICAO 通告时误引用模块全局示例变量 `raw` 而非 `self.raw`，且在报错日志中使用仅 Python 3.12+ 支持的 f-string 嵌套双引号语法（PR `#20`）；
  2. `main.py` 在 `browser_mode = true` 时仍强制顶层导入 `pywebview`，`service/server.py` 依赖相对工作目录路径 `../web/`，且非 Windows 下导出图片触发 `/save_image` 返回 HTTP 400（PR `#21`）。
- **解决方案**：
  - 修复 `self.raw` 校验并提取局部变量保证 Python 3.10–3.12 全版本兼容；
  - 将 `pywebview` 改为桌面模式按需导入并支持缺省自动回退浏览器；将前端资源解析改为基于模块绝对路径；为非 Windows 平台补充 `/save_image` 的 `fallback_download` 前端自动下载机制；
  - 新增 `tests/test_core.py` 5 项离线单元测试并完善开源文档体系（PR `#23`–`#24`）。
