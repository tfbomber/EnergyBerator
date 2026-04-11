# D-ESS Project Walkthrough

## Module 2 — Unified Protocol v1.2 (Qualified)

### 通过条件 (Pass Criteria)
- ✅ 回归入口套件 `test_regression.py` 必须 **100% 通过**（无 xfail / 无容忍失败）。
- ✅ Unified v1.2 必须兼容 **V1.1 Legacy Mode** 的 120 天过渡期逻辑（字段映射 + reason code 映射 + 费率/计算口径对齐）。
- ✅ 运行产物 `d-ess-engine/evidence_store/evidence_index.json` 必须通过 **V1.2 Schema 校验**（结构、字段类型、hash 字段存在性与格式）。
- ✅ Verdict 聚合必须满足 v1.2 优先级契约（见下文），且 Extreme Suite 的 hard gates（Evidence/Anchor/Vorhabenbeginn）不可被 Overlay 覆盖。

### 优先级规则摘要 (Verdict Priority Contract)
系统采用严格的优先级聚合策略（从高到低）：
1. **BLOCKED**：硬阻断（例如 Evidence 缺失 / Anchor 无法定位）。一旦触发，其他结果均视为无效。
2. **INELIGIBLE_REJECTED**：资格不符（例如 Vorhabenbeginn 时间线违规）。
3. **NEEDS_INFO**：缺少关键材料或存在结构性冲突（例如 MISSING_FACTS / CONFLICT_DETECTED），流程挂起等待补齐。
4. **INVALID_INPUT**：输入不合法导致无法解析（例如日期格式错误）。
5. **APPROVED (PASS)**：当且仅当以上 1-4 均未触发时，判定为通过。

### Overlay 规则摘要 (Overlay Runtime Tag Policy)
- Overlay 在 Unified v1.2 中作为 **runtime 标签/说明信息** 使用（例如 PAUSED/PROGRAM_UNDER_REVISION）。
- **不改变主 verdict**：Overlay 不得覆盖 `INELIGIBLE_REJECTED` 等实质判定；唯一例外是 **BLOCKED** 永远保持最高优先级（Overlay 不可影响 BLOCKED）。
- **适配层说明**：统一协议适配层位于 `d-ess-engine/ui/adapter.py` (Thin client adapter)。

### 协议兼容策略 (Protocol Compatibility Policy)
- **Unified 优先**：默认以 Unified v1.2 作为主契约与主输出格式。
- **Legacy Protection（120 天）**：在启用 V1.1 Legacy Mode 且处于过渡期的范围内：
  - 保留 V1.1 的字段/Reason Code 映射与必要的计算口径兼容（作为对齐与解释用途），
  - 但最终对外输出仍必须满足 Unified v1.2 的枚举与审计轨迹要求。

### 详细报告
更多工程证据请参考：
- [Module 2 Final Test Report](reports/module2_final_report_unified_v1_2.md)

---
**Repro Command (repo root)**: `pytest -q d-ess-engine/tests/test_regression.py -x`
**Repro Command (in d-ess-engine/)**: `pytest -q tests/test_regression.py -x`
**Build Identity**: `tag=v1.2.0-beta / vcs=unversioned(local) / date=2026-03-01 / status=QUALIFIED / python=3.13.2 / os=Windows / evidence_schema=v1.2`

> 注：若 `requirements.lock` 缺失，则本次 Qualified 仅代表 **逻辑一致性通过**；不代表依赖可复现构建已锁定（Build Reproducibility 未达标）。

**Artifact Hashes (SHA256)**:
- `d-ess-engine/requirements.lock`: `32416CA8E6AFB42B851C5F284963A4DE1AEF47D8C64E2A10885AA0300BA31102` (Reproducibility=FULL)
- `d-ess-engine/ui/adapter.py`: `C8294CF014EB27270519854C7509F5F4CDFBF55386E2045E90BE4AA69C2244BE`
- `d-ess-engine/core/dess_main.py`: `E3F4CF57F7080B7DB44F5F7B2B9156FD99C0CC72CB690EA86E9CEA135932CDBE`
- `d-ess-engine/evidence_store/evidence_index.json`: `F2CECC48E5319F6E815EDCAA018D6FE9F129B7397CC76295094C91C5AD15FEA8`
- `d-ess-engine/tests/test_regression.py`: `20A9CBE4E83E6911C0B1DC6379D0C91CD30D1DBA635331A77E7B4F4A26376A3D`
