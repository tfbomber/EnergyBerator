import streamlit as st
import json
from typing import Dict, Any

def json_to_white_talk(data: Dict[str, Any]) -> str:
    """Converts business-level JSON to plain language (white talk) summary."""
    try:
        case_id = data.get("case_id", "未知案例")
        applicant = data.get("applicant", {})
        measure = data.get("measure", {})
        timeline = data.get("timeline", {})
        costs = data.get("costs", {})

        lines = [f"### 📝 案例 {case_id} 业务核注报告 (白话版)"]
        
        # 1. 申请人画像
        app_desc = "申请人是"
        app_desc += "一名自然人" if applicant.get("is_private_person") else "企业/组织"
        app_desc += "，且" if applicant.get("is_resident_in_city") else "，非"
        app_desc += "本市居民。"
        if applicant.get("has_duessepass"):
            app_desc += " 持有 Düsseldorf Pass。"
        lines.append(f"**1. 申请人状况**: {app_desc}")

        # 2. 措施详情
        m_type = measure.get("type", "未知项目")
        m_started = "已开工" if measure.get("work_started") else "尚未开工"
        lines.append(f"**2. 申报项目**: 申报项目为 `{m_type}`，目前状态为 `{m_started}`。")

        # 3. 时间线关键点
        t_signed = timeline.get("contract_signed_date", "未提供")
        t_clause = "包含" if timeline.get("contract_has_conditional_clause") else "不包含"
        t_payment = "已支付" if timeline.get("down_payment_made") else "未支付"
        lines.append(f"**3. 时间线核查**: 合同签署于 `{t_signed}`，合同中 `{t_clause}` 解除条款。首付款 `{t_payment}`。")

        # 4. 费用明细
        total_eur = costs.get("eligible_cost_total_eur", 0)
        items = costs.get("items", [])
        lines.append(f"**4. 费用核算**: 合格费用总计 `{total_eur:.2f} EUR`。")
        for item in items:
            eligible = "✅ 合格" if item.get("eligible") else "❌ 不合格"
            lines.append(f"   - {item.get('label')}: {item.get('amount_eur'):.2f} EUR ({eligible})")

        return "\n\n".join(lines)
    except Exception as e:
        return f"❌ 解析 JSON 失败: {str(e)}"

def render_test_generator():
    st.markdown("### 🧪 测试用例快捷生成器")
    st.caption("支持业务级 JSON 与白话描述的双向转换，方便快速测试策略。")

    tab1, tab2 = st.tabs(["JSON ➔ 白话 (提炼)", "白话 ➔ JSON (生成)"])

    with tab1:
        json_input = st.text_area("粘贴业务级 JSON", height=300, placeholder='{"case_id": "...", ...}')
        if st.button("开始提炼白话文本"):
            if json_input:
                try:
                    data = json.loads(json_input)
                    summary = json_to_white_talk(data)
                    st.success("提炼成功！")
                    st.markdown("---")
                    st.markdown(summary)
                except json.JSONDecodeError:
                    st.error("无效的 JSON 格式，请检查。")
            else:
                st.warning("请先输入 JSON 数据。")

    with tab2:
        st.info("💡 请直接详细描述您的案例背景（如：申请人身份、签约时间、费用金额等）。")
        text_input = st.text_area("输入白话描述", height=200, placeholder="例如：我是杜塞居民，昨天签了1200块的阳台光伏合同，还没付钱...")
        
        if st.button("AI 生成业务 JSON"):
            if text_input:
                st.info("正在调用 LLM 引擎提取结构化数据...")
                # 在真实环境下，这里会调用一个内部 API 或者提示用户将此段发给 Antigravity
                st.warning("⚠️ 提示：在当前 Demo 版本中，请将上述描述直接发送给 Antigravity AI 助手，它将为您生成符合规范的 JSON。")
                # 预填充一个模版供参考
                st.code("""
{
  "case_id": "new_case_001",
  "as_of": "2026-02-28",
  "policy_id": "dus_balcony_pv",
  "applicant": { ... },
  ...
}
                """, language="json")
            else:
                st.warning("请先输入白话描述。")

if __name__ == "__main__":
    # Simple standalone check
    pass
