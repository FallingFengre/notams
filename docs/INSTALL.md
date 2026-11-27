# 安装与使用文档

本文档说明 `notams`（航行通告火箭发射落区解析与可视化工具）的本地部署、配置参数、内置离线示例验证方法及跨平台使用注意事项。

---

## 1. 环境要求

- **操作系统**：Windows 10/11、macOS（Apple Silicon / Intel）或 Linux
- **Python 版本**：Python 3.10 及以上（建议 3.10 ~ 3.12）
- **网络环境**：实时抓取在线 NOTAM、海事航警或加载地图底图瓦片时需联网；**离线模式下可使用“手动绘制”功能直接验证坐标解析与几何计算**

---

## 2. 安装步骤

### 方式一：源码运行（推荐，跨平台通用）

1. **克隆或下载仓库**
   ```bash
   # 华中科技大学校内 Git 主仓库
   git clone https://git.hust.edu.cn/U202311386/notams.git
   # 或 GitHub 公开镜像
   # git clone https://github.com/FallingFengre/notams.git
   cd notams
   ```

2. **创建并激活虚拟环境（可选但推荐）**
   ```bash
   python3 -m venv .venv
   # macOS / Linux:
   source .venv/bin/activate
   # Windows PowerShell:
   # .venv\Scripts\Activate.ps1
   ```

3. **安装 Python 依赖**
   ```bash
   pip install -r requirements.txt
   ```
   > 说明：`pywin32` 仅在 Windows 平台安装，macOS / Linux 下会自动跳过。

4. **首次下载 Camoufox 无头浏览器内核**
   ```bash
   python3 -m camoufox fetch
   ```
   > 若仅需使用本地离线解析、手动输入绘制功能（不拉取 FAA 在线接口），可暂不执行该步骤。

### 方式二：Windows 预编译安装包

Windows 用户也可直接从 [GitHub Releases](https://github.com/FallingFengre/notams/releases) 下载已打包版本，解压后运行 `notamChecker.exe`（配置文件位于 `_internal/config.ini`）。

---

## 3. 启动与运行模式

在项目根目录执行：

```bash
python3 main.py
```

`main.py` 启动后台 Flask Web 服务（默认 `http://127.0.0.1:5000`），并根据 `config.ini` 中的 `[SERVER] browser_mode` 自动选择展示方式：

- **浏览器模式（`browser_mode = true`，默认推荐，跨平台稳定）**
  自动调起系统默认浏览器访问 `http://127.0.0.1:5000`，终端按 `Ctrl-C` 退出程序。
- **桌面窗口模式（`browser_mode = false`）**
  通过 `pywebview` 弹出独立桌面窗口展示界面，关闭窗口即自动退出服务。

此外，仓库根目录提供命令行辅助菜单脚本：
```bash
bash run.sh
```

---

## 4. `config.ini` 配置说明

项目通过根目录的 `config.ini`（由 `config.py` 读取）管理运行时参数：

| 配置节 | 参数名 | 默认值 | 说明 |
|---|---|---|---|
| `[ICAO]` | `codes` | `ZBPE ZGZU ZHWH ...` | 需要监控的飞行情报区（FIR）或机场 ICAO 代码，空格分隔 |
| `[SERVER]` | `host` | `127.0.0.1` | Flask 服务监听地址 |
| `[SERVER]` | `port` | `5000` | Flask 服务监听端口 |
| `[SERVER]` | `browser_mode` | `true` | `true` 使用默认浏览器访问；`false` 使用 `pywebview` 桌面窗口 |
| `[WEBVIEW]` | `host` | `127.0.0.1` | 前端访问/桌面窗口连接的主机地址 |
| `[WEBVIEW]` | `port` | `5000` | 前端访问/桌面窗口连接的端口 |
| `[PLAYWRIGHT]` | `page_wait_seconds` | `10` | 无头浏览器打开目标查询页后的初始化等待时间（秒） |
| `[PLAYWRIGHT]` | `max_retries` | `3` | 单次请求失败后的最大重试次数 |
| `[PLAYWRIGHT]` | `channel` / `window_x` / `window_y` | `auto` / `-32000` | 兼容早期版本的保留字段，当前无头模式无需窗口偏移 |

数据源开关（`FETCH_FNS`、`FETCH_MSA`、`FETCH_MSI`、`FETCH_DINS`）与本地缓存过期时间（`FETCH_EXPIRE_TIME = 600` 秒）可在 `config.py` 中调整。

---

## 5. 快速功能验证与离线示例数据

### 5.1 Web 界面功能操作

1. **自动拉取与落区查看**：启动后页面自动调用 `GET /fetch`，按生效时间窗将航警聚类并分色渲染；点击右上角 **“航警列表”** 可展开列表，悬停高亮、点击飞至对应区域并查看完整原始通告与高度限制（米）。
2. **底图切换**：支持高德地图矢量图层、高德卫星影像图层与天地图切换，落区多边形颜色池随底图明暗自动切换以保持对比度。
3. **手动输入 NOTAM 解析绘制（可完全离线验证）**：
   在 **“航警列表 → 手动绘制”** 中粘贴任意以下公开标准格式航警报文并点击 **“绘制”**，即可立即完成坐标提取与地图多边形渲染：

   **示例 1（标准单区域 ICAO NOTAM）**：
   ```text
   A1690/23 - A TEMPORARY DANGER AREA ESTABLISHED BOUNDED BY: N392852E0955438-N385637E0955854-N390118E0970056-N393335E0965708 BACK TO START. VERTICAL LIMITS:SFC-UNL. SFC - UNL, 06 JUL 03:18 2023 UNTIL 06 JUL 04:45 2023. CREATED: 05 JUL 07:40 2023
   ```

   **示例 2（含多组混合精度坐标的跨区域 NOTAM，内置于 `service/notam.py`）**：
   ```text
   B1145/14 NOTAMN
   Q) RPHI/QWMLW/IV/BO /W /000/666/1921N11902E
   A)RPHI XXXX YYYY B) 1412201100 C) 1412221500 EST
   D) DAILY 0100-0430 0600-0900
   E)SPECIAL OPS (AEROSPACE FLT ACT) WILL BE CONDUCTED BY CHINA.
   EST FALL AREA OF UNBURNED DEBRIS WI:
   193600N 1183100E - 193300N1193400E - 19 06 00N 1193300E - 1909N 118 3000E - 19 36N 11831E
   EST FALL AREA OF UNBURNED DEBRIS WI:
   191100N1241800E 190500N 1251500E; 183900.00N 1251200E TO N18 44 00 E124 16 00 - N191100E124180000
   F)SFC G) FT666
   ```

4. **历史航警检索与图片导出**：点击页面底部功能按钮可按日期和 FIR 区域检索历史归档航警（`POST /fetch_archive`），或选择“当前地图视图 / 包含所有落区 / 自定义区域”进行 x1–x4 倍率高清图像导出。

### 5.2 本地解析器离线单测

无需联网即可运行仓库全部离线单元测试（5 项用例）或直接验证 `service/notam.py` 核心解析输出：
```bash
python3 -m unittest discover -s tests -v
python3 -c "from service.notam import raw, test_parse_notam; test_parse_notam(raw)"
```

---

## 6. 已知限制与跨平台说明

- **图像本地保存接口（`/save_image`）与跨平台导出**：Windows 桌面模式下可弹出 `tkinter.filedialog` 另存为对话框并自动复制图片到剪贴板（`win32clipboard`）；macOS / Linux 下服务端返回 `fallback_download: true`，前端 `exportImage.js` 自动通过浏览器下载保存导出图片。
- **在线数据源依赖外部网络**：FAA FNS 站点位于海外，部分网络出口可能受限或触发高频访问限制；程序内置 10 分钟缓存（`FETCH_EXPIRE_TIME = 600`）以避免短时间重复拉取。
