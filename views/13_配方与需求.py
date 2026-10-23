"""配方与物料需求页面（交叉模块的入口）。

页面只做三件事：展示、收集输入、调用业务服务。**不写任何业务规则**——
不算分子量、不判库存、不拼 SQL。这样同一个用例也能被脚本、定时任务或
将来的科研端复用。

页面结构对应四条用例：
1. 配方库    —— 看有哪些方案、是否通过校验
2. 配方编制  —— 录入组分与计量方式
3. 需求试算  —— 配方 × 规模 → 需求 / 缺口 / 采购建议（不落库）
4. 领用单据  —— 落库后的需求单与流转状态
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st

from components.auth import get_current_user, require_auth
from components.sidebar_nav import render_sidebar
from business.manager_service import manager_service
from business.material_pipeline_service import material_pipeline_service
from business.recipe_service import recipe_business_service
from business.requirement_issue_service import requirement_issue_service
from business.requirement_service import requirement_business_service
from domain.substance import ComponentRole
from services.custodian_route import (
    SCOPE_COURSE,
    SCOPE_DEPARTMENT,
    SCOPE_LABELS,
    custodian_route_repository,
)
from utils.field_mapper import RequirementSheetField

st.set_page_config(page_title="配方与需求", layout="wide")

if not require_auth():
    st.stop()

render_sidebar()

st.title("🧪 配方与物料需求")
st.caption(
    "实验方案只声明「用什么、用多少」，系统据此算需求、对库存、出采购建议、发领用单。"
    "教学实验与科研项目共用同一套配方，区别只在来源标注。"
)

current_user = get_current_user() or ""
ROLE_LABELS = {
    "reactant": "反应物",
    "reagent": "试剂",
    "solvent": "溶剂",
    "catalyst": "催化剂",
    "indicator": "指示剂",
    "consumable": "耗材",
    "product": "产物",
}
AMOUNT_LABELS = {
    "per_person": "人均量",
    "per_batch": "每批量",
    "fixed": "每批固定",
    "equivalents": "当量",
    "ratio": "基准倍数",
    "concentration": "浓度",
}

tab_lib, tab_edit, tab_plan, tab_ticket, tab_pipe = st.tabs(
    ["📚 配方库", "✍️ 配方编制", "🧮 需求试算", "📄 需求量与单据", "🔀 申领流转"]
)

# ==========================================================================
# 1. 配方库
# ==========================================================================
with tab_lib:
    listed = recipe_business_service.list_recipes()
    if not listed.success:
        st.error(listed.message)
    elif not listed.data["items"]:
        st.info("还没有配方。切到「配方编制」录入第一张。")
    else:
        frame = pd.DataFrame(
            [
                {
                    "配方键": item["key"],
                    "标题": item["title"],
                    "版本": item["version"],
                    "状态": item["status_label"],
                    "来源": item["source"],
                    "备料项": item["material_count"],
                    "校验": "通过" if item["is_valid"] else f"{item['issue_count']} 个问题",
                }
                for item in listed.data["items"]
            ]
        )
        st.dataframe(frame, use_container_width=True, hide_index=True)

        options = [item["key"] for item in listed.data["items"]]
        picked = st.selectbox(
            "查看配方明细",
            options,
            format_func=lambda key: next(
                (i["title"] for i in listed.data["items"] if i["key"] == key), key
            ),
            key="recipe_pick",
        )
        if picked:
            st.session_state["active_recipe"] = picked
            detail = recipe_business_service.get_recipe(picked)
            if detail.success:
                data = detail.data
                col1, col2, col3 = st.columns(3)
                col1.metric("版本", f"v{data['detail']['version']}")
                col2.metric("状态", data["detail"]["status_label"])
                col3.metric("组分", len(data["detail"]["components"]))

                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "序": c["seq"] + 1,
                                "物质": c["name"],
                                "CAS": c["cas"],
                                "分子式": c["formula"],
                                "角色": c["role_label"],
                                "计量": c["amount"],
                                "系数": c["coefficient"],
                            }
                            for c in data["detail"]["components"]
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

                validation = data["validation"]
                if validation.is_valid:
                    st.success(f"校验通过：{validation.summary()}")
                else:
                    st.error(f"校验未通过：{validation.errors[0]}")
                for issue in validation.issues:
                    st.caption(f"· {issue}")

# ==========================================================================
# 2. 配方编制
# ==========================================================================
with tab_edit:
    st.markdown("##### 录入一张配方")
    st.caption(
        "计量方式：人均量按「人数 × 批次」放大；当量以限制试剂为 1.00；"
        "基准倍数是基准组分用量的倍数（如溶剂取 3 倍体积）；浓度需配合容器体积。"
    )

    default_rows = pd.DataFrame(
        [
            {"名称": "水杨酸", "CAS": "69-72-7", "分子式": "C7H6O3", "角色": "reactant",
             "计量方式": "per_person", "数值": 2.0, "单位": "g", "系数": 1.0},
            {"名称": "乙酸酐", "CAS": "108-24-7", "分子式": "C4H6O3", "角色": "reactant",
             "计量方式": "equivalents", "数值": 2.5, "单位": "g", "系数": 1.0},
        ]
    )

    with st.form("recipe_form"):
        col1, col2, col3 = st.columns([1.2, 1.6, 1])
        recipe_key = col1.text_input("配方键", placeholder="teach:aspirin")
        title = col2.text_input("标题", placeholder="乙酰水杨酸制备")
        source_kind = col3.selectbox(
            "来源", ["teaching", "research", "manual"],
            format_func=lambda k: {"teaching": "教学", "research": "科研", "manual": "手工"}[k],
        )

        source_code = st.text_input("来源编码（课程/实验名或项目编号）", placeholder="有机化学实验/实验三")
        note = st.text_input("备注", placeholder="可选")

        st.markdown("**组分明细**（可直接增删行）")
        edited = st.data_editor(
            default_rows,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "角色": st.column_config.SelectboxColumn(
                    "角色", options=list(ROLE_LABELS.keys()), required=True
                ),
                "计量方式": st.column_config.SelectboxColumn(
                    "计量方式", options=list(AMOUNT_LABELS.keys()), required=True
                ),
                "数值": st.column_config.NumberColumn("数值", format="%.4f"),
                "系数": st.column_config.NumberColumn("系数", format="%.3f", default=1.0),
            },
            key="components_editor",
        )

        saved = st.form_submit_button("保存配方", type="primary")
        if saved:
            components = []
            for index, row in edited.iterrows():
                name = str(row.get("名称") or "").strip()
                if not name:
                    continue
                components.append(
                    {
                        "substance": {
                            "name": name,
                            "cas": str(row.get("CAS") or "").strip(),
                            "formula": str(row.get("分子式") or "").strip(),
                        },
                        "role": row.get("角色") or "reagent",
                        "amount": {
                            "amount_type": row.get("计量方式") or "per_person",
                            "amount_value": float(row.get("数值") or 0),
                            "amount_unit": str(row.get("单位") or "g").strip() or "g",
                        },
                        "coefficient": float(row.get("系数") or 1),
                        "seq": index,
                    }
                )

            payload = {
                "key": recipe_key.strip(),
                "title": title.strip(),
                "note": note.strip(),
                "source": {
                    "kind": source_kind,
                    "code": source_code.strip(),
                    "title": title.strip(),
                },
                "components": components,
            }
            result = recipe_business_service.save_recipe(payload, operator=current_user)
            if result.success:
                st.success(result.message)
                st.session_state["active_recipe"] = result.data["recipe"].key
            else:
                st.error(result.message)
                for issue in (result.data or {}).get("issues", []):
                    st.caption(f"· {issue['message']}")

# ==========================================================================
# 3. 需求试算
# ==========================================================================
with tab_plan:
    listed = recipe_business_service.list_recipes()
    keys = [item["key"] for item in listed.data["items"]] if listed.success else []
    if not keys:
        st.info("还没有配方，先去「配方编制」建一张。")
    else:
        active = st.session_state.get("active_recipe") or keys[0]
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1.4])
        chosen = col1.selectbox(
            "配方", keys, index=keys.index(active) if active in keys else 0,
            format_func=lambda key: next(
                (i["title"] for i in listed.data["items"] if i["key"] == key), key
            ),
        )
        persons = col2.number_input("人数", min_value=1, value=12, step=1)
        batches = col3.number_input("批次", min_value=1, value=1, step=1)
        policy = col4.selectbox(
            "可用量口径", ["standard", "strict"],
            format_func=lambda p: {"standard": "标准（未过期即可）",
                                   "strict": "严格（效期余量 30 天）"}[p],
        )

        if st.button("试算需求", type="primary"):
            result = requirement_business_service.preview(
                chosen, {"persons": int(persons), "batches": int(batches)}, policy
            )
            if not result.success:
                st.error(result.message)
            else:
                st.session_state["plan_preview"] = result.data

        preview = st.session_state.get("plan_preview")
        if preview and preview.get("recipe_key") == chosen:
            st.markdown(f"##### {preview['title']} · {preview['scale']}")
            st.caption(preview["summary"])

            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "序": line["seq"] + 1,
                            "物质": line["name"],
                            "角色": line["role_label"],
                            "需求": line["quantity"],
                            "可用": line["available"],
                            "缺口": line["gap"],
                            "覆盖率": f"{line['coverage_ratio'] * 100:.0f}%",
                            "受管控": "是" if line["controlled"] else "",
                            "计算依据": line["explanation"],
                        }
                        for line in preview["lines"]
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )

            if preview["is_fulfillable"]:
                st.success("现有库存可满足全部需求")
            else:
                st.warning(preview["coverage_summary"])

            if preview["proposal"]:
                st.markdown("##### 采购建议")
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "物质": row["name"],
                                "缺口": row["gap"],
                                "包装": row["pack_size"],
                                "包数": row["packs"],
                                "供应商": row["supplier"],
                                "金额": row["cost"] if row["cost"] is not None else "待询价",
                                "说明": row["note"],
                            }
                            for row in preview["proposal"]
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
                st.caption(preview["proposal_summary"])

            for warning in preview["warnings"]:
                st.caption(f"提示：{warning}")

            col_a, col_b = st.columns([1, 3])
            if col_a.button("生成需求单", type="secondary"):
                created = requirement_business_service.create_sheet(
                    chosen,
                    {"persons": int(persons), "batches": int(batches)},
                    requester=current_user,
                    policy_name=policy,
                )
                if created.success:
                    st.success(created.message)
                    st.session_state["last_sheet"] = created.data["sheet_number"]
                else:
                    st.error(created.message)

# ==========================================================================
# 4. 需求量与单据
# ==========================================================================
with tab_ticket:
    st.markdown("##### 最近的需求单")
    recent = requirement_business_service.recent_sheets(30)
    if recent.success and recent.data["items"]:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "单据号": row["sheet_number"],
                        "标题": row["title"],
                        "配方": row["recipe_key"],
                        "申请人": row["requester"],
                        "人数": row["persons"],
                        "批次": row["batches"],
                        "生成时间": row["created_at"],
                    }
                    for row in recent.data["items"]
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

        picked_sheet = st.selectbox(
            "查看单据明细",
            [row["sheet_number"] for row in recent.data["items"]],
            key="sheet_pick",
        )
        if picked_sheet:
            detail = requirement_business_service.get_sheet(picked_sheet)
            if detail.success:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "序": line["seq"] + 1,
                                "物质": line["name"],
                                "数量": f"{line['quantity']} {line['unit']}",
                                "依据": line["basis"],
                                "受管控": "是" if line["controlled"] else "",
                            }
                            for line in detail.data["lines"]
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
    else:
        st.info("还没有需求单。先在「需求试算」里生成一张。")

    st.markdown("##### 未完结领用单据")
    tickets = requirement_business_service.open_tickets()
    if tickets.success and tickets.data["items"]:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "单据号": item["ticket_no"],
                        "标题": item["title"],
                        "申请人": item["requester"],
                        "状态": item["status_label"],
                        "项数": item["line_count"],
                        "提交时间": item["created_at"],
                    }
                    for item in tickets.data["items"]
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("当前没有未完结单据（内存网关在重启后清空，接入数据库网关后持久保留）。")


# ==========================================================================
# 5. 申领流转（两段管线）
#
# 这一页不显示"流程状态"，而是显示"谁该办、办到哪一步"：
#   - 保管账：谁名下有什么（教师看这个才知道该找谁）
#   - 第一段：受理人 + 实发 + 缺口
#   - 第二段：从谁那调多少
# ==========================================================================
with tab_pipe:
    st.markdown("##### 保管账：这批料在谁名下")
    summary = material_pipeline_service.custody_summary()
    if summary.success:
        info = summary.data
        st.caption(f"{info['ledger_text']} ｜ 路由：{info['router_text']}")
        if info["rows"]:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "保管人": row["custodian"],
                            "科室": row["department"],
                            "物质": row["substance"],
                            "CAS": row["cas"],
                            "持有量": f"{row['quantity_text']}",
                            "瓶数": row["lots"],
                        }
                        for row in info["rows"]
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("库存里还没有记在具体管理员名下的瓶子。请先在「试剂管理」里指定管理人。")
        if info["unclaimed"]:
            st.warning(
                "以下物质有未指定保管人的批次，谁都调不到，需先认领："
                + "、".join(info["unclaimed"])
            )

    with st.expander("配置受理人：这门课归谁管"):
        st.caption(
            "第一段的受理人是**指派**的，不是按库存优先级挑的。不配这条规则，"
            "系统会直接拒绝受理，而不是随便找个人。"
        )
        col_scope, col_key, col_who = st.columns([1, 1.4, 1.2])
        scope_label = col_scope.selectbox(
            "维度", list(SCOPE_LABELS.values()), key="route_scope_label"
        )
        scope_type = {v: k for k, v in SCOPE_LABELS.items()}[scope_label]
        scope_key = col_key.text_input(
            "匹配键",
            placeholder="课程名，或「课程/班级」；科室维度填科室名",
            key="route_scope_key",
        )
        candidates = manager_service.get_candidates()
        options = candidates.data if candidates.success else []
        custodian_name = col_who.selectbox(
            "受理管理员", options or [current_user], key="route_custodian"
        )
        if st.button("保存这条路由", key="route_save"):
            if not scope_key.strip():
                st.error("匹配键不能为空")
            else:
                try:
                    custodian_route_repository.upsert(
                        scope_type, scope_key.strip(), custodian_name
                    )
                    st.success(f"已配置：{scope_label}「{scope_key}」→ {custodian_name}")
                    st.rerun()
                except Exception as exc:  # 配置错误要原样显示，不要吞掉
                    st.error(f"保存失败：{exc}")

        if not custodian_route_repository.table_ready():
            st.warning("路由表尚未创建，请重启应用（启动脚本会幂等建表）。")
        existing = custodian_route_repository.rows()
        if existing:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "维度": SCOPE_LABELS.get(row["scope_type"], row["scope_type"]),
                            "匹配键": row["scope_key"] or "（默认）",
                            "受理管理员": row["custodian"],
                            "备注": row.get("remark") or "",
                        }
                        for row in existing
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )

    st.divider()

    # ---------------------------------------------------------------- 第一段
    st.markdown("##### 第一段：受理（只报受理人名下够不够）")
    recent = requirement_business_service.recent_sheets(30)
    items = recent.data["items"] if recent.success else []
    if not items:
        st.info("还没有需求单。请先在「需求试算」里算一张并落库。")
    else:
        col_sheet, col_due = st.columns([2, 1])
        picked = col_sheet.selectbox(
            "选一张需求单", [row["sheet_number"] for row in items], key="pipe_sheet"
        )
        due = col_due.text_input("用途时间（可选）", placeholder="周三下午", key="pipe_due")

        detail = requirement_business_service.get_sheet(picked) if picked else None
        sheet_obj = detail.data["sheet"] if detail and detail.success else None

        if sheet_obj is not None:
            requester_default = detail.data.get("requester") or current_user
            requester = st.text_input("申请人（教师）", value=requester_default, key="pipe_requester")

            if st.button("受理这张申请", type="primary", key="pipe_intake"):
                result = material_pipeline_service.intake(
                    requester=requester,
                    sheet=sheet_obj,
                    source=sheet_obj.source,
                    due_hint=due,
                )
                if result.success:
                    st.session_state["pipe_acceptance"] = result.data["acceptance"]
                    st.session_state["pipe_acceptance_sheet"] = picked
                    st.session_state.pop("pipe_proposal", None)
                else:
                    st.error(result.message)

        acceptance = st.session_state.get("pipe_acceptance")
        if acceptance is not None and sheet_obj is not None:
            if acceptance.request.sheet.recipe_key != sheet_obj.recipe_key:
                st.caption("（下面是上一次受理的结论，换单据后请重新受理）")

            st.success(acceptance.describe())
            issued = [
                {
                    "序": line.seq + 1,
                    "物质": line.name,
                    "实发": line.quantity.format(3),
                    "瓶号": line.lot_id or "现场指定",
                }
                for line in acceptance.issued
            ]
            shortfalls = [
                {
                    "物质": item.name,
                    "缺口": item.quantity.format(3),
                    "原因": item.reason,
                }
                for item in acceptance.shortfalls
            ]
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**实发 {len(issued)} 项**（保管权不变）")
                st.dataframe(pd.DataFrame(issued) if issued else pd.DataFrame(), use_container_width=True, hide_index=True)
            with col_b:
                st.markdown(f"**缺口 {len(shortfalls)} 项**（进第二段）")
                st.dataframe(pd.DataFrame(shortfalls) if shortfalls else pd.DataFrame(), use_container_width=True, hide_index=True)

            for note in acceptance.notes:
                st.caption(f"· {note}")

            # ------------------------------------------------------------ 转单
            st.markdown("##### 转借出单：借出即兑付")
            sheet_row = requirement_issue_service.sheets.get_by_number(picked) or {}
            already = (sheet_row.get(RequirementSheetField.ORDER_NUMBER) or "").strip()
            accepted_sheet = st.session_state.get("pipe_acceptance_sheet")
            if accepted_sheet and accepted_sheet != picked:
                st.caption("上面的受理结论属于另一张单。换单后请重新受理，再转借出单。")
            elif already:
                st.success(f"这张需求单已兑付，借出单 {already}；不再占用学年保底。")
            elif not acceptance.issued:
                st.info("受理结论里没有可发的料，无从转单；缺口请走第二段或采购。")
            else:
                st.caption(
                    "转单会逐瓶扣库存、生成一张借出单（一单多瓶），并把需求单置为"
                    "「已兑付」。兑付之后，这张单不再占本学年保底——否则同一门课"
                    "第二周再申领，会被自己上一张单压住。"
                )
                if st.button("签发借出单（借出即兑付）", type="primary", key="pipe_issue"):
                    drafted = requirement_issue_service.issue(picked, acceptance, current_user)
                    if drafted.success:
                        st.success(drafted.message)
                        for key in ("pipe_acceptance", "pipe_acceptance_sheet", "pipe_proposal"):
                            st.session_state.pop(key, None)
                        st.rerun()
                    else:
                        st.error(drafted.message)

            # ------------------------------------------------------------ 第二段
            if acceptance.is_complete:
                st.info("受理人名下就够，不需要第二段。")
            else:
                st.markdown("##### 第二段：平账（缺料的管理员去找别人调）")
                st.caption(
                    f"申报人已从「{acceptance.request.requester_name}」换成受理人"
                    f"「{acceptance.custodian.name}」——这一段动的是保管权。"
                )
                if st.button("算一算该找谁调", key="pipe_settle"):
                    settled = material_pipeline_service.settle(acceptance)
                    if settled.success:
                        st.session_state["pipe_proposal"] = settled.data["proposal"]
                    else:
                        st.error(settled.message)

                proposal = st.session_state.get("pipe_proposal")
                if proposal is not None:
                    if proposal.lines:
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "从谁": line.from_custodian.name,
                                        "到谁": line.to_custodian.name,
                                        "物质": line.name,
                                        "数量": line.quantity.format(3),
                                        "瓶号": line.lot_id or "现场指定",
                                        "关系": ("同科室" if line.from_custodian.in_department_of(line.to_custodian) else "跨科室"),
                                    }
                                    for line in proposal.lines
                                ]
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.info("其他管理员名下也没有可调的量。")

                    if proposal.unresolved:
                        st.warning(
                            "以下缺口全院都调不到，需转采购："
                            + "；".join(item.describe() for item in proposal.unresolved)
                        )

                    if proposal.lines:
                        if st.button("执行调拨（转保管权）", key="pipe_commit"):
                            committed = material_pipeline_service.commit_transfers(
                                proposal, current_user, note=acceptance.request.sheet.recipe_key
                            )
                            if committed.success:
                                st.success(committed.message)
                                st.session_state.pop("pipe_proposal", None)
                            else:
                                st.error(committed.message)
                        st.caption(
                            "执行后瓶子不会移动，变的是「算谁名下」——"
                            "变更会写入管理人变更记录，可追溯。"
                        )

    if st.checkbox("查看上一轮的完整推导", key="pipe_trace"):
        acceptance = st.session_state.get("pipe_acceptance")
        if acceptance is not None:
            for row in acceptance.explain():
                st.text(row)
            proposal = st.session_state.get("pipe_proposal")
            if proposal is not None:
                for row in proposal.explain():
                    st.text(row)
