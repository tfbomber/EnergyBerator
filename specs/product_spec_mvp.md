# D-ESS MVP Product Specification: Agentic Canvas

## 1. 产品价值 (Value Proposition)
**"D-ESS 帮你在不踩资格红线的前提下，找到可执行的最优补贴路径，并把申请顺序和证据链一次性做对。"**

- **对客户 (B2C)**：多拿补贴、避免掉坑、不用自己啃 PDF、每个数字都有证据。
- **对安装商/顾问 (B2B2C)**：缩短成交周期、降低解释成本与返工风险、提供专业交付背书。
- **系统降维打击**：从“泛聊天的 AI”升级为“能源补贴执行操作系统”。

## 2. 使用逻辑 (Usage Logic)
以**“项目驱动”**取代“对话驱动”。
1. **Quick Scan (初筛)**: NLP 输入 -> 风险提示 -> 建立项目。
2. **Data Ingestion (填弹)**: 拖拽/上传报价单 -> OCR抽取 -> 人工确认状态。
3. **Plan Generation (方案计算)**: 引擎过状态机 -> 输出 Plan A/B/C。
4. **Execution Nav (执行导航)**: 给出具体的时间线和红线动作。
5. **Contextual Copilot**: 在上下文框架内的防呆问答。
6. **Report Handoff**: 导出客户级视图 + 审计级试图。

## 3. UI 布局：Agentic Canvas (三大视窗)

### 3.1 顶部状态栏 (State Bar)
核心功能：项目的“心电图”。
- **State Tracker**: S0 (意向) -> S1 (准备) -> S2 (申请中) -> S3 (批复) -> S4 (签约) -> S5 (开工)。
- **Compliance Lights**: 绿（安全）/ 黄（有缺失）/ 红（踩雷）。
- **Project Completeness**: 资料收集百分比。

### 3.2 左侧导航栏 (Navigator)
核心功能：项目的“任务树/骨架”。
- 项目概览 | 房屋信息 | 项目类型 | 合同收纳
- 自动生成的补贴锚点分支 (e.g., KfW 458, Düsseldorf PV)
- 输出模块：合规时间线 | 报告与导出

### 3.3 中间智能画布 (Canvas)
核心功能：随 S0-S5 状态**动态变化**的工作台。
- **前期 (S0-S1)**: 资料上传区、自动抽取结果核对卡、缺失信息追问卡。
- **中期 (S2-S3)**: Plan A/B/C 对比卡、红线动作阻断卡、待办清单。
- **后期 (S4-S5)**: 合同合规审查结果、最终开工白名单指令。

### 3.4 右侧审查器 (Inspector) - The Killer Feature
核心功能：“为什么是这个结果”的终极解释。
联动的证据面板：点击 Canvas 里的任何数字、风险预警，Inspector 将滑出并展示：
- 适用条件判断原由。
- 官方来源 URL、生效日期。
- **极其精确的页码/段落锚点文本**（来自 `evidence_index.json`）。

### 3.5 底部对话框 (Copilot)
核心功能：上下文感知的现场指挥。
不是瞎聊，而是绑定当前 State，回答“我今天能签合同吗？”这类硬核合规问题。

---
*(Specification frozen based on User Blueprint V1.0)* 
