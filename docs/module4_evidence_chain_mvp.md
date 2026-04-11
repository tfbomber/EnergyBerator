# Module 4: Evidence Chain MVP Specification (v1.1)

本规格说明书定义了 D-ESS 证据链模块的最小可行版本（MVP），旨在将 Engine 的判定逻辑与实体审计凭据（Evidence）进行强制对齐。

---

## A. 定位与范围 (Positioning & Scope)

- **目标**: 实现“无证据不判定”。将审计结论从“规则通过”升级为“证据支撑的规则通过”。
- **MVP 包含 (IN-SCOPE)**:
  - 证据核对清单 (Checklist)
  - 证据三态状态 (YES/NO/UNKNOWN)
  - 外部引用链接 (Evidence Reference/URL)
  - 证据门禁 (Evidence Gate): 缺失证据将阻塞状态转换为 APPROVED。
- **MVP 不包含 (OUT-OF-SCOPE)**:
  - OCR 自动识别、发票真伪核验。
  - 自动 Sha256 Hash 校验（API 预留字段，但不强制验证）。

---

## B. Evidence 数据模型 (Business Protocol)

`evidence_pack` 是 Business JSON 的新增顶层字段，结构如下：

```json
{
  "evidence_pack": {
    "CONTRACT": {
      "status": "YES",
      "ref": "https://storage.local/docs/contract_v1.pdf",
      "note": "Signed on 10.02.2026",
      "uploaded_at": "2026-02-28T10:00:00Z",
      "hash_sha256": "e3b0c442..."
    },
    "PAYMENT_PROOF": {
      "status": "UNKNOWN",
      "ref": null,
      "note": "Down payment not yet confirmed by user"
    }
  }
}
```

---

## C. Evidence Gate 规则 (判定与证据的映射)

系统为每一个关键判定路径定义“Minimal Evidence Set（最小证据集）”。

| 判定路径 / Violation | 必需证据 (Required Evidence) | 缺失后果 (Consequence) |
| :--- | :--- | :--- |
| **Vorhabenbeginn (Timing)** | `CONTRACT`, `PROJECT_DESCRIPTION` | Status -> `NEEDS_INPUT`; Violation + `EVIDENCE_MISSING_CONTRACT` |
| **Payment Status** | `PAYMENT_PROOF` | Status -> `NEEDS_INPUT`; Violation + `EVIDENCE_MISSING_PAYMENT` |
| **Applicant Identity** | `IDENTIFICATION` | Status -> `NEEDS_INPUT`; Violation + `EVIDENCE_MISSING_ID` |
| **Technical Eligibility** | `TECHNICAL_SPEC` | Status -> `NEEDS_INPUT`; Violation + `EVIDENCE_MISSING_TECH_SPEC` |

**逻辑流程**:
1. Engine 执行规则判定。
2. 命中某条需证据支撑的规则（如 Timing）。
3. 检查 `evidence_pack` 中对应的 `status`。
4. 若 `status` 为 `NO` 或 `UNKNOWN`：
   - 将原有可能的 `APPROVED` 状态强制降级为 `NEEDS_INPUT`（或保持 `ON_HOLD_PROVISIONAL` 但标记风险）。
   - 在 Violation 列表中注入 `EVIDENCE_MISSING_*` 代码。

---

## D. Evidence Anchors (政策依据 vs 事实依据)

在审计报告（S2）中，每一条判定必须同时包含：
- **Policy Anchor (规则依据)**: 对应政策原文中的条款 ID（例如 `dus_balcony_pv_2025.timing_rules.contract_clause`）。
- **Evidence Ref (事实依据)**: 对应用户提交的凭证引用（例如 `evidence_pack.CONTRACT.ref`）。

---

## E. Report 输出要求 (S2 - Evidence Trail)

审计报告中将新增 `evidence_trail` 区块，用于展示审计核对单。

```json
"evidence_trail": {
  "summary": { "count_required": 4, "count_verified": 3, "count_missing": 1 },
  "checklist": [
    {
      "label": "Final Invoice",
      "required": true,
      "verified": "YES",
      "ref": "INV-2026-001"
    }
  ]
}
```

---

## F. 附录模板

### Appendix A: Minimal Evidence Set Mapping (YAML)
```yaml
logic_gates:
  timing_check:
    required: ["CONTRACT", "PROJECT_DESCRIPTION"]
    error_code: "EVIDENCE_MISSING_TIMING"
  cost_audit:
    required: ["INVOICE_OR_OFFER", "PAYMENT_PROOF"]
    error_code: "EVIDENCE_MISSING_COSTS"
```

### Appendix B: 新增 Violation Codes
- `EVIDENCE_MISSING_CONTRACT`: 缺少合同或订单确认件。
- `EVIDENCE_MISSING_PAYMENT`: 缺少转账证明或发票收据。
- `EVIDENCE_MISSING_TECH_SPEC`: 缺少技术参数表（如 PV 组件功率证明）。
- `EVIDENCE_STATUS_UNKNOWN`: 提供证据但状态未标记，需要核实。
