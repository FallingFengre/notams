# 版本更新记录 (CHANGELOG)

本项目重要版本变更均在此记录，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

---

## [v1.9.1] - 2026-11-27

### 新增与完善
- 补充项目根目录下开源许可证文件 `LICENSE`（MIT License），明确主创团队与贡献者版权声明及第三方 Leaflet 许可归属（PR `#19`）
- 新增完全离线的核心单元测试套件 `tests/test_core.py`（5 项用例，覆盖 `NotamParser` 解析与拦截、自交多边形修复、跨 180° 日界线重叠判断、点位/高度解析、跨源时空去重与并查集聚类）（PR `#23`）
- 补全开源协作文档体系：`docs/INSTALL.md`（安装运行与离线测试说明）、`docs/ISSUES_SUMMARY.md`（历史问题处理记录）、`CONTRIBUTING.md`（贡献指南与合规准则）（PR `#24`）
- 新增系统四层总体架构图 `docs/architecture.png`，并重构 `README.md` 内容结构，修正过时描述（PR `#24`）

### 缺陷修复与兼容性改进
- **修复 `NotamParser.parse()` 缺陷与 Python 3.10/3.11 兼容**（PR `#20`）：修复 `service/notam.py` 中 `!` 非 ICAO 通告校验误引用全局示例变量 `raw` 而非 `self.raw` 的问题，并移除仅 Python 3.12+ 支持的 f-string 嵌套引号语法
- **跨平台运行时与图像导出回退修复**（PR `#21`）：在 `main.py` 改为按需延迟导入 `pywebview` 并支持缺省自动回退浏览器模式；将 `service/server.py` 前端静态路径改为基于 `__file__` 解析；为 macOS/Linux 无原生弹窗环境增加 `/save_image` `fallback_download` 自动触发前端浏览器下载
- **配置与脚本规范化**（PR `#22` & `#19`）：更新 `config.ini`、`config.py` 与 `run.sh` 注释及安装提示以匹配当前 Camoufox 无头架构，并补充 `.gitignore` 忽略规则

---

## [维护迭代] - 2026-04 ~ 2026-08（主干演进）

> 对应 `v1.9` 发布后在 `main` 分支推进的稳定性修复与采集架构重构（提交 `965617b` ~ `7350dc6`）。

### 性能优化与架构重构
- **Camoufox 无头浏览器会话方案**（`7350dc6`）：以基于 Firefox 的 Camoufox 无头浏览器替换早期有窗口浏览器实现，配合页面 JS `Promise.all()` 批量并行检索（`batch_size=15`），完整抓取耗时从 `27.2s` 降至 `21.4s`，全文检索批处理耗时从 `18.6s` 降至 `6.0s`；精简约 90 行平台差异代码，实现 Windows / macOS / Linux 统一无头运行
- **适配 FAA FNS 站点接口变更**（`ce2e64d`）：新增 `service/fetch/faa_browser.py` 与连通性自测脚本 `service/fetch/self_test.py`，重构 `FNS_NOTAM_SEARCH.py` 与 `FNS_NOTAM_ARCHIVE_SEARCH.py`，解决数据源增强管理改造后的抓取兼容问题

### 缺陷修复
- **关键词笔误容错**（`04783e7`）：针对上游 NOTAM 原文中出现 `AER0SPACE`（数字 0 替代字母 O）的拼写差异新增检索与匹配兼容
- **实时与历史航警抓取修复**（`965617b`, `e81a3f2`）：修复 2026 年 4 月上游接口参数调整导致的实时与历史归档航警抓取失败问题

---

## [v1.9] - 2025-12-22

> Release: `notamsChecker v1.9`

### 新增功能
- 依据 NOTAM 生效时间进行时序并查集分类，并以不同颜色区分多组发射窗口（`@Joey0609`）
- 增加对历史航警的检索爬取与落区绘制功能（`@FallingFengre`）
- 增加对航警生效高度范围（`F)` / `G)` 及 `Q)` 项）的解析与米制换算展示（`@festoney8`）
- 增加回收/着陆场图标显示与图标资源优化（`@FallingFengre`）
- 增加地图图像导出功能（支持当前视图、全落区、自定义裁剪区域及 x1–x4 分辨率，重构 `leaflet-image.js` 支持高 DPI 与 SVG 矢量路径导出）（`@Joey0609`, `@FallingFengre`）
- 增加海事局（MSA）与 NGA（MSI）海警获取及与航空 NOTAM 的时空重叠自动去重

### 重构与优化
- 分离前后端目录结构为 `service/` 与 `web/`，拆分 `config.py` 配置加载与 `server.py` 接口服务（`@festoney8`）
- 初步建立独立 `NotamParser` 结构化解析器与 Shapely 跨日界线重叠检测引擎（`service/notam.py`）（`@festoney8`）
- 将手动绘制页与自动获取页整合入统一侧边栏，优化界面布局与航警列表筛选（`@Joey0609`, `@FallingFengre`）

---

## [v1.8] - 2025-11-21

> Release: `notamsChecker v1.8`

- **地图引擎全面开源化迁移**：从受免费配额限制的商业地图 SDK 迁移至开源 **Leaflet v1.9.4**，结合高德地图/天地图公开瓦片源实现零配额限制的矢量/卫星图层绘制
- 引入 `pywebview` 独立桌面窗口模式与占位加载页，隐藏终端窗口简化使用体验
- 优化航警信息弹窗与帮助页样式，完善依赖清单与源码运行说明（`@NearlyHeadlessJack`）

---

## [v1.7] - 2025-10-14

> Release: `notamsChecker v1.7`

- 将航警主数据源从下线的 `dinsQueryWeb` 迁移至 FAA `FNS NOTAM Search`
- 引入本地 JSON 缓存机制（10 分钟有效期）避免短时间高频重复请求
- 增加加载状态弹窗与失败重试机制（`@Joey0609`）

---

## [v1.6] - 2025-08-17

> Release: `notamsChecker v1.6`

- 增加手动绘制模块对海事航行警告坐标格式的支持
- 优化坐标组提取逻辑，避免同一报文多落区或零散坐标导致的错误连线
- 新增 `config.ini` 支持用户自定义 FIR / ICAO 代码列表
- 新增前端“自动获取落区列表”侧边栏视图

---

## [v1.5] - 2025-03-20

> Release: `notamsChecker v1.5`

- 支持南半球（`S`）与西半球（`W`）经纬度坐标提取与绘制
- 兼容 `N(S)/E(W)` 前置或后置及多分隔符的复杂坐标文本解析
- 落区信息弹窗新增“复制坐标”快捷按钮，手动绘制弹窗支持显示序号标识

---

## [v1.4.1] - 2025-01-20

> Release: `notamsChecker v1.4.1`

- 修复形如 `XXXXNXXXXXE`（4 位纬度 + 5 位经度）短精度坐标格式解析错误的问题

---

## [v1.4] - 2025-01-18

> Release: `notamsChecker v1.4`

- 修复部分航警时间字段解析结果显示为 `NaN` 的问题（Issue `#1`）
- 新增未获取到有效航警时的前端友好提示
- 新增海阳东方航天港图标标注与 `YMMM`、`WIIF`、`RJJJ` 飞行情报区代码
