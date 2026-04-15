from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import streamlit as st

from app.config import get_settings
from app.orchestrator import NL2SQLOrchestrator
from core.local_db_assets import LOCAL_DATABASE_DIR, build_local_database_assets, delete_local_database_assets, ensure_local_database_assets, list_local_database_files, rebuild_all_local_database_assets, refresh_database_assets
from core.models import NL2SQLResponse, OPERATION_MODE_DDL, OPERATION_MODE_DML, StageUpdate
from core.schema_loader import clear_schema_loader_caches, load_schema_catalog, load_schema_document


DEFAULT_DATABASE_OPTION = "-- 使用默认 Chinook 数据库 --"
DEFAULT_UI_OPERATION_MODE = OPERATION_MODE_DML
OPERATION_MODE_LABELS = {
    OPERATION_MODE_DML: "DML",
    OPERATION_MODE_DDL: "DDL",
}
LABEL_TO_OPERATION_MODE = {label: mode for mode, label in OPERATION_MODE_LABELS.items()}


def render_app() -> None:
    st.set_page_config(page_title="NL2SQL Agent", page_icon="🧭", layout="wide")
    _init_session_state()
    settings = _resolve_active_settings(get_settings())
    _sync_database_context(settings)
    _inject_custom_styles()
    operation_mode = _render_operation_mode_selector(Path(settings.database_path).stem)

    st.title("NL2SQL Agent")
    st.caption("输入自然语言描述，系统会按当前模式完成分析、生成 SQL、校验并执行。")
    st.markdown(_render_context_badges(Path(settings.database_path).stem, operation_mode), unsafe_allow_html=True)

    chat_col, detail_col = st.columns([2.2, 1.0], gap="large")

    with chat_col:
        _render_chat_history()
        orchestrator = NL2SQLOrchestrator(settings)

        user_question = st.chat_input(_build_chat_input_placeholder(operation_mode))
        if user_question:
            _handle_user_question(orchestrator, user_question, operation_mode)
            st.rerun()

    with detail_col:
        _render_detail_panel(settings, operation_mode)


def _handle_user_question(orchestrator: NL2SQLOrchestrator, question: str, operation_mode: str) -> None:
    st.session_state["chat_history"].append({"role": "user", "content": question})
    response: NL2SQLResponse | None = None

    with st.chat_message("assistant"):
        stage_placeholder = st.empty()
        stage_updates: list[StageUpdate] = []
        for event_type, payload in orchestrator.answer_question_stream(question, operation_mode=operation_mode):
            if event_type == "stage":
                assert isinstance(payload, StageUpdate)
                stage_updates.append(payload)
                stage_placeholder.markdown(
                    _render_stage_bubbles(stage_updates, highlight_latest=True),
                    unsafe_allow_html=True,
                )
                continue

            assert isinstance(payload, NL2SQLResponse)
            response = payload

        stage_placeholder.empty()
        if response is not None:
            st.markdown(_format_assistant_message(response))
            if _should_render_result_table(response):
                result_frame = pd.DataFrame(
                    list(response.execution.rows),
                    columns=list(response.execution.columns),
                )
                st.dataframe(result_frame, width="stretch")

    if response is None:
        raise RuntimeError("UI did not receive a final NL2SQL response")

    _refresh_current_database_summary(orchestrator, response)
    st.session_state["latest_response"] = response
    st.session_state["chat_history"].append(
        {
            "role": "assistant",
            "content": _format_assistant_message(response),
            "response": response,
        }
    )


def _render_chat_history() -> None:
    for message in st.session_state["chat_history"]:
        with st.chat_message(message["role"]):
            response = message.get("response")
            if response is not None and response.stage_updates:
                st.markdown(_render_stage_bubbles(list(response.stage_updates)), unsafe_allow_html=True)

            st.markdown(message["content"])
            if response is None or not _should_render_result_table(response):
                continue

            result_frame = pd.DataFrame(
                list(response.execution.rows),
                columns=list(response.execution.columns),
            )
            st.dataframe(result_frame, width="stretch")


def _render_detail_panel(settings, operation_mode: str) -> None:
    response: NL2SQLResponse | None = st.session_state.get("latest_response")
    schema_document = load_schema_document(settings.schema_metadata_path)
    schema_catalog = load_schema_catalog(settings.schema_metadata_path, settings.semantic_layer_path)
    database_name = Path(settings.database_path).stem
    database_description = str(schema_document.get("description") or "")

    with st.container(border=True):
        st.subheader("执行详情")
        st.caption("SQL 与 agent 细节默认收起，仅在需要排查时展开。")

        llm_status = "已启用" if settings.llm_api_key and settings.llm_model else "未配置，当前走本地回退"
        st.write("LLM 状态：", llm_status)
        st.write("当前模式：", OPERATION_MODE_LABELS.get(operation_mode, operation_mode.upper()))

        with st.expander("数据资源", expanded=False):
            _render_database_resource_panel(settings)

            st.write(f"Schema Metadata: {Path(settings.schema_metadata_path).name}")
            st.write(f"语义映射: {Path(settings.semantic_layer_path).name}")
            st.write(f"演示样例: {Path(settings.demo_questions_path).name}")

        if st.button("查看当前库表结构摘要", use_container_width=True):
            _show_schema_summary_dialog(database_name, schema_catalog, database_description)

        if response is None:
            with st.expander("使用建议", expanded=True):
                st.write("可以直接输入自然语言描述，例如：")
                for example in _build_mode_examples(operation_mode):
                    st.write(f"- {example}")
            return

        with st.expander("问题分析", expanded=False):
            st.write("关键词:", list(response.pipeline.analysis.tokens))
            st.write("意图标签:", list(response.pipeline.analysis.intent_tags))
            st.write("指标提示:", list(response.pipeline.analysis.metric_hints))
            st.write("实体提示:", list(response.pipeline.analysis.entity_hints))
            st.write("模糊词:", list(response.pipeline.analysis.ambiguous_terms))
            st.write("时间粒度:", response.pipeline.analysis.time_grain or "无")
            st.write("Top-K:", response.pipeline.analysis.top_k or "无")

        with st.expander("Thinking 语义解释", expanded=False):
            if response.semantic_interpretation is None:
                st.write("本次没有触发 thinking 语义解释。")
            else:
                st.write("改写后问题:", response.semantic_interpretation.rewritten_question)
                st.write("解析指标:", response.semantic_interpretation.resolved_metric or "无")
                st.write("解析实体:", response.semantic_interpretation.resolved_entity or "无")
                st.write("置信度:", response.semantic_interpretation.confidence)
                st.write("假设:", list(response.semantic_interpretation.assumptions) or ["无"])

        with st.expander("Schema 命中", expanded=False):
            if not response.pipeline.retrievals:
                st.write("当前没有召回到高相关表。")
            for hit in response.pipeline.retrievals:
                st.markdown(f"**{hit.table_name}** | 分数 {hit.score}")
                st.write("命中词:", list(hit.matched_terms))
                st.write("原因:", list(hit.reasons))

        with st.expander("SQL 生成与校验", expanded=False):
            if response.draft is not None:
                st.write("生成来源:", response.draft.source)
                st.caption(response.draft.rationale)
                st.code(response.draft.sql, language="sql")
            else:
                st.write("当前未生成 SQL。")

            st.write("操作模式:", OPERATION_MODE_LABELS.get(response.operation_mode, response.operation_mode.upper()))
            if response.validation.statement_type:
                st.write("语句类型:", response.validation.statement_type)
            st.write("校验结果:", response.validation.message)
            if response.final_sql:
                st.write("最终 SQL:")
                st.code(response.final_sql, language="sql")

        with st.expander("自动修复记录", expanded=False):
            if not response.repairs:
                st.write("本次没有触发自动修复。")
            for repair in response.repairs:
                st.caption(repair.reason)
                st.write("修复前")
                st.code(repair.sql_before or "<empty>", language="sql")
                st.write("修复后")
                st.code(repair.sql_after, language="sql")

        with st.expander("Agent Trace", expanded=False):
            for trace in response.agent_traces:
                st.markdown(f"**{trace.agent_name}** | {trace.strategy}")
                st.caption(trace.detail)

        with st.expander("Prompt", expanded=False):
            if response.prompt:
                st.code(response.prompt, language="text")
            else:
                st.write("当前没有 prompt。")


def _init_session_state() -> None:
    st.session_state.setdefault(
        "chat_history",
        [
            {
                "role": "assistant",
                "content": _build_welcome_message("Chinook", DEFAULT_UI_OPERATION_MODE),
            }
        ],
    )
    st.session_state.setdefault("latest_response", None)
    st.session_state.setdefault("selected_database", None)
    st.session_state.setdefault("active_database_name", None)
    st.session_state.setdefault("operation_mode", DEFAULT_UI_OPERATION_MODE)
    st.session_state.setdefault("active_operation_mode", DEFAULT_UI_OPERATION_MODE)


def _format_assistant_message(response: NL2SQLResponse) -> str:
    sections = [response.answer_text.strip() or "当前没有可展示的回答。"]
    if response.final_sql:
        sections.append(f"最终 SQL：\n```sql\n{response.final_sql}\n```")
    return "\n\n".join(sections)


def _inject_custom_styles() -> None:
    st.markdown(
        """
        <style>
        .context-badge-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.7rem;
            margin: 0.25rem 0 1rem 0;
        }
        .stage-bubble-stack {
            display: flex;
            flex-direction: column;
            gap: 0.55rem;
            margin: 0.25rem 0 0.9rem 0;
        }
        .stage-bubble {
            max-width: 92%;
            background: linear-gradient(135deg, #fff7ed 0%, #fffbeb 100%);
            border: 1px solid #f59e0b;
            border-radius: 16px 16px 16px 6px;
            padding: 0.75rem 0.9rem;
            box-shadow: 0 8px 20px rgba(245, 158, 11, 0.08);
        }
        .stage-bubble.is-latest {
            background: linear-gradient(135deg, #fef3c7 0%, #fff7ed 100%);
            border-color: #ea580c;
            box-shadow: 0 10px 24px rgba(234, 88, 12, 0.14);
        }
        .stage-bubble-title {
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: #9a3412;
            margin-bottom: 0.3rem;
        }
        .stage-bubble-text {
            color: #431407;
            line-height: 1.45;
            font-size: 0.95rem;
        }
        .database-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.7rem;
            padding: 0.45rem 0.7rem;
            border-radius: 999px;
            background: linear-gradient(135deg, #ecfccb 0%, #fef3c7 100%);
            border: 1px solid #84cc16;
            box-shadow: 0 10px 24px rgba(101, 163, 13, 0.12);
        }
        .database-badge-label {
            font-size: 0.78rem;
            font-weight: 700;
            color: #3f6212;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .database-badge-name {
            font-size: 0.98rem;
            font-weight: 700;
            color: #1f2937;
        }
        .mode-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.7rem;
            padding: 0.45rem 0.7rem;
            border-radius: 999px;
            border: 1px solid #2563eb;
            box-shadow: 0 10px 24px rgba(37, 99, 235, 0.12);
            background: linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%);
        }
        .mode-badge.is-ddl {
            border-color: #dc2626;
            box-shadow: 0 10px 24px rgba(220, 38, 38, 0.12);
            background: linear-gradient(135deg, #fee2e2 0%, #fff1f2 100%);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_stage_bubbles(updates: list[StageUpdate], highlight_latest: bool = False) -> str:
    if not updates:
        return ""

    parts = ['<div class="stage-bubble-stack">']
    for index, update in enumerate(updates, start=1):
        latest_class = " is-latest" if highlight_latest and index == len(updates) else ""
        title = _stage_title(update.stage, index)
        parts.append(
            f'<div class="stage-bubble{latest_class}">'
            f'<div class="stage-bubble-title">{title}</div>'
            f'<div class="stage-bubble-text">{update.message}</div>'
            '</div>'
        )
    parts.append("</div>")
    return "".join(parts)


def _stage_title(stage: str, index: int) -> str:
    labels = {
        "analysis": "阶段 1 · 问题分析",
        "thinking": "阶段 2 · 语义澄清",
        "retrieval_refresh": "阶段 3 · 召回刷新",
        "generation": "阶段 4 · SQL 生成",
        "validation": "阶段 5 · SQL 校验",
        "repair": "阶段 6 · SQL 修复",
        "execution": "阶段 7 · SQL 执行",
        "answer": "阶段 8 · 结果整理",
    }
    return labels.get(stage, f"阶段 {index} · 处理中")


def _render_operation_mode_selector(database_name: str) -> str:
    current_mode = st.session_state.get("operation_mode", DEFAULT_UI_OPERATION_MODE)
    current_label = OPERATION_MODE_LABELS.get(current_mode, "DML")
    selected_label = st.radio(
        "操作模式",
        options=list(LABEL_TO_OPERATION_MODE.keys()),
        index=list(LABEL_TO_OPERATION_MODE.keys()).index(current_label),
        horizontal=True,
        help="DML 用于查询和增删改数据，DDL 用于创建或修改数据库结构。",
    )
    selected_mode = LABEL_TO_OPERATION_MODE[selected_label]
    if selected_mode != current_mode:
        st.session_state["operation_mode"] = selected_mode
        st.session_state["active_operation_mode"] = selected_mode
        st.session_state["database_notice"] = f"已切换到 {selected_label} 模式，旧对话已清空"
        _reset_chat_history(database_name, selected_mode)
        st.rerun()
    return selected_mode


def _resolve_active_settings(base_settings):
    selected_database = st.session_state.get("selected_database")
    if not selected_database:
        return base_settings

    database_path = Path(selected_database)
    if not database_path.exists():
        st.session_state.pop("selected_database", None)
        return base_settings

    try:
        asset_paths = ensure_local_database_assets(database_path, settings=base_settings)
    except Exception as exc:
        st.warning(f"本地数据库资产生成失败，已回退默认数据库：{exc}")
        st.session_state.pop("selected_database", None)
        clear_schema_loader_caches()
        return base_settings

    return replace(
        base_settings,
        database_path=database_path,
        schema_metadata_path=asset_paths["metadata"],
        semantic_layer_path=asset_paths["semantic"],
        demo_questions_path=asset_paths["examples"],
    )


def _render_database_resource_panel(settings) -> None:
    if st.session_state.get("database_notice"):
        st.success(st.session_state.pop("database_notice"))

    database_files = list_local_database_files()
    options = [DEFAULT_DATABASE_OPTION] + [path.name for path in database_files]
    current_database = st.session_state.get("selected_database")
    current_option = Path(current_database).name if current_database else DEFAULT_DATABASE_OPTION
    current_index = options.index(current_option) if current_option in options else 0

    st.write("当前数据库:", Path(settings.database_path).name)
    selected_name = st.selectbox("选择数据库", options, index=current_index, key="database_selector")

    if selected_name == DEFAULT_DATABASE_OPTION and current_database:
        st.session_state.pop("selected_database", None)
        st.session_state["active_database_name"] = "Chinook"
        clear_schema_loader_caches()
        _reset_chat_history("Chinook", st.session_state.get("operation_mode", DEFAULT_UI_OPERATION_MODE))
        st.rerun()

    if selected_name != DEFAULT_DATABASE_OPTION:
        selected_path = next((path for path in database_files if path.name == selected_name), None)
        if selected_path is not None and str(selected_path) != current_database:
            ensure_local_database_assets(selected_path, settings=settings)
            clear_schema_loader_caches()
            st.session_state["selected_database"] = str(selected_path)
            st.session_state["active_database_name"] = selected_path.stem
            st.session_state["database_notice"] = f"已切换到数据库 {selected_path.name}"
            _reset_chat_history(selected_path.stem, st.session_state.get("operation_mode", DEFAULT_UI_OPERATION_MODE))
            st.rerun()

    uploaded = st.file_uploader(
        "上传 SQLite 数据库 (.sqlite 或 .db)",
        type=["sqlite", "db"],
        key="database_uploader",
        help="上传后会自动抽取 schema metadata，并加入上方可选列表",
    )
    if uploaded is not None:
        upload_token = f"{uploaded.name}:{uploaded.size}"
        if upload_token != st.session_state.get("last_uploaded_token"):
            save_path = LOCAL_DATABASE_DIR / uploaded.name
            save_path.write_bytes(uploaded.getbuffer())
            build_local_database_assets(save_path, settings=settings)
            clear_schema_loader_caches()
            st.session_state["last_uploaded_token"] = upload_token
            st.session_state["selected_database"] = str(save_path)
            st.session_state["active_database_name"] = save_path.stem
            st.session_state["database_notice"] = f"已导入数据库 {uploaded.name}，并生成 schema metadata"
            _reset_chat_history(save_path.stem, st.session_state.get("operation_mode", DEFAULT_UI_OPERATION_MODE))
            st.rerun()

    refresh_col, delete_col = st.columns(2)
    with refresh_col:
        if st.button("刷新数据库列表", use_container_width=True):
            rebuild_all_local_database_assets(settings=settings)
            clear_schema_loader_caches()
            st.session_state["database_notice"] = "已刷新本地数据库列表并重建 metadata"
            st.rerun()
    with delete_col:
        if st.button(
            "删除已上传数据库",
            disabled=not current_database,
            use_container_width=True,
        ):
            delete_path = Path(current_database) if current_database else None
            if delete_path is not None and delete_path.exists():
                delete_local_database_assets(delete_path)
                delete_path.unlink()
            st.session_state.pop("selected_database", None)
            st.session_state["active_database_name"] = "Chinook"
            st.session_state.pop("database_selector", None)
            clear_schema_loader_caches()
            st.session_state["database_notice"] = "已删除所选数据库并回退到默认库"
            _reset_chat_history("Chinook", st.session_state.get("operation_mode", DEFAULT_UI_OPERATION_MODE))
            st.rerun()


def _render_schema_summary(schema_catalog) -> None:
    if not schema_catalog:
        st.write("当前数据库没有可展示的数据表。")
        return

    summary_rows = []
    for table in schema_catalog:
        primary_keys = [column.name for column in table.columns if column.is_primary_key]
        summary_rows.append(
            {
                "表名": table.name,
                "简介": table.description or "-",
                "字段角色预览": _build_column_role_preview(table),
                "行数": table.row_count,
                "列数": len(table.columns),
                "主键": ", ".join(primary_keys) or "-",
                "字段预览": ", ".join(column.name for column in table.columns[:5]),
            }
        )
    st.dataframe(pd.DataFrame(summary_rows), width="stretch")


def _build_column_role_preview(table) -> str:
    preview_items = []
    for column in table.columns[:3]:
        if column.description:
            preview_items.append(f"{column.name}: {column.description}")
        else:
            preview_items.append(column.name)
    return "；".join(preview_items) or "-"


@st.dialog("当前库表结构摘要", width="large")
def _show_schema_summary_dialog(database_name: str, schema_catalog, database_description: str) -> None:
    st.caption(f"当前数据库：{database_name}")
    if database_description:
        st.write("数据库简介：", database_description)
    _render_schema_summary(schema_catalog)


def _reset_chat_history(database_name: str, operation_mode: str) -> None:
    st.session_state["chat_history"] = [
        {
            "role": "assistant",
            "content": _build_welcome_message(database_name, operation_mode),
        }
    ]
    st.session_state["latest_response"] = None


def _sync_database_context(settings) -> None:
    current_database_name = Path(settings.database_path).stem
    previous_database_name = st.session_state.get("active_database_name")
    if previous_database_name is None:
        st.session_state["active_database_name"] = current_database_name
        return

    if previous_database_name != current_database_name:
        _reset_chat_history(current_database_name, st.session_state.get("operation_mode", DEFAULT_UI_OPERATION_MODE))
        st.session_state["active_database_name"] = current_database_name
        st.session_state["database_notice"] = f"已切换到数据库 {current_database_name}，旧对话已清空"


def _render_context_badges(database_name: str, operation_mode: str) -> str:
    mode_label = OPERATION_MODE_LABELS.get(operation_mode, operation_mode.upper())
    mode_class = "mode-badge is-ddl" if operation_mode == OPERATION_MODE_DDL else "mode-badge"
    return (
        '<div class="context-badge-row">'
        '<div class="database-badge">'
        '<span class="database-badge-label">当前数据库</span>'
        f'<span class="database-badge-name">{database_name}</span>'
        '</div>'
        f'<div class="{mode_class}">'
        '<span class="database-badge-label">当前模式</span>'
        f'<span class="database-badge-name">{mode_label}</span>'
        '</div>'
        '</div>'
    )


def _build_chat_input_placeholder(operation_mode: str) -> str:
    if operation_mode == OPERATION_MODE_DDL:
        return "例如：创建一个课程表，包含课程编号、课程名、学分"
    return "例如：把学号 S1005 的学生姓名更新为王晨；或查询借书未归还记录"


def _build_mode_examples(operation_mode: str) -> list[str]:
    if operation_mode == OPERATION_MODE_DDL:
        return [
            "创建一张课程表，包含课程编号、课程名、学分",
            "给 Book 表新增一个出版社字段",
            "删除一张临时测试表 temp_books",
        ]
    return [
        "查询当前所有未归还的借阅记录",
        "向 Student 表新增一条学生记录，学号 S1006，姓名 李青，班级 软工2302",
        "把 Book 表中编号 B006 的状态改成 已借出",
    ]


def _build_welcome_message(database_name: str, operation_mode: str) -> str:
    mode_label = OPERATION_MODE_LABELS.get(operation_mode, operation_mode.upper())
    if operation_mode == OPERATION_MODE_DDL:
        return f"你好，当前连接到 {database_name} 数据库，工作模式为 {mode_label}。可以直接描述建表、加列、改表结构等需求。"
    return f"你好，当前连接到 {database_name} 数据库，工作模式为 {mode_label}。可以直接描述查询、插入、更新或删除数据的需求。"


def _refresh_current_database_summary(orchestrator: NL2SQLOrchestrator, response: NL2SQLResponse) -> None:
    execution = response.execution
    if execution is None or not execution.succeeded or execution.statement_type == "select":
        return

    database_path = Path(orchestrator.settings.database_path).resolve()
    if database_path.suffix.lower() not in {".sqlite", ".db"}:
        return

    try:
        refresh_database_assets(
            database_path,
            Path(orchestrator.settings.schema_metadata_path),
            Path(orchestrator.settings.semantic_layer_path),
            Path(orchestrator.settings.demo_questions_path),
        )
        clear_schema_loader_caches()
        st.session_state["database_notice"] = f"已根据最新 SQL 执行结果刷新 {database_path.name} 的库表结构摘要"
    except Exception as exc:
        clear_schema_loader_caches()
        st.session_state["database_notice"] = f"SQL 已执行成功，但库表结构摘要刷新失败：{exc}"


def _should_render_result_table(response: NL2SQLResponse) -> bool:
    execution = response.execution
    return execution is not None and execution.succeeded and execution.statement_type == "select"