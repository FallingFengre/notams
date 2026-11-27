# 贡献指南 (Contributing Guide)

感谢你对 `notams` 项目的关注与支持！无论你是航天/航空爱好者、地理信息开发者还是高校开源实践者，我们都非常欢迎你通过 Issue 或 Pull Request 参与本项目建设。

---

## 1. 代码目录结构

```text
notams/
├── main.py                      # 程序入口：启动 Flask 服务并拉起浏览器或 PyWebview 窗口
├── config.py / config.ini       # 配置加载与运行时参数（FIR/ICAO、端口、缓存时长、会话参数）
├── requirements.txt             # Python 第三方依赖声明
├── run.sh                       # 命令行快捷启动菜单
├── docs/                        # 项目文档与系统架构图
│   ├── architecture.png         # 四层系统总体架构图
│   ├── INSTALL.md               # 安装部署与离线验证指南
│   └── ISSUES_SUMMARY.md        # 社区 Issue 与缺陷修复台账
├── tests/                       # 离线单元测试套件（零外网依赖）
│   └── test_core.py             # 解析器、几何重叠、去重与聚类单测
├── service/                     # 后端核心服务与数据处理引擎
│   ├── server.py                # Flask REST 接口、跨源时空去重、时间聚类及图像保存
│   ├── notam.py                 # 独立 ICAO NOTAM 解析器与 Shapely 跨日界线几何引擎
│   └── fetch/                   # 多源公开航行/海事通告采集适配器
│       ├── faa_browser.py       # Camoufox 无头浏览器会话管理器与 Promise.all 并发查询
│       ├── FNS_NOTAM_SEARCH.py  # 实时 NOTAM 抓取、过滤与格式化
│       ├── FNS_NOTAM_ARCHIVE_SEARCH.py # 历史 NOTAM 归档查询
│       ├── MSA_NAV_SEARCH.py    # 中国海事局政务公开航行警告解析
│       ├── MSI_NAV_SEARCH.py    # 美国 NGA MSI 公开海事警告解析
│       ├── dinsQueryWeb.py      # 历史 DINS 接口适配模块
│       └── self_test.py         # 采集连通性自测脚本
└── web/                         # 前端静态资源与交互页面
    ├── templates/               # index.html / placeholder.html
    ├── static/                  # 样式表、发射/着陆场图标与 Leaflet v1.9.4 库
    └── scripts/                 # 地图渲染、侧边栏、手动解析绘制、历史检索与高清导出 JS
```

---

## 2. 本地开发与验证流程

1. Fork 本仓库并在本地从 `main` 创建功能或文档分支（如 `feat/xxx` 或 `docs/xxx`）。
2. 按 [docs/INSTALL.md](docs/INSTALL.md) 安装依赖并配置本地环境。
3. 修改后端解析逻辑时，建议补充或运行离线单元测试验证无回归：
   ```bash
   python3 -m py_compile main.py config.py service/notam.py service/server.py
   python3 -m unittest discover -s tests -v
   python3 -c "from service.notam import raw, test_parse_notam; test_parse_notam(raw)"
   ```
4. 修改采集或前端交互后，启动 `python3 main.py` 在浏览器中验证自动绘制、手动输入、历史查询与导出功能是否正常。

---

## 3. 提交 Issue 与 Pull Request 规范

- **提交 Issue**：请清晰描述复现步骤、运行环境（操作系统、Python 版本）、相关航警报文样例（如涉及解析异常）或终端日志输出。
- **提交 Commit**：建议采用语义化前缀，如 `feat:`、`fix:`、`docs:`、`refactor:`、`perf:`，简洁写明改动动机与测试状态。
- **提交 Pull Request**：
  - 每个 PR 尽量聚焦单一功能或修复（如“新增 KML 导出”或“修复特定格式坐标解析”）；
  - 请勿提交本地调试缓存文件（`notam_results.json`、`msi_result.json`）、系统临时文件（`.DS_Store`）或个人编辑器配置（`.claude/`、`.vscode/`）。

---

## 4. 数据安全与合规红线（必读）

1. **数据源合法公开原则**：本项目仅采集与解析国内外民航、海事官方门户依法公开发布的航行通告与航行警告，严禁接入任何未公开、非授权或涉密数据来源。
2. **禁止敏感目标推演**：不得在主仓库代码中加入针对特定航天器或涉密载荷型号的自动定型、识别或敏感目标推断逻辑。
3. **第三方依赖许可兼容**：本项目采用 **MIT License**，引入新的第三方代码或依赖库时，请确认其开源许可证与 MIT 协议兼容，并在文档中注明出处与许可证类型。
