# D-ESS MVP Product & Technical Spec (v1.1)

**Status**: Final (Audit-Ready)  
**Version**: 1.1  
**Last Updated**: 2026-02-28  
**Role Binding**: PM + Compliance Architect + UX Designer  
**Scope**: Module 2 (Plan) & Module 3 (Audit)  

---

## 0. Protocol 宪法 (System Philosophy)

本协议旨在规范 D-ESS 系统各层级的技术交互，确保在“德国标准”下实现结论的长久可追溯性。

1.  **Zero-Inference (零推断原则)**: 系统禁止对缺失数据进行猜测。所有事实字段必须支持 `UNKNOWN` 枚举。若关键核查点（如首付日期）为 `UNKNOWN`，系统必须通过 `AT_RISK` 状态显式反馈。
2.  **Thin Client (瘦客户端)**: UI (Streamlit) 仅作为纯展示层与数据采集层。所有逻辑判定（Verdict）、准入闸门（Gate）、计算过程（Audit Trail）必须来自核心引擎。UI 严禁包含 IF-ELSE 业务逻辑判定。
3.  **Verdict Decoupling (结论解耦)**: 
    - **Primary Verdict (对外状态)**：决定报告最终定性。当政策处于 `PAUSED` 时，Primary Verdict 必须强制设为 `ON_HOLD_PROVISIONAL`，禁止出现“PAUSED 状态下的 REJECTED”。
    - **Hypothetical Verdict (推测判定)**：内在逻辑冲突（如违规）以 `violation` 形式记录（例如 `code: WOULD_REJECT`），仅在详情页供专业审计员分析。
4.  **Math Visibility (计算透明化)**: 无论判定结果为何（Pass/Fail/Paused），`Eligible Cost Total` (合规费用总计) 必须计算并展示。计算中间过程 (`calc_trace`) 必须包含锚点关联 (`evidence_refs`)。
5.  **Audit Traceability (审计可追溯)**: 每一份报告必须锚定 `policy_hash`、`runtime_status` 以及此时此刻的 `overlay_gate_applied` 布尔状态及其触发原因。

---

## 1. Module 2: Plan (Sales Hook / 方案咨询)

**核心目标**: 针对潜在客户，提供“1分钟快速推演”，通过红线预警（Redline）防止用户由于错误操作（提前签署/支付）导致资格丧失。

### 1.1 输入协议（Minimal Intake）
| 字段 | 类型 | 是否必填 | 备注 |
| :--- | :--- | :--- | :--- |
| `policy_id` | Enum | Yes | DUS_BALCONY_PV_2025 等 |
| `measure_type` | Enum | Yes | BALCONY_PV / HEAT_PUMP |
| `is_conditional` | Bool | No | 映射 `has_conditional_clause` |
| `timing_set` | Object | No | 包含 `contract_signed_at`, `down_payment_at`, `work_started_at` |
| `application_date` | Date | No | 预估申请日期 |

### 1.2 费用模式：Quick vs. Exact
-   **Quick Estimate (估算模式)**:
    -   允许输入单数值（估算总额）。
    -   输出必须附加 `confidence_tag`: `LOW` (缺详细项) / `MED` / `HIGH`。
    -   报告必须显著标注 **`PROVISIONAL_MATH`** 标签。
-   **Exact Costs (精确模式)**:
    -   用户提交 itemized `cost_items`。
    -   移除 `PROVISIONAL_MATH` 标签，显示“基于精确报价值”。

### 1.3 S2 Report (Plan) 框架
1.  **Verdict Card**: 展示 `APPROVED` / `REJECTED` 或 `ON_HOLD` (Purple UI)。
2.  **Redline 执行卡 (核心)**: 
    -   `ALLOWED` (绿): "您当前可以签署【带解除条件】的合规合同。"
    -   `FORBIDDEN` (红): "**禁止支付任何定金**。后果：市级补贴将立即降至 0.00 €。"
    -   `CAUTION` (黄): "存在日期重合歧义，请确保证件顺序。"
3.  **The Math**: 包含 `eligible_cost_total` 与 `final_subsidy`。
4.  **Evidence Checklist**: 为后续审计准备的材料清单。

---

## 2. Module 3: Audit (Compliance Shield / 项目审计)

**核心目标**: 针对已开始执行的项目，进行事实核查。输出“合规判定书”，作为领取补贴的技术依据。

### 2.1 Audit 输入协议 (Engineering Schema)
-   **`project_stage`**: `PRE_CONTRACT | POST_CONTRACT | POST_APPLICATION | IN_PROGRESS | COMPLETED`
-   **Timing Ledger**: 必须包含 `application_status` (`UNKNOWN/PREPARATION/SUBMITTED/APPROVED`) 和 `receipt_status`。
-   **Cost Items**: 包含 `id`, `category`, `description`, `amount_cents`, `is_eligible` (`YES/NO/UNKNOWN`)。
-   **Evidence Pack**: `per type -> { status: YES/NO/UNKNOWN, ref: string, note: string }`。

### 2.2 六块判定书输出结构
1.  **Audit Verdict**: 极简大色卡展示 `PASS | AT_RISK | FAIL | ON_HOLD_PROVISIONAL`。
2.  **Issues & Warnings**: 按 `severity` (HIGH/MED/LOW) 排序。提供人话版纠偏建议。
3.  **The Math (三柱式)**:
    -   `Eligible Cost Total`: 算法底数。
    -   `Final Subsidy`: 扣除违约/闸门后的实际发放值。
    -   `Hypothetical Subsidy`: 仅在 `PAUSED` 时出现，展示“如政策恢复后预期”。
4.  **Delta Report (核心)**: 展示 `Ideal Path` vs `Actual Facts`。明确计算 `delta_eur` 并标识 `reason_codes` (如 `EARLY_PAYMENT`)。
5.  **Remedy / Plan B**: 提供补救操作（如“由税务顾问验证所得税 §35c 替代方案”）。
6.  **Audit Trace**: 展示 `policy_hash`, `as_of`, `overlay_gate_applied`。

### 2.3 AT_RISK 触发逻辑
-   **Ambiguity (歧义)**: 签约与申请日期重合且无具体时间戳。
-   **Evidence Unknown**: 关键物证缺失状态标记为 `UNKNOWN`。
-   **Freshness Warning**: 政策验证时间戳过期（见下章）。

---

## 3. Policy Runtime & Freshness

-   **Policy Rules**: 存储在 `policy_rules.json`。核心字段必须包含 `last_verified_at` (ISO UTC) 和 `policy_hash`。
-   **Status Overlay**: 通过 `status_updates.json` 实现轻量动态更新。支持 `keyword` 匹配（如 "überarbeitet" -> `PAUSED_OVERLAY`），匹配逻辑需大小写不敏感。
-   **Freshness Gate**:
    -   逻辑：`If (now - last_verified_at) > 14 days`。
    -   行为：**禁止硬阻断**。但在所有计算结果旁强制追加 `PROVISIONAL_MATH` 字样，告知用户数据时效性一般。

---

## 4. Streamlit UI 设计规范

### 4.1 全局布局
-   **Top State Bar**: 实时显示当前进度（S1-S5）及 `Policy Status` 标签。
-   **Sidebar**: 模块切至 `Plan` 或 `Audit` 视图。
-   **Right Inspector**: 折叠式面板，显示当前的 `Business JSON Payload` 全量数据，供极客用户校验输入是否有脏数据。

### 4.2 交互逻辑 (Smart Adapter)
-   **自动清洗**: 用户输入 `1.099,00 €` 时，UI 透传给 `adapter.py` 进行去杂。若解析失败，UI 必须报错 `COST_PARSE_ERROR` 并阻止提交。
-   **数据承接 (Plan -> Audit)**: 
    -   当用户从 Plan 点击“转入正式审计”时，已有字段需根据逻辑带入。
    -   **新增必填高亮**: 缺失字段（如证据占位符）需标记为橙色背景，提示“Audit 必要项”。

### 4.3 颜色语义字典
-   **PASS (Green)**: `#2E7D32` (Approved / Match)
-   **AT_RISK (Yellow)**: `#F57F17` (Missing Evidence / Ambiguity)
-   **FAIL (Red)**: `#C62828` (Hard Reject)
-   **ON_HOLD (Purple)**: `#6A1B9A` (Paused / Provisional)

---

## 5. Appendices (The Schema Standard)

### Appendix A: Plan Business JSON Template
```json
{
  "case_id": "PLAN-2026-001",
  "as_of": "2026-02-28",
  "policy_id": "DUS_BALCONY_PV_2025",
  "costs": {
    "mode": "QUICK",
    "total_estimate_eur": 1298.0
  },
  "timeline": {
    "contract_has_conditional_clause": true,
    "contract_signed_date": "2026-02-10",
    "application_submitted_date": null
  }
}
```

### Appendix B: Audit Business JSON Template
```json
{
  "project_stage": "POST_APPLICATION",
  "timing_ledger": {
    "application_status": "SUBMITTED",
    "contract_signed_date": "2026-02-10",
    "has_conditional_clause": "YES",
    "payment_made_date": "2026-02-12"
  },
  "cost_items": [
    {"id": "c1", "category": "HARDWARE", "amount_cents": 109900, "is_eligible": "YES"}
  ],
  "evidence_pack": [
    {"type": "CONTRACT_COPY", "status": "YES", "ref": "SHA256:abcd..."}
  ]
}
```

### Appendix C: Violation Codes Dictionary (MVP 标准集)
| Code | Severity | Category | Description (中文语义) |
| :--- | :--- | :--- | :--- |
| `VORHABENBEGINN_BEFORE_APPLICATION` | HIGH | Timing | 申请前项目已启动 (违规) |
| `PAYMENT_BEFORE_APPLICATION` | HIGH | Timing | 申请前存在支付行为 (违规) |
| `WORK_STARTED_BEFORE_APPLICATION` | HIGH | Timing | 申请前已开工 (违规) |
| `CONDITIONAL_CLAUSE_EXEMPTION` | INFO | Timing | 触发附条件合同豁免条款 |
| `AMBIGUOUS_SAME_DAY_ORDER` | MED | Timing | 同日先后顺序歧义 |
| `MISSING_APPLICATION_EVENT` | MED | Timing | 缺少申请递交记录 |
| `POLICY_PAUSED` | HIGH | Policy | 政策修订暂停中 |
| `POLICY_CLOSED` | HIGH | Policy | 政策已正式关闭 |
| `POLICY_FRESHNESS_STALE` | MED | Policy | 政策同步时间过久 (14天+) |
| `HYPOTHETICAL_VERDICT` | INFO | Verdict | 假设性研判结果 (PAUSED 时可见) |
| `PROVISIONAL_MATH` | INFO | Math | 预估性数学模型 |
| `COST_PARSE_ERROR` | HIGH | Cost | 金额格式解析失败 |
| `COST_AMOUNT_MISSING` | HIGH | Cost | 必填费项金额缺失 |
| `COST_NEGATIVE_AMOUNT` | MED | Cost | 费项含负数，已自动过滤 |
| `DUPLICATE_ITEM_DETECTED` | MED | Cost | 检测到重复费项 |
| `ELIGIBLE_FLAG_MISSING` | MED | Cost | 合规标记缺失 |
| `DATE_PARSE_ERROR` | Input | HIGH | 日期格式非法 (如 2月29日) |
| `DATE_FORMAT_UNSUPPORTED` | MED | Input | 日期格式不符合 ISO/Euro 标准 |
| `EVIDENCE_MISSING` | MED | Evidence | 关键审计物证缺失 |
| `EVIDENCE_EXPIRED` | MED | Evidence | 证明文件已失效 |
| `ANCHOR_VALIDATION_FAILED` | Audit | HIGH | 证据锚点校验失败 |
| `CRAWLER_UNHEALTHY` | System | LOW | 策略情报抓取异常 |

---
**Disclaimer**: Orientation only / requires manual verification / based on last known rules as of test date.
