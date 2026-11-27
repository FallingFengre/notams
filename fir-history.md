# Joey0609/notams 历史航警 FIR 统计

2025-10-16 至 2026-11-27（UTC），三个公开分支 main、V1、release 共包含 2,136 个由 github-actions[bot] 提交且相对第一父提交新增或修改了根目录 data_dict.json 的快照。其中 1,923 个提交可从 main 到达，共检查了 1,453 种不同的机器人快照内容。main 截点为 `845a5ec472e7151717f564fda3290c225cbb3936`。没有变更文件的运行无法从提交历史计数。

1,504 个快照含航警 FIR 字段，其中 1,500 个含有四字母代码。其余 632 个快照没有航警 FIR 字段。含该字段的机器人快照最早可追溯到 2026-03-29（UTC）。

## 字段中出现的 41 个代码

检查了旧版顶层的逐行字段、新版 FOCUSED_NOTAM_DATA、NOTAM_DATA 和各来源快照。仅纳入航警记录。同一提交中的相同代码只计一次；一次通告可能保留在连续多次提交里，故下表按快照出现次数计。重点位置按截点当天的配置判断，31 个重点位置覆盖了其中 21 个代码。

| FIR | 含该代码的快照提交数 | 在原重点清单中 |
|---|---:|---|
| EGGX | 50 | 否 |
| FAJO | 123 | 否 |
| FIMM | 189 | 否 |
| KZAK | 326 | 是 |
| LPPO | 121 | 否 |
| MDCS | 44 | 否 |
| MKJK | 50 | 否 |
| MMFO | 695 | 否 |
| MMFR | 1,190 | 否 |
| MTEG | 47 | 否 |
| MUFH | 84 | 否 |
| NTTT | 1,156 | 否 |
| NZZC | 297 | 否 |
| NZZO | 419 | 否 |
| RCAA | 66 | 是 |
| RJJJ | 732 | 是 |
| RKRR | 394 | 是 |
| RPHI | 1,424 | 是 |
| SCIZ | 1,180 | 否 |
| SCTZ | 2 | 否 |
| SMPM | 11 | 否 |
| SOOO | 21 | 否 |
| TNCF | 80 | 否 |
| TTZP | 55 | 否 |
| VCCF | 127 | 是 |
| VHHK | 92 | 否 |
| VOMF | 336 | 是 |
| VVHM | 63 | 是 |
| WIIF | 17 | 是 |
| WMFC | 177 | 是 |
| WSJC | 106 | 是 |
| YMMM | 477 | 是 |
| ZBPE | 333 | 是 |
| ZGZU | 287 | 是 |
| ZHWH | 141 | 是 |
| ZJSA | 151 | 是 |
| ZLHW | 993 | 是 |
| ZPKM | 348 | 是 |
| ZSHA | 468 | 是 |
| ZWUQ | 251 | 是 |
| ZYSH | 106 | 是 |
 
## 原文补充与异常值

对缺少可用 FIR 字段的航警，另取原始报文 Q) 和 A) 段中的区域标识，并与公开的历史 FIR/UIR 图层交叉核对。DGAC、VECF、YBBB 三个额外代码均有 Q) 段佐证。将其与字段中的代码合并，可得到以下 44 个有历史依据的优先查询位置。

```text
DGAC EGGX FAJO FIMM KZAK LPPO MDCS MKJK MMFO MMFR MTEG MUFH NTTT NZZC NZZO RCAA RJJJ RKRR RPHI SCIZ SCTZ SMPM SOOO TNCF TTZP VCCF VECF VHHK VOMF VVHM WIIF WMFC WSJC YBBB YMMM ZBPE ZGZU ZHWH ZJSA ZLHW ZPKM ZSHA ZWUQ ZYSH
```

航警字段还出现了 UNKNOWN（6 个提交）和旧检索任务名 FUCK2（1 个提交）。海警使用同名字段保存 UNKNOWN 或数字分区 5、7、8、11、13、14。

快照反映项目按当时的查询范围和规则筛选后保留的通告。缺失字段、采集故障、范围外的通告及未来出现的新区域，都会限制这份清单的覆盖能力。

[仓库快照](https://github.com/Joey0609/notams/blob/845a5ec472e7151717f564fda3290c225cbb3936/data_dict.json) · [地区配置](https://github.com/Joey0609/notams/blob/845a5ec472e7151717f564fda3290c225cbb3936/config.ini) · [用于交叉核对的历史图层](https://services5.arcgis.com/62o2qANhRqripAuB/arcgis/rest/services/ICAO_Flight_Information_Region/FeatureServer/12)
