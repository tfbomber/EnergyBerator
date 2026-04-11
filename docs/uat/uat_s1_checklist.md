# UAT-S1 Smoke Test Checklist

| Case ID | 用户场景 | 操作输入 | 预期结果 | 状态 | 证据 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| UAT-01 | Golden 一次跑通 | 选政策 + E2E-01 证据 | 出 APPROVED 报告 | [x] | `UAT-01_report.json` |
| UAT-02 | 缺证据文件 | 不上传 evidence | BLOCKED + 原因清晰 | [x] | `UAT-02_report.json` |
| UAT-03 | Anchor 找不到 | 上传不含锚点的 PDF | BLOCKED + 显示 anchor_id | [x] | `UAT-03_report.json` |
| UAT-04 | Vorhabenbeginn 违规 | 填入早于允许日期 | INELIGIBLE_REJECTED | [x] | `UAT-04_report.json` |
| UAT-05 | 缺字段挂起 | 不填关键字段 | NEEDS_INFO + 缺失清单 | [x] | `UAT-05_report.json` |
| UAT-06 | 输入格式错误 | 日期格式错/金额格式错 | INVALID_INPUT + 指明字段 | [x] | `UAT-06_report.json` |
| UAT-07 | Overlay=PAUSED | 选择带 PAUSED 的 policy | PAUSED + verdict 并存 | [x] | `UAT-07_report.json` |
| UAT-08 | Legacy 模式可解释 | Legacy policy / context=LEGACY | v1.2 enum + legacy trace | [x] | `UAT-08_report.json` |
| UAT-09 | 导出可交付 | 导出 JSON | 文件可打开、字段齐全 | [x] | Artifact Dir |
| UAT-10 | 重跑一致性 | 同输入连续跑两次 | 结果一致 (Hash Match) | [x] | Match Log |

**Final Consensus**: 10/10 PASS
**Date**: 2026-03-01
