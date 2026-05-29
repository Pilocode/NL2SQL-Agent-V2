from __future__ import annotations

import io
import sqlite3
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd
import streamlit as st

from app.config import get_settings
from app.orchestrator import NL2SQLOrchestrator
from core.local_db_assets import LOCAL_DATABASE_DIR, build_local_database_assets, delete_local_database_assets, ensure_local_database_assets, list_local_database_files, rebuild_all_local_database_assets, refresh_database_assets
from core.models import NL2SQLResponse, OPERATION_MODE_AUTO, OPERATION_MODE_DDL, OPERATION_MODE_DML, PipelineResult, QueryAnalysis, QueryExecution, StageUpdate, SubTaskResult, ValidationResult
from core.schema_loader import clear_schema_loader_caches, load_schema_catalog, load_schema_document
from core.sql_executor import SQLiteExecutor


DEFAULT_DATABASE_OPTION = "-- 使用默认 Chinook 数据库 --"


def render_app() -> None:
    st.set_page_config(page_title="NL2SQL Agent", page_icon="🧭", layout="wide")
    _init_session_state()
    settings = _resolve_active_settings(get_settings())
    _sync_database_context(settings)
    _inject_custom_styles()
    operation_mode = OPERATION_MODE_AUTO

    # --- header ---
    hl, hr = st.columns([6, 0.8])
    with hl:
        st.markdown('<div class="gemini-title">NL2SQL Agent</div>', unsafe_allow_html=True)
        st.markdown('<div class="gemini-subtitle">输入自然语言，自动识别意图，智能生成并执行 SQL。</div>', unsafe_allow_html=True)
        st.markdown(_render_context_badges(Path(settings.database_path).stem), unsafe_allow_html=True)
    with hr:
        toggle_label = "✕ 关闭工具" if st.session_state["sidebar_open"] else "☰ 工具"
        if st.button(toggle_label, use_container_width=True, key="sidebar_toggle"):
            st.session_state["sidebar_open"] = not st.session_state["sidebar_open"]
            st.rerun()

    orchestrator = NL2SQLOrchestrator(settings)

    # --- body ---
    if st.session_state["sidebar_open"]:
        chat_col, side_col = st.columns([3, 1], gap="medium")
        with chat_col:
            _render_chat_area(orchestrator, settings, operation_mode)
        with side_col:
            _render_tools_sidebar(orchestrator, settings, operation_mode)
    else:
        _pad_l, chat_center, _pad_r = st.columns([1, 3.5, 1])
        with _pad_l:
            pass
        with chat_center:
            _render_chat_area(orchestrator, settings, operation_mode)
        with _pad_r:
            pass


def _render_chat_area(orchestrator: NL2SQLOrchestrator, settings, operation_mode: str) -> None:
    pending = st.session_state.get("pending_ddl_response")
    if pending is not None:
        _render_ddl_confirmation(orchestrator, pending)

    _render_chat_history()

    ocr = _check_ocr_status()
    if not ocr["ok"]:
        st.caption(f"🔴 {ocr['label']} — 点击右侧工具面板「OCR 配置引导」安装")

    uploader_key = f"image_uploader_{st.session_state.get('image_upload_counter', 0)}"
    uploaded_image = st.file_uploader(
        "📎 上传截图，自动识别文字和表格",
        type=["png", "jpg", "jpeg", "webp"],
        key=uploader_key,
        help="支持 PNG / JPG / WebP 格式的截图，自动提取文字后查询",
    )
    if uploaded_image is not None:
        _handle_image_input(uploaded_image, orchestrator, operation_mode)
        st.session_state["image_upload_counter"] = st.session_state.get("image_upload_counter", 0) + 1
        st.rerun()

    user_question = st.chat_input(_build_chat_input_placeholder(operation_mode))
    if user_question:
        _handle_user_question(orchestrator, user_question, operation_mode)
        st.rerun()


def _handle_image_input(uploaded_file, orchestrator: NL2SQLOrchestrator, operation_mode: str) -> None:
    try:
        from PIL import Image
    except ImportError:
        st.error("需要安装 Pillow 库才能处理图片：pip install Pillow")
        return

    try:
        image = Image.open(uploaded_file)
    except Exception:
        st.error("无法读取该图片文件，请确认格式为 PNG / JPG / WebP")
        return

    img_bytes = io.BytesIO()
    image.save(img_bytes, format="PNG")
    img_bytes = img_bytes.getvalue()

    col_a, col_b = st.columns([1, 3])
    with col_a:
        st.image(image, caption="已上传", width=220)
    with col_b:
        with st.spinner("正在识别图片中的文字和表格..."):
            extracted = _extract_text_from_image(img_bytes)

    if not extracted:
        st.error(
            "图片识别失败。"
            "如使用 DeepSeek 等不支持视觉的 API，需安装本地 OCR 引擎：\n\n"
            "1. 下载安装 Tesseract：https://github.com/UB-Mannheim/tesseract/wiki\n"
            "2. 安装后重启终端即可自动使用本地 OCR 识别"
        )
        return

    st.text_area("识别结果", extracted, height=120, disabled=True, key="ocr_result")

    query = _build_image_query(extracted, operation_mode)
    _handle_user_question(orchestrator, query, operation_mode)


def _build_image_query(extracted: str, operation_mode: str) -> str:
    if operation_mode not in (OPERATION_MODE_DDL, OPERATION_MODE_AUTO):
        return f"[📎 图片识别]\n\n{extracted}"

    if _looks_like_table_structure(extracted):
        return f"根据以下表结构信息创建表：\n\n{extracted}"

    return f"[📎 图片识别]\n\n{extracted}"


def _looks_like_table_structure(text: str) -> bool:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    # lines that look like column definitions: "name TYPE" or "name TYPE constraints"
    col_like = 0
    for ln in lines:
        words = ln.split()
        if len(words) >= 2 and all(w.isascii() for w in words[:2]):
            col_like += 1
    return col_like >= 2


def _extract_text_from_image(img_bytes: bytes) -> str | None:
    try:
        import pytesseract
        from PIL import Image as PILImage, ImageEnhance, ImageFilter, ImageOps

        _configure_tesseract_path()

        image = PILImage.open(io.BytesIO(img_bytes))

        # --- preprocess: enhance clarity while keeping character detail ---
        # 1) grayscale
        if image.mode != "L":
            image = image.convert("L")
        # 2) scale up small images (< 800px wide)
        w, h = image.size
        if w < 800:
            scale = max(2, 1600 // w)
            image = image.resize((w * scale, h * scale), PILImage.LANCZOS)
        # 3) mild contrast stretch
        image = ImageOps.autocontrast(image, cutoff=1)
        # 4) mild sharpen
        image = image.filter(ImageFilter.SHARPEN)

        text = pytesseract.image_to_string(
            image, lang="chi_sim+eng",
            config="--psm 6 --oem 3",
        ).strip()
        if text:
            return text
    except pytesseract.pytesseract.TesseractNotFoundError:
        st.error(
            "未找到 Tesseract OCR 引擎。请安装：\n\n"
            "Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "安装时勾选中文语言包，装完后重启终端"
        )
    except ImportError:
        st.error("未安装 pytesseract，请运行：pip install pytesseract")
    except Exception as exc:
        st.error(f"OCR 识别失败：{exc}")
    return None


def _render_ddl_confirmation(orchestrator: NL2SQLOrchestrator, response: NL2SQLResponse) -> None:
    st.warning(response.execution_confirmation.message)
    confirm_col, cancel_col = st.columns(2, gap="small")
    with confirm_col:
        if st.button("确认执行 DDL", use_container_width=True, key="confirm_ddl_execution"):
            confirmed_response = orchestrator.confirm_ddl_response(response)
            _refresh_current_database_summary(orchestrator, confirmed_response)
            st.session_state["latest_response"] = confirmed_response
            st.session_state["pending_ddl_response"] = None
            st.session_state["chat_history"].append(
                {
                    "role": "assistant",
                    "content": _format_assistant_message(confirmed_response),
                    "response": confirmed_response,
                }
            )
            st.rerun()
    with cancel_col:
        if st.button("取消本次执行", use_container_width=True, key="cancel_ddl_execution"):
            st.session_state["pending_ddl_response"] = None
            st.session_state["chat_history"].append(
                {
                    "role": "assistant",
                    "content": "已取消本次 DDL 执行，当前只保留生成与校验结果，未对数据库结构做任何修改。",
                }
            )
            st.rerun()


def _handle_compound_task(orchestrator: NL2SQLOrchestrator, question: str, plan: list[str], operation_mode: str) -> None:
    final_sub_results: tuple = ()
    with st.chat_message("assistant"):
        st.markdown(f"**📋 复合任务**，共 {len(plan)} 步")
        has_ddl = any(
            kw in desc.upper() or kw in desc
            for desc in plan
            for kw in ("CREATE", "ALTER", "DROP", "建表", "删表", "加列", "添加字段", "修改表", "增加字段", "删除字段")
        )
        for i, desc in enumerate(plan, 1):
            tag = " 🔒" if has_ddl and any(
                kw in desc.upper() or kw in desc
                for kw in ("CREATE", "ALTER", "DROP", "建表", "删表", "加列", "添加字段", "修改表", "增加字段", "删除字段")
            ) else ""
            st.caption(f"  {i}. {desc}{tag}")

        if has_ddl:
            st.warning("⚠️ 此计划包含修改表结构的操作，执行后不可撤销。")

        confirm_col, cancel_col = st.columns(2, gap="small")
        with confirm_col:
            confirmed = st.button("确认执行全部步骤", use_container_width=True, key="compound_confirm")
        with cancel_col:
            cancelled = st.button("取消", use_container_width=True, key="compound_cancel")

        if cancelled:
            st.session_state["chat_history"].append({
                "role": "assistant",
                "content": "已取消复合任务，未对数据库做任何修改。",
            })
            return

        if not confirmed:
            return

        progress = st.empty()
        for etype, payload in orchestrator.execute_compound_stream(question, plan, operation_mode):
            if etype == "step_start":
                idx, total, desc = payload
                progress.markdown(
                    f'<div class="gemini-progress anim-fade-up">'
                    f'步骤 {idx}/{total}: {desc}'
                    f'<span class="gemini-progress-dots"><span></span><span></span><span></span></span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            elif etype == "step_done":
                sr = payload
                status = "✓" if sr.succeeded else "✗"
                st.caption(f"  {status} {sr.message[:80]}")
                if sr.succeeded and sr.statement_type == "select" and sr.rows:
                    frame = pd.DataFrame(list(sr.rows), columns=list(sr.columns))
                    st.dataframe(frame, width="stretch")
            elif etype == "done":
                final_sub_results = payload
                progress.empty()
                break

    sub_results = final_sub_results
    succeeded = sum(1 for sr in sub_results if sr.succeeded)
    failed = len(sub_results) - succeeded
    all_ok = failed == 0 and len(sub_results) > 0

    if all_ok:
        answer = f"复合任务完成：{succeeded} 步全部成功。"
    else:
        answer = f"复合任务：{succeeded} 步成功，{failed} 步失败（已中断）。"

    dummy_response = NL2SQLResponse(
        pipeline=PipelineResult(
            analysis=QueryAnalysis(original_question=question, normalized_question=question, tokens=()),
            retrievals=(), example_candidates=(),
            operation_mode=operation_mode,
        ),
        prompt="",
        draft=None,
        validation=ValidationResult(is_valid=True, message=""),
        execution=QueryExecution(
            succeeded=all_ok,
            sql="",
            error_message="" if all_ok else answer,
        ),
        answer_text=answer,
        sub_results=sub_results,
        operation_mode=operation_mode,
    )
    status_badge = _build_execution_status_badge(dummy_response)
    st.markdown(
        f'{status_badge}<div class="anim-fade-up">{answer}</div>',
        unsafe_allow_html=True,
    )
    st.session_state["latest_response"] = dummy_response
    st.session_state["chat_history"].append({
        "role": "assistant",
        "content": f"{status_badge}\n\n{_format_compound_message(question, sub_results)}",
        "response": dummy_response,
    })
    # refresh DB summary if any DDL/DML modified the schema/data
    if any(sr.succeeded and sr.statement_type in ("create", "alter", "drop", "insert", "update", "delete") for sr in sub_results):
        _refresh_current_database_summary(orchestrator, dummy_response)


def _format_compound_message(question: str, sub_results: tuple) -> str:
    lines = ["📋 复合任务完成："]
    for sr in sub_results:
        icon = "✓" if sr.succeeded else "✗"
        msg = (sr.message or "")[:120]
        lines.append(f"{icon} {sr.description} → {msg}")
    return "\n\n".join(lines)


def _handle_user_question(orchestrator: NL2SQLOrchestrator, question: str, operation_mode: str) -> None:
    st.session_state["chat_history"].append({"role": "user", "content": question})

    # show immediate feedback while planning
    with st.chat_message("assistant"):
        status = st.empty()
        status.markdown(
            '<div class="gemini-progress anim-fade-up">正在分析意图'
            '<span class="gemini-progress-dots"><span></span><span></span><span></span></span></div>',
            unsafe_allow_html=True,
        )
        plan = orchestrator.plan_compound(question)
        status.empty()

    if plan and len(plan) >= 2:
        _handle_compound_task(orchestrator, question, plan, operation_mode)
        return

    response: NL2SQLResponse | None = None

    with st.chat_message("assistant"):
        progress_placeholder = st.empty()
        stage_updates: list[StageUpdate] = []
        for event_type, payload in orchestrator.answer_question_stream(question, operation_mode=operation_mode):
            if event_type == "stage":
                assert isinstance(payload, StageUpdate)
                stage_updates.append(payload)
                progress_placeholder.markdown(
                    f'<div class="gemini-progress anim-fade-up">'
                    f'{_stage_label(payload.stage)}'
                    f'<span class="gemini-progress-dots"><span></span><span></span><span></span></span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                continue

            assert isinstance(payload, NL2SQLResponse)
            response = payload

        progress_placeholder.empty()
        if response is not None:
            st.markdown(f'<div class="anim-fade-up">{_format_assistant_message(response)}</div>', unsafe_allow_html=True)
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
    st.session_state["pending_ddl_response"] = response if _response_is_awaiting_ddl_confirmation(response) else None
    st.session_state["chat_history"].append(
        {
            "role": "assistant",
            "content": _format_assistant_message(response),
            "response": response,
        }
    )


def _render_chat_history() -> None:
    msgs = st.session_state["chat_history"]
    n = len(msgs)
    if n == 0:
        return

    def _render_msg(message, display_idx: int) -> None:
        role = message["role"]
        with st.chat_message(role):
            response = message.get("response")
            msg_class = "gemini-msg-user" if role == "user" else "gemini-msg-assistant"
            delay_style = f"animation-delay: {display_idx * 0.05}s;" if display_idx < 10 else ""

            if response is not None and response.stage_updates:
                with st.expander("查看处理过程", expanded=False):
                    st.markdown(_render_stage_bubbles(list(response.stage_updates)), unsafe_allow_html=True)

            st.markdown(
                f'<div class="{msg_class}" style="{delay_style}">{message["content"]}</div>',
                unsafe_allow_html=True,
            )
            if response is None or not _should_render_result_table(response):
                return
            result_frame = pd.DataFrame(
                list(response.execution.rows),
                columns=list(response.execution.columns),
            )
            st.dataframe(result_frame, width="stretch")

    if n <= 3:
        for i, msg in enumerate(msgs):
            _render_msg(msg, i)
        return

    # always visible: welcome message
    _render_msg(msgs[0], 0)

    # collapsed: middle messages
    hidden = msgs[1:-2]
    with st.expander(f"历史记录（{len(hidden)} 条）", expanded=False):
        for i, msg in enumerate(hidden, start=0):
            _render_msg(msg, i)

    # always visible: latest Q&A pair
    for i, msg in enumerate(msgs[-2:], start=0):
        _render_msg(msg, i)


def _configure_tesseract_path() -> None:
    """Probe common Tesseract install locations and configure pytesseract."""
    import importlib
    try:
        import pytesseract
    except ImportError:
        return
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for path in candidates:
        if Path(path).exists():
            pytesseract.pytesseract.tesseract_cmd = path
            return


def _check_ocr_status() -> dict:
    try:
        import pytesseract
        _configure_tesseract_path()
        try:
            ver = pytesseract.get_tesseract_version()
            return {"ok": True, "label": f"OCR 就绪 (Tesseract {ver})"}
        except pytesseract.pytesseract.TesseractNotFoundError:
            return {"ok": False, "label": "OCR 未配置 — Tesseract 引擎未安装"}
    except ImportError:
        return {"ok": False, "label": "OCR 未配置 — pytesseract 未安装"}


@st.dialog("OCR 配置引导", width="large")
def _show_ocr_setup_dialog() -> None:
    status = _check_ocr_status()
    if status["ok"]:
        st.success(f"✅ {status['label']}")
        st.write("OCR 已就绪，上传截图即可自动识别文字和表格。")
        return

    st.error(f"❌ {status['label']}")
    st.markdown("### 安装步骤")
    st.markdown("""
**第 1 步 — 安装 Tesseract OCR 引擎**

👉 [下载 Windows 安装包](https://github.com/UB-Mannheim/tesseract/wiki)

下载 `tesseract-ocr-w64-setup-5.4.0.20240606.exe`，安装时务必勾选：

- **Chinese Simplified**（中文简体语言包）
- **English**（默认已勾选）

**第 2 步 — 验证安装**

打开新的终端窗口，输入：

```
tesseract --version
```

如果显示版本号（如 `tesseract 5.4.0`），说明安装成功。

**第 3 步 — 重启应用**

关闭并重新启动 Streamlit 应用，OCR 状态应变为绿色就绪。
""")
    st.info("安装完成后点击下方按钮刷新状态")
    if st.button("🔄 重新检测", use_container_width=True):
        st.rerun()


def _render_tools_sidebar(orchestrator: NL2SQLOrchestrator, settings, operation_mode: str) -> None:
    response: NL2SQLResponse | None = st.session_state.get("latest_response")
    schema_document = load_schema_document(settings.schema_metadata_path)
    schema_catalog = load_schema_catalog(settings.schema_metadata_path, settings.semantic_layer_path)
    database_name = Path(settings.database_path).stem
    database_description = str(schema_document.get("description") or "")

    ocr = _check_ocr_status()

    with st.container(border=True):
        st.markdown('<div class="sidebar-header">工具面板</div>', unsafe_allow_html=True)
        llm_status = "LLM 已启用" if settings.llm_api_key and settings.llm_model else "LLM 未配置，走本地回退"
        st.caption(llm_status)

        ocr_color = "#4ade80" if ocr["ok"] else "#f87171"
        st.markdown(
            f'<div style="font-size:0.78rem;color:{ocr_color};display:flex;align-items:center;gap:4px;">'
            f'{"🟢" if ocr["ok"] else "🔴"} {ocr["label"]}'
            f'</div>',
            unsafe_allow_html=True,
        )
        if not ocr["ok"]:
            if st.button("🔧 OCR 配置引导", use_container_width=True, key="side_ocr_setup"):
                _show_ocr_setup_dialog()

        st.markdown('<div class="sidebar-section-label">数据浏览</div>', unsafe_allow_html=True)
        if st.button("📊 库表结构摘要", use_container_width=True, key="side_schema"):
            st.session_state["show_schema_summary"] = not st.session_state.get("show_schema_summary", False)
        if st.session_state.get("show_schema_summary"):
            with st.expander("📊 库表结构摘要", expanded=True):
                st.caption(f"当前数据库：{database_name}")
                if database_description:
                    st.write("数据库简介：", database_description)
                _render_schema_summary(schema_catalog)

        if st.button("🔍 浏览表数据", use_container_width=True, key="side_browse"):
            st.session_state["show_table_browser"] = not st.session_state.get("show_table_browser", False)
        if st.session_state.get("show_table_browser"):
            with st.expander("🔍 浏览表数据", expanded=True):
                _render_table_browser(settings, schema_catalog)

        st.markdown('<div class="sidebar-section-label">管理</div>', unsafe_allow_html=True)
        if st.button("💾 数据资源管理", use_container_width=True, key="side_resources"):
            st.session_state["show_resources"] = not st.session_state.get("show_resources", False)
        if st.session_state.get("show_resources"):
            with st.expander("💾 数据资源管理", expanded=True):
                _render_database_resource_panel(settings)

        if response is not None:
            st.markdown('<div class="sidebar-section-label">诊断</div>', unsafe_allow_html=True)
            if st.button("📋 执行详情", use_container_width=True, key="side_exec"):
                st.session_state["show_exec_detail"] = not st.session_state.get("show_exec_detail", False)
            if st.session_state.get("show_exec_detail"):
                with st.expander("📋 执行详情", expanded=True):
                    _render_execution_detail(response, orchestrator, settings, operation_mode)

        if response is None:
            st.markdown('<div class="sidebar-section-label">帮助</div>', unsafe_allow_html=True)
            for example in _build_mode_examples(operation_mode):
                st.caption(f"• {example}")


def _init_session_state() -> None:
    st.session_state.setdefault(
        "chat_history",
        [
            {
                "role": "assistant",
                "content": _build_welcome_message("Chinook"),
            }
        ],
    )
    st.session_state.setdefault("latest_response", None)
    st.session_state.setdefault("selected_database", None)
    st.session_state.setdefault("active_database_name", None)
    st.session_state.setdefault("pending_ddl_response", None)
    st.session_state.setdefault("sidebar_open", False)
    st.session_state.setdefault("last_image_token", None)
    st.session_state.setdefault("image_upload_counter", 0)


def _format_assistant_message(response: NL2SQLResponse) -> str:
    status_html = _build_execution_status_badge(response)
    lines = [status_html] if status_html else []
    lines.append(response.answer_text.strip() or "当前没有可展示的回答。")
    if response.final_sql:
        lines.append(f'<div class="gemini-result-card"><div class="gemini-result-label">最终 SQL</div>')
        lines.append(f'\n```sql\n{response.final_sql}\n```')
        lines.append('</div>')
    return "\n\n".join(lines)


def _build_execution_status_badge(response: NL2SQLResponse) -> str:
    exec_data = response.execution
    if exec_data is None:
        return ""

    if _response_is_awaiting_ddl_confirmation(response):
        return f'<div class="exec-status-badge pending">等待确认</div>'

    if exec_data.succeeded:
        stmt = exec_data.statement_type
        if stmt == "select":
            label = f"查询成功 · 返回 {exec_data.row_count} 行"
        elif stmt in ("insert", "update", "delete"):
            label = f"写入成功 · 影响 {exec_data.affected_rows} 行"
        elif stmt in ("create", "alter", "drop"):
            label = "DDL 已执行"
        else:
            label = "执行成功"
        return f'<div class="exec-status-badge success">{label}</div>'
    else:
        label = "执行失败"
        return f'<div class="exec-status-badge error">{label}</div>'


def _inject_custom_styles() -> None:
    st.markdown(
        """
        <style>
        /* ===== Theme-neutral core ===== */
        :root {
            --bg-surface: rgba(128, 128, 128, 0.06);
            --bg-card: rgba(128, 128, 128, 0.04);
            --border-subtle: rgba(128, 128, 128, 0.12);
            --border-hover: rgba(128, 128, 128, 0.22);
            --text-secondary: rgba(128, 128, 128, 0.7);
            --accent-1: #4285f4;
            --accent-2: #8b5cf6;
            --accent-3: #e94560;
            --accent-gradient: linear-gradient(135deg, #4285f4, #8b5cf6, #e94560);
            --accent-glow: 0 0 20px rgba(66, 133, 244, 0.15), 0 0 40px rgba(139, 92, 246, 0.08);
            --success: #22c55e;
            --warning: #eab308;
            --error: #ef4444;
        }

        /* ===== Animations ===== */
        @keyframes geminiFadeUp {
            from { opacity: 0; transform: translateY(14px); }
            to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes geminiShimmer {
            0%   { background-position: -200% 0; }
            100% { background-position: 200% 0; }
        }
        @keyframes geminiPulse {
            0%, 100% { opacity: 1; }
            50%      { opacity: 0.45; }
        }
        @keyframes geminiGlow {
            0%, 100% { box-shadow: 0 0 8px rgba(66, 133, 244, 0.12); }
            50%      { box-shadow: 0 0 22px rgba(168, 85, 247, 0.22); }
        }
        @keyframes geminiGradientShift {
            0%   { background-position: 0% 50%; }
            50%  { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
        @keyframes geminiScaleIn {
            from { opacity: 0; transform: scale(0.96); }
            to   { opacity: 1; transform: scale(1); }
        }
        @keyframes geminiDotBounce {
            0%, 80%, 100% { transform: translateY(0); }
            40%           { transform: translateY(-6px); }
        }

        .anim-fade-up {
            animation: geminiFadeUp 0.45s ease-out both;
        }
        .anim-scale-in {
            animation: geminiScaleIn 0.35s ease-out both;
        }

        /* ===== Title ===== */
        .gemini-title {
            font-size: 2.3rem;
            font-weight: 700;
            background: var(--accent-gradient);
            background-size: 200% 200%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: geminiGradientShift 6s linear infinite;
            margin-bottom: 0.15rem;
        }
        .gemini-subtitle {
            color: rgba(128,128,128,0.7);
            font-size: 0.95rem;
            margin-bottom: 0.6rem;
        }

        /* ===== Context Badges ===== */
        .context-badge-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
            margin: 0.5rem 0 1.1rem 0;
        }
        .gemini-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.35rem 0.75rem;
            border-radius: 999px;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            transition: border-color 0.3s ease, box-shadow 0.3s ease;
        }
        .gemini-badge:hover {
            border-color: var(--border-hover);
            box-shadow: var(--accent-glow);
        }
        .gemini-badge-label {
            font-size: 0.73rem;
            font-weight: 600;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            opacity: 0.65;
        }
        .gemini-badge-name {
            font-size: 0.95rem;
            font-weight: 600;
        }
        .gemini-badge.accent {
            border-color: rgba(66, 133, 244, 0.3);
        }
        .gemini-badge.accent-rose {
            border-color: rgba(233, 69, 96, 0.3);
        }

        /* ===== Chat Messages ===== */
        .gemini-chat-wrap {
            animation: geminiFadeUp 0.4s ease-out both;
        }
        .gemini-msg-user {
            background: rgba(66, 133, 244, 0.08);
            border: 1px solid rgba(66, 133, 244, 0.18);
            border-radius: 20px 20px 6px 20px;
            padding: 1.1rem 1.3rem;
            margin: 0.5rem 0 0.9rem 0;
            line-height: 1.6;
            font-size: 1.02rem;
        }
        .gemini-msg-assistant {
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 20px 20px 20px 6px;
            padding: 1.1rem 1.3rem;
            margin: 0.5rem 0 0.9rem 0;
            line-height: 1.6;
            font-size: 1.02rem;
            transition: border-color 0.3s ease;
        }
        .gemini-msg-assistant:hover {
            border-color: var(--border-hover);
        }

        /* ===== Progress Indicator ===== */
        .gemini-progress {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.6rem 0.9rem;
            margin: 0.4rem 0;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 14px;
            font-size: 0.85rem;
        }
        .gemini-progress-dots {
            display: inline-flex;
            gap: 4px;
            margin-left: 2px;
        }
        .gemini-progress-dots span {
            width: 5px; height: 5px;
            border-radius: 50%;
            background: var(--accent-2);
            display: inline-block;
            animation: geminiDotBounce 1.4s ease-in-out infinite both;
        }
        .gemini-progress-dots span:nth-child(1) { animation-delay: 0.0s; }
        .gemini-progress-dots span:nth-child(2) { animation-delay: 0.16s; }
        .gemini-progress-dots span:nth-child(3) { animation-delay: 0.32s; }

        /* ===== Stage Bubbles (in expander) ===== */
        .stage-bubble-stack {
            display: flex;
            flex-direction: column;
            gap: 0.45rem;
            margin: 0.2rem 0 0.6rem 0;
        }
        .stage-bubble {
            max-width: 100%;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 0.6rem 0.8rem;
            transition: border-color 0.3s ease;
        }
        .stage-bubble.is-latest {
            border-color: rgba(168, 85, 247, 0.35);
            animation: geminiGlow 3s ease-in-out infinite;
        }
        .stage-bubble-title {
            font-size: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: var(--accent-2);
            margin-bottom: 0.2rem;
        }
        .stage-bubble-text {
            line-height: 1.4;
            font-size: 0.88rem;
        }

        /* ===== Glass Panel ===== */
        .gemini-glass-panel {
            background: var(--bg-surface);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--border-subtle);
            border-radius: 18px;
            padding: 1.2rem 1.3rem;
            transition: border-color 0.3s ease, box-shadow 0.3s ease;
        }
        .gemini-glass-panel:hover {
            border-color: var(--border-hover);
        }

        /* ===== Buttons ===== */
        .stButton > button {
            border-radius: 12px !important;
            font-weight: 600 !important;
            transition: all 0.25s ease !important;
            border: 1px solid var(--border-subtle) !important;
        }
        .stButton > button:hover {
            border-color: var(--border-hover) !important;
            box-shadow: var(--accent-glow) !important;
            transform: translateY(-1px);
        }
        .stButton > button:active {
            transform: translateY(0) scale(0.98);
        }

        details[data-testid="stExpander"] {
            border: 1px solid var(--border-subtle) !important;
            border-radius: 12px !important;
            transition: border-color 0.3s ease !important;
            margin-bottom: 0.4rem !important;
        }
        details[data-testid="stExpander"]:hover {
            border-color: var(--border-hover) !important;
        }
        details[data-testid="stExpander"] summary {
            font-weight: 600 !important;
            padding: 0.55rem 0.75rem !important;
            border-radius: 12px !important;
        }

        [data-testid="stChatInput"] {
            border-radius: 16px !important;
            border: 1px solid var(--border-subtle) !important;
            transition: border-color 0.3s ease, box-shadow 0.3s ease !important;
        }
        [data-testid="stChatInput"]:focus-within {
            border-color: rgba(66, 133, 244, 0.4) !important;
            box-shadow: var(--accent-glow) !important;
        }

        [data-testid="stDataFrame"] {
            border: 1px solid var(--border-subtle) !important;
            border-radius: 12px !important;
            overflow: hidden !important;
        }
        [data-testid="stDataFrame"] th {
            font-weight: 600 !important;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.04em;
        }
        [data-testid="stDataFrame"] td {
            border-bottom: 1px solid var(--border-subtle) !important;
        }

        pre, code {
            border: 1px solid var(--border-subtle) !important;
            border-radius: 10px !important;
        }

        [data-testid="stSelectbox"], [data-testid="stSlider"],
        [data-testid="stTextInput"], .stRadio {
            transition: all 0.25s ease !important;
        }

        /* ===== Scrollbar ===== */
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.08);
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.14);
        }

        /* ===== Dialog ===== */
        [data-testid="stDialog"] > div {
            backdrop-filter: blur(24px) !important;
            -webkit-backdrop-filter: blur(24px) !important;
            border: 1px solid var(--border-subtle) !important;
            border-radius: 18px !important;
        }

        /* ===== Welcome Card ===== */
        .gemini-welcome {
            text-align: center;
            padding: 2rem 1.5rem;
            animation: geminiScaleIn 0.5s ease-out both;
        }
        .gemini-welcome-icon {
            font-size: 2.8rem;
            margin-bottom: 0.8rem;
        }
        .gemini-welcome-text {
            font-size: 1.05rem;
            line-height: 1.6;
        }

        /* ===== Result Card ===== */
        .gemini-result-card {
            background: rgba(52, 168, 83, 0.06);
            border: 1px solid rgba(52, 168, 83, 0.2);
            border-radius: 14px;
            padding: 1rem 1.2rem;
            margin-top: 0.6rem;
        }
        .gemini-result-label {
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: var(--success);
            margin-bottom: 0.3rem;
        }

        /* ===== Expand All / Collapse All ===== */
        .gemini-detail-section {
            animation: geminiFadeUp 0.35s ease-out both;
        }

        /* ===== Execution Status Badge ===== */
        .exec-status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.35rem 0.8rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
            animation: geminiScaleIn 0.35s ease-out both;
        }
        .exec-status-badge.success {
            background: rgba(52, 168, 83, 0.1);
            border: 1px solid rgba(52, 168, 83, 0.25);
            color: #4ade80;
        }
        .exec-status-badge.success::before {
            content: "✓";
            font-weight: 700;
            font-size: 0.85rem;
        }
        .exec-status-badge.error {
            background: rgba(234, 67, 53, 0.1);
            border: 1px solid rgba(234, 67, 53, 0.25);
            color: #f87171;
        }
        .exec-status-badge.error::before {
            content: "✗";
            font-weight: 700;
            font-size: 0.85rem;
        }
        .exec-status-badge.pending {
            background: rgba(251, 188, 4, 0.1);
            border: 1px solid rgba(251, 188, 4, 0.3);
            color: #facc15;
        }
        .exec-status-badge.pending::before {
            content: "⏳";
            font-size: 0.85rem;
        }

        /* ===== Sidebar ===== */
        .sidebar-header {
            font-size: 1.05rem;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 0.4rem;
        }
        .sidebar-section-label {
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: var(--text-secondary);
            margin: 0.7rem 0 0.35rem 0;
            padding-left: 0.2rem;
        }

        /* ===== Mode Section Label ===== */
        .gemini-mode-section-label {
            text-align: right;
            font-size: 0.82rem;
            font-weight: 600;
            color: var(--text-secondary);
            letter-spacing: 0.04em;
            text-transform: uppercase;
            padding-top: 0.2rem;
        }

        /* ===== Global Font ===== */
        html { font-size: 17px; }
        .stMarkdown p { font-size: 1rem; line-height: 1.6; }
        .stChatMessage p { font-size: 1rem; }
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
    return f"阶段 {index} · {_stage_label(stage)}"


_STAGE_LABELS = {
    "analysis": "问题分析",
    "analysis_decision": "分析决策",
    "thinking": "语义澄清",
    "retrieval_refresh": "召回刷新",
    "generation": "SQL 生成",
    "validation": "SQL 校验",
    "confirmation": "执行确认",
    "execution": "SQL 执行",
    "answer": "结果整理",
}


def _stage_label(stage: str) -> str:
    return _STAGE_LABELS.get(stage, "处理中")


def _response_is_awaiting_ddl_confirmation(response: NL2SQLResponse) -> bool:
    confirmation = response.execution_confirmation
    return bool(confirmation is not None and confirmation.required and not confirmation.confirmed)



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
        _reset_chat_history("Chinook")
        st.rerun()

    if selected_name != DEFAULT_DATABASE_OPTION:
        selected_path = next((path for path in database_files if path.name == selected_name), None)
        if selected_path is not None and str(selected_path) != current_database:
            ensure_local_database_assets(selected_path, settings=settings)
            clear_schema_loader_caches()
            st.session_state["selected_database"] = str(selected_path)
            st.session_state["active_database_name"] = selected_path.stem
            st.session_state["database_notice"] = f"已切换到数据库 {selected_path.name}"
            _reset_chat_history(selected_path.stem)
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
            with st.spinner(f"正在导入 {uploaded.name} ..."):
                save_path.write_bytes(uploaded.getbuffer())
                build_local_database_assets(save_path, settings=settings)
                clear_schema_loader_caches()
                st.session_state["last_uploaded_token"] = upload_token
                st.session_state["selected_database"] = str(save_path)
                st.session_state["active_database_name"] = save_path.stem
                st.session_state["database_notice"] = f"已导入数据库 {uploaded.name}，并生成 schema metadata"
                _reset_chat_history(save_path.stem)
            st.success(f"✓ 已导入 {uploaded.name}")
            time.sleep(0.4)
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
            _reset_chat_history("Chinook")
            st.rerun()

    st.divider()
    st.caption("新建空白数据库")
    new_db_name = st.text_input(
        "数据库名称（不含扩展名）",
        key="new_db_name_input",
        placeholder="例如：my_project",
    )
    existing_names = {p.stem for p in database_files} | {"Chinook"}
    create_disabled = not new_db_name.strip() or new_db_name.strip() in existing_names
    if st.button("创建空白数据库", disabled=create_disabled, use_container_width=True):
        safe_name = new_db_name.strip().replace("/", "_").replace("\\", "_").replace(" ", "_")
        new_path = LOCAL_DATABASE_DIR / f"{safe_name}.sqlite"
        with st.spinner(f"正在创建 {safe_name}.sqlite ..."):
            LOCAL_DATABASE_DIR.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(new_path))
            conn.execute("CREATE TABLE _tmp(id INTEGER)")
            conn.execute("DROP TABLE _tmp")
            conn.close()
            build_local_database_assets(new_path, settings=settings)
            clear_schema_loader_caches()
            st.session_state["selected_database"] = str(new_path)
            st.session_state["active_database_name"] = safe_name
            st.session_state["database_notice"] = f"已创建空白数据库 {safe_name}.sqlite"
            _reset_chat_history(safe_name)
        st.success(f"✓ 数据库 {safe_name}.sqlite 创建成功")
        time.sleep(0.4)
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


def _render_table_browser(settings, schema_catalog) -> None:
    if not schema_catalog:
        st.write("当前数据库没有可浏览的数据表。")
        return

    database_path = Path(settings.database_path)
    if not database_path.exists():
        st.write("当前数据库文件不可用。")
        return

    table_names = [table.name for table in schema_catalog]
    selected_table = st.selectbox("选择数据表", table_names, key="table_browser_select")
    limit_rows = st.slider("返回行数上限", min_value=10, max_value=500, value=50, step=10, key="table_browser_limit")

    if st.button("查询表数据", use_container_width=True, key="table_browser_query"):
        try:
            executor = SQLiteExecutor(database_path)
            safe_table = selected_table.replace('"', '""')
            result_frame = executor.query(f'SELECT * FROM "{safe_table}" LIMIT {int(limit_rows)}')
            st.write(f"**{selected_table}**（共 {len(result_frame)} 行）")
            st.dataframe(result_frame, width="stretch")
        except Exception as exc:
            st.error(f"查询失败：{exc}")


@st.dialog("当前库表结构摘要", width="large")
def _show_schema_summary_dialog(database_name: str, schema_catalog, database_description: str) -> None:
    try:
        st.caption(f"当前数据库：{database_name}")
        if database_description:
            st.write("数据库简介：", database_description)
        if not schema_catalog:
            st.write("当前数据库没有可展示的数据表。")
            return
        _render_schema_summary(schema_catalog)
    except Exception as exc:
        st.error(f"渲染失败：{exc}")


@st.dialog("浏览表数据", width="large")
def _show_table_browser_dialog(settings, schema_catalog) -> None:
    try:
        _render_table_browser(settings, schema_catalog)
    except Exception as exc:
        st.error(f"渲染失败：{exc}")


@st.dialog("数据资源管理", width="large")
def _show_database_resources_dialog(settings) -> None:
    try:
        _render_database_resource_panel(settings)
    except Exception as exc:
        st.error(f"渲染失败：{exc}")


def _render_execution_detail(response: NL2SQLResponse, orchestrator: NL2SQLOrchestrator, settings, operation_mode: str) -> None:
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
            st.write("当前未生成 SQL，流程已在生成阶段终止。")
        st.write("操作模式:", "智能识别" if response.operation_mode == OPERATION_MODE_AUTO else response.operation_mode.upper())
        if response.validation.statement_type:
            st.write("语句类型:", response.validation.statement_type)
        st.write("校验结果:", response.validation.message)
        if response.final_sql:
            st.write("最终 SQL:")
            st.code(response.final_sql, language="sql")

    if response.generation_diagnostics is not None:
        with st.expander("第3阶段调试面板", expanded=False):
            st.write("失败类型:", response.generation_diagnostics.strategy)
            st.write("诊断信息:", response.generation_diagnostics.message)
            if response.generation_diagnostics.raw_response_preview is not None:
                st.write("原始返回预览:")
                st.code(response.generation_diagnostics.raw_response_preview, language="text")
            else:
                st.write("本次没有可展示的原始返回预览。")

    with st.expander("自动修复记录", expanded=False):
        if not response.repairs:
            st.write("当前版本已关闭自动修复；生成失败或校验失败后会直接终止后续阶段。")
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


def _reset_chat_history(database_name: str) -> None:
    st.session_state["chat_history"] = [
        {
            "role": "assistant",
            "content": _build_welcome_message(database_name),
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
        _reset_chat_history(current_database_name)
        st.session_state["active_database_name"] = current_database_name
        st.session_state["database_notice"] = f"已切换到数据库 {current_database_name}，旧对话已清空"


def _render_context_badges(database_name: str) -> str:
    return (
        '<div class="context-badge-row">'
        '<div class="gemini-badge">'
        '<span class="gemini-badge-label">数据库</span>'
        f'<span class="gemini-badge-name">{database_name}</span>'
        '</div>'
        '<div class="gemini-badge accent">'
        '<span class="gemini-badge-label">模式</span>'
        '<span class="gemini-badge-name">智能识别</span>'
        '</div>'
        '</div>'
    )


def _build_chat_input_placeholder(operation_mode: str) -> str:
    return "例如：查询未归还记录；或创建课程表(id, name, credit)；或插入测试数据"


def _build_mode_examples(operation_mode: str) -> list[str]:
    return [
        "查询当前所有未归还的借阅记录",
        "向 Student 表新增一条学生记录，学号 S1006，姓名 李青，班级 软工2302",
        "创建一张课程表，包含课程编号、课程名、学分，并插入3条测试数据",
    ]


def _build_welcome_message(database_name: str) -> str:
    body = f"当前连接到 <strong>{database_name}</strong>，智能识别查询、插入、更新、删除、建表、改表等操作。"
    return (
        '<div class="gemini-welcome">'
        '<div class="gemini-welcome-icon">🧭</div>'
        f'<div class="gemini-welcome-text">{body}</div>'
        '</div>'
    )


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