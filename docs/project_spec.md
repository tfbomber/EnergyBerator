# D-ESS Engine Project Specification (v1.2)

## 1. 项目愿景与核心架构 (Philosophy & Architecture)

### 1.1 核心哲学：德国级严谨度 (German-Grade Rigor)
D-ESS (Düsseldorf Energy Stacking Solver) 不仅仅是一个计算器，而是一个**可审计的合规导航引擎**。其设计遵循以下原则：
- **零推断 (Zero-Inference)**：在数据缺失或模糊时，系统拒绝假设，强制降级为 `NEEDS_INPUT` 或输出 `UNKNOWN` 警告。
- **状态机化建议**：将晦涩的政策条款（如 Vorhabenbeginn）转化为确定性的状态转换逻辑。
- **证据锚定 (Evidence Anchors)**：每一个计算结果和审计结论必须关联到官方文档的特定页码或段落锚点。

### 1.2 物理架构 (Module Interaction)
系统由 Python 编写，采用解耦的模块化设计：
- `dess_main.py`：分发中心，负责加载 Policy、Case，调度各模块并生成最终报告。
- `dess_state_machine.py`：生命周期哨兵，执行 Vorhabenbeginn（动工/签约时间线）逻辑检查。
- `cost_engine.py`：成本精算，处理多维度成本桶（Buckets）及 VAT（增值税）转换。
- `solver.py`：叠加优化器，在多政策互斥与上限（Kumulierungsgrenze）约束下计算最大补贴。
- `evidence.py`：审计链管理，负责文件哈希校验（SHA-256）与锚点索引解析。

---

## 2. 数据契约与内容方案 (Data Schemas)

### 2.1 案例输入契约 (Case Schema - V1.2)
```json
{
  "case_id": "TC-2026-DUS-001",
  "engine_context": "V1.2",
  "timeline_events": [
    { "event_type": "APPLICATION_SUBMITTED", "date": "2026-03-01" },
    { "event_type": "CONTRACT_SIGNED", "date": "2026-02-28", "is_conditional": true }
  ],
  "costs": {
    "buckets": {
      "HARDWARE": { "amount": "15000.00", "amount_basis": "NET" },
      "LABOR": { "amount": "5000.00", "amount_basis": "GROSS" }
    }
  },
  "attributes": {
    "is_private_person": true,
    "bonuses": ["KLIMA_GESCHWINDIGKEITS_BONUS"],
    "other_subsidies_cents": 500000
  }
}
```

### 2.2 政策定义契约 (Policy Schema)
政策 JSON 文件存储于 `policies/` 目录，核心字段包括：
- `timing_rules`: 定义 `blocking_actions`（如 WORK_STARTED）。
- `cost_rules`: 定义合规的成本桶及对应的 `vat_rate`。
- `calculation`: 
  - `grant_rate`: 基础补贴率（如 30%）。
  - `cap_cents`: 硬上限。
  - `stacking_limit`: 叠加上限（如不超过总成本的 70%）。
  - `bonuses`: 条件触发的加成额度（add_grant_rate / add_fixed_cents）。

---

## 3. 核心逻辑深挖 (Logic Deep-Dive)

### 3.1 Vorhabenbeginn Gate (状态机闸门)
系统通过 `check_timing` 函数进行判定：
- **违规判定**：如果 `CONTRACT_SIGNED` 或 `WORK_STARTED` 早于 `APPLICATION_SUBMITTED` 且没有 `conditional_clause`（附条件条款），直接触发 `REJECTED`。
- **同一天原则**：申请与签约同日发生时，系统标记为 `AMBIGUOUS`，要求用户提供带时间戳的辅助凭证。
- **宽限期**：支持根据政策配置 `vorhabenbeginn_limit_days`（宽限天数）。

### 3.2 多维成本精算 (Cost Engine)
- **VAT 转换**：系统自动处理 `NET` 与 `GROSS` 的换算。政策通常有指定的 `eligible_basis`（如 KfW 458 使用 GROSS）。
- **浮点数规避**：所有货币计算在核心层强制转换为 `Integer Cents` 或 `decimal.Decimal`，严禁使用浮点数，确保 100% 精确。

### 3.3 叠加优化器 (Stacking Optimizer)
- **Kumulierungsgrenze**：执行公式 `MaxTotal = EligibleCost * StackingLimit`。
- **优先级**：当多个 Bonus 冲突时，系统根据政策配置应用最高加成或累加逻辑。
- **输出**：提供 `math_trace`，记录计算每一步的中间变量。

---

## 4. 情报层与动态监控 (Intelligence Layer)

- **Runtime Overlay**：系统在运行时读取 `intelligence/status_updates.json`。
- **优先级**：如果 Crawler 探测到政策已 `PAUSED` 或 `CLOSED`，则覆盖静态 JSON 状态。
- **审计优先**：即使用户在 Overlay 状态（如 PAUSED）下试图计算，如果其基础条件（如动工日期）不合规，系统仍会优先报出 `REJECTED` 违规。

---

## 5. 质量保障体系 (QA & Standards)

### 5.1 审计追踪 (Audit Trail)
每个报告包含一个 `audit_trail` 列表，每条记录必须包含：
- `step_id`：逻辑步骤 ID。
- `amount_cents`：该步骤产生的金额变动。
- `evidence_anchor`：关联的政策文本页码/锚点。

### 5.2 回归测试流程
- **Golden Cases**：核心逻辑修改后，必须通过 `Golden_Suite` 的回归测试。
- **Contract Validation**：所有生成的 JSON 报告必须通过 `validate_report_contract` 的 Schema 校验，确保前端加载不报错。

---
*Document Version: 1.2.0-Alpha | Created by Antigravity*
