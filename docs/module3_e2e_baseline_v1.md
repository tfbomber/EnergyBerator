# Module 3 — E2E Integration Audit Baseline (v1.0)

## A. 基础 Smoke Suite（8 Cases）

> 目标：验证 E2E 闭环骨架稳定：`Policy Snapshot -> Evidence -> Anchor -> Gate -> Math -> Audit -> Export`

| Case ID | 核心点                | 触发条件（最小化）                                              | 预期 Verdict                    | 必须断言（Audit Trace）                                                                              |
| ------- | ------------------ | ------------------------------------------------------ | ----------------------------- | ---------------------------------------------------------------------------------------------- |
| E2E-01  | Golden APPROVED    | Evidence 存在且 hash 匹配；Anchor 可定位；事实完整；无时间线违规            | APPROVED                      | `policy_hash`、`evidence_hash`、`anchor_resolved=true`、`final_verdict=APPROVED`、`export_ok=true` |
| E2E-02  | Evidence Missing   | evidence_ref 指向不存在文件                                   | BLOCKED                       | `BLOCKED` + `reason=EVIDENCE_MISSING`（或等价）+ `evidence_check=failed`                            |
| E2E-03  | Anchor Not Found   | Evidence 存在但 anchor 无法定位                               | BLOCKED                       | `BLOCKED` + `reason=ANCHOR_NOT_FOUND` + `anchor_id` + `anchor_strategy`                        |
| E2E-04  | Vorhabenbeginn 违规  | 工作开始/付款早于允许时间线                                         | INELIGIBLE_REJECTED           | `final_verdict=INELIGIBLE_REJECTED` + `gate=VORHABENBEGINN` + 关键日期字段记录                         |
| E2E-05  | Missing Facts      | 必填字段缺失（例如日期/金额/资格字段）                                   | NEEDS_INFO                    | `final_verdict=NEEDS_INFO` + `missing_facts=[...]`                                             |
| E2E-06  | Invalid Input      | 日期格式不可解析（或金额格式错误）                                      | INVALID_INPUT                 | `final_verdict=INVALID_INPUT` + `parse_error` 明确字段名                                            |
| E2E-07  | Overlay 不改 verdict | policy runtime overlay=PAUSED（或关键词命中）但同时存在 REJECTED 原因 | INELIGIBLE_REJECTED（不变）       | `runtime_tags` 包含 PAUSED，但 `final_verdict` 不被覆盖（符合 v1.2）                                       |
| E2E-08  | Legacy 120 天兼容     | 开启 legacy_mode 且在过渡期范围内                                | verdict 依输入而定（推荐 APPROVED 样例） | audit 中必须同时记录：`legacy_mode=true`、`mapping_applied=V1.1`（说明性）且最终输出枚举仍为 v1.2                     |

---

## B. 防御性 Hardening Pack（4 Cases）

> 目标：验证 2026 真实业务里最容易“审计翻车”的边缘场景，确保系统保持**确定性 + 可解释**。

| Case ID | 核心点                | 触发条件（Input + Fixture）                                   | 预期 Verdict        | 关键 Reason / Trace 断言                                                                                   |
| ------- | ------------------ | ------------------------------------------------------- | ----------------- | ------------------------------------------------------------------------------------------------------ |
| E2E-09  | Umlaut/编码陷阱        | anchor 文本含德语特殊字符（ö/ü/ß），PDF 文本抽取出现乱码导致锚点失败              | BLOCKED           | `reason=ANCHOR_NOT_FOUND` 或 `TEXT_DECODE_ERROR`；trace 必须记录 `extracted_text_digest`（可选）或 `decoder_used` |
| E2E-10  | Zero-Byte / 损坏 PDF | evidence 文件存在但 size=0 或无法打开                             | BLOCKED           | `reason=FILE_READ_ERROR`（或等价）+ `file_size=0` / `pdf_open_failed=true`                                  |
| E2E-11  | 边界日期闭区间            | 申请/签约时间 = 截止日最后一刻 `2026-03-31T23:59:59`（明确时区或 naive 规则） | APPROVED（若其它条件满足） | audit 必须记录：`cutoff`、`comparison_operator`（<=）以及输入时间戳原值，防止“冤假错案”                                        |
| E2E-12  | 多源事实冲突             | UI 声明 `work_started=false`，但证据（发票/元数据）显示已动工或已付款         | NEEDS_INFO（不裁决）   | `final_verdict=NEEDS_INFO` + `conflicts=[{fact, source_a, source_b}]`；不得推理“谁对谁错”                       |

---

## C. 需要修正的点 (Protocol Reconciliation)

依据 **Unified v1.2** 契约：
* ✅ **Policy Snapshot 变更应影响 runtime_tags / policy_hash / 版本记录**
* ❌ 不应强制把 verdict 改成 NEEDS_INFO（除非另有 Gate 明确规定）。
* 验证 tag 存在、verdict 不变、audit 可追溯。

---

# 给 anti 的最终 Prompt（Module 3 — Smoke + Hardening v2）

```text
你是 D-ESS 的测试工程师。请为 Module 3（E2E Integration）建立“E2E Smoke + Hardening Pack”，目标是验证从 policy snapshot -> evidence/anchor -> gate aggregation -> math -> audit trace -> report export 的闭环确定性。

必须输出：
1) 新增 tests/test_e2e_smoke.py（或等价），包含 E2E-01 ~ E2E-08
2) 新增 tests/test_e2e_hardening.py（或等价），包含 E2E-09 ~ E2E-12
3) 每个用例必须断言：
   - final_verdict（严格等于预期）
   - runtime_tags（如适用，特别是 PAUSED）
   - report.audit_trail 中必须包含 policy_hash（强校验）
   - evidence_check / anchor_result / gate_trigger 的关键字段至少各 1 条
4) Zero-Inference 约束：
   - E2E-12 “多源事实冲突”必须输出 NEEDS_INFO，并在 audit_trail 中记录 conflicts 列表；禁止做任何“推断谁为真”。
5) 数值确定性：
   - 金额计算相关字段不得出现 float 漂移。测试里要求金额字段要么是 Decimal，要么是整数分（cents），并断言序列化输出稳定。
6) 时间线要求：
   - 所有测试日期必须使用 2026 年，并明确时区处理策略（naive 或 Europe/Berlin）；E2E-11 必须验证截止日闭区间（<=）逻辑。
7) Determinism：
   - 同一输入重复运行两次，导出的报告（至少关键字段集合）必须一致；如存在运行时间戳字段，需明确排除或固定化。
8) 不引入任何新业务逻辑：只允许新增测试、fixtures、以及必要的最小测试 harness。禁止改核心判定逻辑。

请在输出末尾给出：
- 新增/修改文件清单
- 每个文件的内容
- 运行命令（repo root 与 d-ess-engine/ 目录各一条，fail-fast -x）
```
