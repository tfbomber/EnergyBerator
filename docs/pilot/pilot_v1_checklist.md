# Module 6 — Pilot (Field Beta) 执行计划（Final v1.0）

## 0) Pilot 的核心原则

Pilot 的成功不是 “PASS 数量”，而是：
**仅通过 `report.json` + `pilot_feedback.md` 就能还原决策链、解释原因、给出下一步动作**（不看代码也能复盘）。

---

## 1) 必须新增的工程协议

### 1.1 脱敏审计协议（Redaction Rule）✅

**适用范围：** 所有 `artifacts/pilot_v1/P-0X/evidence/` 中的真实 PDF/图片/发票等。
**规则：**
* 必须脱敏：姓名、电话、邮箱、完整门牌号、银行账号、客户号、签名等
* 允许保留：城市/区域、PLZ（建议 40xxx）、政策必要字段、金额、日期
* **重要：** 版本库/共享目录里只能存“脱敏后的干净证据”，确保 `evidence_hash` 永远对应脱敏文件

**验收：**
* 每个案例目录新增一份：`redaction_checklist.md`

### 1.2 可解释性成本（Explainability Cost）✅

**要求：** `pilot_feedback.md` 必须包含：
* “用户是否理解为什么被阻断/拒绝？”（Yes/No）
* “用户下一步是否明确怎么做？”（Yes/No）
* “如果 No，哪句话/哪个字段不清楚？”

### 1.3 Zero-Inference 压力测试（P-05）✅

**P-05 的通过标准写死：**
* 必须输出 `NEEDS_INFO`
* 必须产出 `conflicts` 清单（或等价结构）
* 禁止任何“自动修正/脑补选择”
* audit 中必须能看到冲突对

### 1.4 Shadow Anchor Check（阴影锚点）✅

**执行方式：**
* 在 `pilot_feedback.md` 里记录：`shadow_anchor_notes`
* 记录：期望锚点字符串、实际 PDF 视觉文字、失败现象
* 如需调试，在 artifact 侧补一个 `anchor_debug_snippet.txt`

---

## 2) Pilot 案例组合（Priority: P-01, P-02, P-05）

* **P-01 真实 Golden（干净 PDF）**
* **P-02 扫描 PDF（无文本层）**：预期 BLOCKED，但必须“说人话 + 下一步指令”
* **P-05 多源事实冲突**：预期 NEEDS_INFO + conflicts 清单

---

## 3) 归档规范（强制）

`d-ess-engine/artifacts/pilot_v1/P-0X/` 内必须包含：
- `policy_snapshot.json`
- `input_case.json`
- `evidence/`（脱敏后）
- `evidence_index.json`
- `report.json`
- `pilot_feedback.md`
- `redaction_checklist.md`
- `anchor_debug_snippet.txt` (可选)

---

## 4) Pilot 验收标准

* 至少 **3 个案例（P-01/P-02/P-05）全链路完成归档**
* 每个案例包含完整的报告、Hash 追溯及反馈表
* P-02 做到：BLOCKED + 人话解释 + 下一步操作指令
* P-05 做到：NEEDS_INFO + conflicts 清单 + 禁止推断

---

## 5) Module 7 的进入条件

* 扫描 PDF 占比高，用户频繁卡在 “无文本层”
* Umlaut/编码导致 anchor 失败频发
* 用户反馈中 “不理解原因/下一步不清楚” ≥ 2 次
* P-05 conflicts 表达不清晰
