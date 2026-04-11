# D-ESS Violation → Flash UI Dictionary (v1.1)

本字典定义了 Engine 输出的违规代码与前端 UI 显示的映射关系。所有描述均采用“审计口径”，避免直接承诺补助。

| 唯一代码 (Code) | 严重程度 | 标题 (Title_CN) | 消息内容 (Message_CN) | 用户操作建议 (Action_CN) | 模块 | 关联证据 (M4) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **POLICY_PAUSED** | MED | 政策修订中 | 当前补助政策正在修订或暂停（PAUSED）。计算结果仅供参考，不作为最终依据。 | 建议等待官方正式重启后再行申请。 | BOTH | N/A |
| **REJECTED_POLICY_CLOSED** | HIGH | 政策已关闭 | 当前补助政策已停止受理（CLOSED）。系统已停止自动审计。 | 建议查看是否有替代政策或联系咨询顾问。 | BOTH | N/A |
| **PROVISIONAL_MATH** | LOW | 临时性测算 | 由于政策或输入状态处于非确定模式，计算结果标记为“临时（Provisional）”。 | 补充缺失数据或等待政策更新。 | BOTH | N/A |
| **VORHABENBEGINN_BEFORE_APPLICATION** | HIGH | 申请前已动工 | 在正式提交申请前已签署合同或支付款项，违反“资助前置”原则。 | 请核实合同签署日期是否早于申请日期。 | AUDIT | 合同原文 |
| **PAYMENT_BINDING** | MED | 存在约束性付款 | 检测到在申请完成前已支付定金或全款，可能影响补助资格。 | 提供付款凭证，核实是否包含“退款条款”。 | AUDIT | 银行回单 |
| **WORK_STARTED_BINDING** | HIGH | 物理工程已启动 | 检测到在获得预核准前已开始物理安装。 | 通常无法补救。请核实施工日志。 | AUDIT | 施工合同/照片 |
| **AMBIGUOUS_SAME_DAY_ORDER** | MED | 申请与签约同日 | 申请与签约在同一天发生，无法确认先后顺序。 | 请提供带时间戳的电子邮件或系统日志作为辅助凭证。 | AUDIT | 邮件截图/日志 |
| **MISSING_ATTRIBUTES** | MED | 属性缺失 | 关键审计属性（如合同是否带条件）未明确，无法完成闭环判定。 | 请在“项目详情”中补全相关属性。 | AUDIT | 合同附件 |
| **DATE_PARSE_ERROR** | MED | 日期格式错误 | 提交的日期格式（如 2026-13-45）无法被系统识别。 | 请使用 DD.MM.YYYY 或 ISO8601 标准。 | BOTH | N/A |
| **COST_PARSE_ERROR** | MED | 金额格式错误 | 提交的费用金额无法解析为数字。 | 请检查是否包含非法字符，建议使用 1.200,00 格式。 | BOTH | 报价单/发票 |
| **INPUT_INVALID_NEGATIVE_AMOUNT** | HIGH | 无效负数金额 | 检测到费用金额为负值，系统无法处理。 | 请修正金额为正数。 | BOTH | N/A |
| **DUPLICATE_ITEM_DETECTED** | LOW | 重复子项提醒 | 系统检测到多条费用条目名称与金额高度重合，可能存在误报。 | 请核实费用清单是否有重复录入。 | BOTH | 费用明细 |
| **ELIGIBLE_FLAG_UNKNOWN** | MED | 合规标记不明 | 部分费用项的“是否符合政策”标记为未知，已自动排除在计算外。 | 请核实该项是否属于政策支持的范畴。 | AUDIT | 政策原文 |
| **WORK_STARTED_UNKNOWN** | MED | 施工状态不详 | “是否已开工”回答为未知，系统采取保守拒绝策略。 | 请明确勾选施工状态。 | BOTH | 开工告知单 |
| **MISSING_APPLICATION_EVENT** | HIGH | 缺少申请日期 | 时间轴中未找到申请提交事件，无法进行时间合规审计。 | 请在时间轴中增加“提交申请”事件。 | AUDIT | 申请官网截图 |
| **CONDITIONAL_CLAUSE_UNKNOWN**| MED | 合同条款不详 | 合同是否包含“以获得补助为准”的条件条款未知，影响早期签约的合规判定。 | 请核实合同中是否有补助相关免责条款。 | AUDIT | 完整版合同 |
| **APPLICANT_TYPE_MISMATCH** | HIGH | 申请人身份不符 | 申请人身份类型不符合政策要求的“私人住宅”身份。 | 请核实申请人是否为个人身份。 | AUDIT | 身份证件 |
| **MEASURE_NOT_SUPPORTED** | HIGH | 改造项目暂不支持 | 提交的项目类型（如 工业光伏）不在当前政策支持范围内。 | 建议查询相关配套政策。 | BOTH | 项目说明书 |
| **EVIDENCE_MISSING** | MED | 缺少关键凭证 | 核心判定逻辑已通过，但未关联到实体证据（Evidence）。 | 请在附件库中上传相应文件引用。 | BOTH | 分类清单 |
| **CAP_REACHED** | LOW | 触及最高金额上限 | 您的符合条件的总额已超过政策规定的最高补助限额。 | 无须操作，系统已自动按上限计算。 | BOTH | N/A |

---

### UI 实现说明
- **颜色代码**:
  - `HIGH`: 红色 (#FF4D4F) - 对应 REJECTED / BLOCKED。
  - `MED`: 橙色 (#FFA940) - 对应 NEEDS_INPUT。
  - `LOW`: 蓝色 (#1890FF) - 对应 INFO / APPROVED 带有警告。
- **国际化**: 字典文件推荐以 JSON 形式动态加载到 Flash 工具，以支持未来语言扩展。
