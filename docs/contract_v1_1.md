# D-ESS Business & Technical Contract v1.1 (Gold)

本协议定义了 D-ESS Engine v1.1 的核心行为准则、状态逻辑与数据契约，是实现 “German-grade Rigor” 与审计可追溯性的基石。

## 1. 对外状态枚举 (Status Enums)

Engine 输出的 `status` 字段必须严格遵循以下五种状态：

| 状态 (Status) | 含义 | 业务行为 |
| :--- | :--- | :--- |
| **APPROVED** | 自动审计通过 | 符合所有已知规则，可输出正式 subsidy 建议。 |
| **REJECTED** | 自动审计拒绝 | 明确违反关键红线（如逾期、身份不符），subsidy 为 0。 |
| **NEEDS_INPUT** | 需要人工干预 | 关键信息缺失、属性为 `UNKNOWN` 或存在歧义（Same-day）。 |
| **ON_HOLD_PROVISIONAL** | 政策性挂起 | 政策处于 PAUSED 状态，计算结果仅供参考 (Provisional Math)。 |
| **BLOCKED** | 系统性封堵 | 政策处于 CLOSED 状态，完全中止审计流程。 |

---

## 2. Policy Runtime 状态机规则 (Verdict Decoupling)

政策运行状态（由 Crawler/Intelligence 驱动）具有最高优先级的判定权：

- **Policy CLOSED**: 
  - 触发 `REJECTED_POLICY_CLOSED` 违规。
  - Status 强制设为 `BLOCKED`。
  - `final_subsidy` 强制归零。
- **Policy PAUSED**: 
  - 触发 `POLICY_PAUSED` 与 `PROVISIONAL_MATH` 警告。
  - Status 强制设为 `ON_HOLD_PROVISIONAL`。
  - 允许计算并显示 `hypothetical_subsidy`，用于 orientation 目的。

---

## 3. Tri-state 准则 (YES / NO / UNKNOWN)

严禁在信息不足时进行过度推断（Zero-Inference）。

### 3.1 核心逻辑
- **YES**: 满足条件，推进逻辑。
- **NO**: 明确不满足，触发拒绝/排除。
- **UNKNOWN**: 
  - **不得默认跳转为 YES**。
  - 在 Audit 模式下：必须通过 `MISSING_ATTRIBUTES` 或专用的 `UNKNOWN` 类 violation 回显。
  - 状态通常降级为 `NEEDS_INPUT`（如果该字段是判定所必需的）。

### 3.2 适用范围
- `applicant`: `is_private_person`, `has_duessepass`
- `timeline`: `has_conditional_clause`, `down_payment_made`, `work_started`
- `costs.items`: `is_eligible`

---

## 4. 数学可见性 (Math Visibility)

为了保证“透明审计”，Engine 必须即使在失败时也保持计算逻辑的可见性。

- **Eligible Cost Total**: 无论最终 Verdict 如何（即使是 REJECTED），审计追踪中的“合规费用总额”应基于输入数据保持可见，以便用户理解“如果我合规，能拿多少”。
- **Final Subsidy**:
  - 在 `APPROVED` / `ON_HOLD_PROVISIONAL` 状态下显示计算结果。
  - 在 `REJECTED` / `BLOCKED` 状态下为 0.00。
  - 在 `NEEDS_INPUT` 状态下，输出结果应标注为 `ORIENTATION_ONLY`。

---

## 5. 命名与兼容性约定

- **字段一致性**: 所有接口 JSON 字段使用小写下划线蛇形命名（snake_case）。
- **解耦显示**: `violation.code` 是机器读取的唯一断言依据；`message_cn` 是人类阅读的最终解释。
- **时间格式**: 优先支持 `DD.MM.YYYY` (German Standard) 与 `ISO8601` (System Standard)。
- **金额单位**: 内部核心计算统一使用 `cents` (Integer)，API 输出统一转换为 `EUR` (Float/String)。
