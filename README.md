# NL2SQL Agent

一个面向课程项目和本地演示的 NL2SQL 系统，提供 Streamlit 界面，支持自然语言查询、数据写入、数据库结构修改，以及多数据库切换。

## 你可以用它做什么

- 把自然语言转换成 SQL，并直接执行。
- 在 DML 模式下执行查询、插入、更新、删除。
- 在 DDL 模式下创建表、加列、改表结构。
- 在页面里切换默认 Chinook 库和本地上传的 SQLite 库。
- 自动展示当前库表结构摘要，并在成功执行非 SELECT SQL 后自动刷新。

## 当前项目特性

- Streamlit 聊天式界面。
- Analysis / Thinking / Generation / Validation / Repair / Execution 分阶段流水线。
- OpenAI 兼容接口接入，支持通过环境变量切换模型服务。
- 本地数据库资产构建：metadata、semantic layer、examples。
- 多数据库路由与本地示例库管理。
- 已包含 Chinook 和多个本地 SQLite 演示库。

## 快速开始

### 1. 创建并激活虚拟环境

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. 安装依赖

```powershell
pip install -r requirements.txt
```

### 3. 启动 Web UI

```powershell
python -m streamlit run app/main.py
```

启动后默认访问地址：

- http://localhost:8501

## 常用命令

运行全部测试：

```powershell
python -m pytest
```

仅运行关键流水线测试：

```powershell
python -m pytest tests/test_sql_pipeline.py tests/test_operation_modes.py
```

重新生成 Chinook metadata：

```powershell
python scripts/generate_metadata.py
```

生成演示本地数据库：

```powershell
python scripts/create_sample_dbs.py
python scripts/create_library_demo_db.py
```

## 环境变量

项目优先读取以下变量：

- `NL2SQL_API_KEY` / `OPENAI_API_KEY` / `DASHSCOPE_API_KEY`
- `NL2SQL_BASE_URL` / `OPENAI_BASE_URL`
- `NL2SQL_MODEL` / `OPENAI_MODEL`
- `NL2SQL_ANALYSIS_MODEL`
- `NL2SQL_THINKING_MODEL`
- `NL2SQL_GENERATION_MODEL`
- `NL2SQL_REPAIR_MODEL`
- `NL2SQL_ANSWER_MODEL`

如果当前环境里存在 `DASHSCOPE_API_KEY`，项目会默认走 DashScope 兼容接口，并优先使用配置里的默认模型。

## 目录说明

- `app/`：Streamlit UI、配置和主编排逻辑。
- `core/`：分析、生成、校验、执行、检索和数据库资产管理核心代码。
- `data/`：原始数据库、处理后的 metadata/semantic layer、评测集和本地演示库。
- `scripts/`：数据准备、资产构建和评测脚本。
- `tests/`：单元测试和轻量回归测试。
- `docs/`：系统架构图和答辩图材料。

## 推荐演示路径

1. 打开页面后，先选择 `library_demo.sqlite`。
2. 在 DML 模式中执行一条查询或更新。
3. 切换到 DDL 模式，执行建表或加列。
4. 打开“当前库表结构摘要”，确认结构已自动刷新。

## 适用场景

- 数据库课程大作业演示。
- 本地 SQLite 数据库问答和操作原型。
- Text-to-SQL / Agent 工作流实验。

## 说明

- 当前仓库以 SQLite 为主。
- 默认库为 Chinook。
- 本地上传库和默认 SQLite 库在成功执行非 SELECT SQL 后，摘要会自动刷新。