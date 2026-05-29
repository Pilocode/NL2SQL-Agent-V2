# NL2SQL Agent

一个面向课程项目和本地演示的 NL2SQL 系统，提供 Streamlit 界面，支持自然语言查询、数据写入、数据库结构修改、多数据库切换，以及复合任务执行。

## 核心功能

- 自然语言 → SQL，自动识别意图，智能选择查询/插入/更新/删除/建表/改表
- 复合任务：一句自然语言完成多步操作（如"建表→插入数据→查询"），自动分解并顺序执行
- 图片 OCR：上传或粘贴截图，自动提取文字和表格信息并查询
- 多数据库切换：Chinook 默认库 + 本地上传 + 新建空白库
- 库表结构摘要 & 浏览表数据
- 执行结果反馈：成功/失败带彩色状态徽章，失败时 LLM 生成中文解释
- Gemini 风格暗色/浅色自适应 UI

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

### 3. 安装 Tesseract OCR（图片识别需要）

下载安装 [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)，勾选中文语言包。安装后重启终端。

### 4. 启动

```powershell
python -m streamlit run app/main.py
```

默认访问：http://localhost:8501

## 常用命令

```powershell
# 运行全部测试
python -m pytest

# 运行流水线测试
python -m pytest tests/test_sql_pipeline.py tests/test_operation_modes.py

# 生成 Chinook metadata
python scripts/generate_metadata.py

# 创建演示数据库
python scripts/create_sample_dbs.py
python scripts/create_library_demo_db.py
```

## 环境变量

| 变量 | 说明 |
|---|---|
| `NL2SQL_API_KEY` / `OPENAI_API_KEY` / `DASHSCOPE_API_KEY` | LLM API 密钥（优先级从高到低） |
| `NL2SQL_BASE_URL` / `OPENAI_BASE_URL` | LLM 接口地址 |
| `NL2SQL_MODEL` / `OPENAI_MODEL` | 默认模型 |
| `NL2SQL_ANALYSIS_MODEL` | 分析阶段模型 |
| `NL2SQL_THINKING_MODEL` | 语义思考阶段模型 |
| `NL2SQL_GENERATION_MODEL` | SQL 生成阶段模型 |
| `NL2SQL_ANSWER_MODEL` | 回答阶段模型 |

DashScope 用户只需设置 `DASHSCOPE_API_KEY`，base URL 和模型自动切换。

## 项目架构

### 流水线

1. **Analysis** — 意图分类、关键词提取
2. **Analysis gate** — unsupported/irrelevant 提前终止
3. **Semantic thinking** — 解析模糊词（"热门"、"经典"）
4. **SQL generation** — LLM 优先，回退到规则+示例
5. **Validation** — sqlglot 解析 + 操作模式校验
6. **DDL confirmation** — 修改表结构前二次确认（单任务）或计划确认（复合任务）
7. **Execution** — SQLite 执行
8. **Answer** — 结果自然语言解释，失败时 LLM 诊断原因

### 复合任务

LLM 判断请求是否需要多步骤，自动分解为子任务并顺序执行。支持混合 DDL + DML。任一子任务失败立即停止。执行后自动刷新表结构摘要。

### 图片 OCR

截图 → Tesseract 本地引擎识别文字/表格 → Markdown 格式输出 → 送入流水线。支持灰度增强、放大、对比度拉伸预处理。点击上传或拖拽到页面。

### 智能模式

不再手动切换 DML/DDL。系统自动根据用户请求选择 SQL 类型（SELECT / INSERT / UPDATE / DELETE / CREATE / ALTER / DROP），DDL 操作执行前需确认。

### 目录

- `app/` — Streamlit UI、配置和编排
- `core/` — 分析、生成、校验、执行、检索、OCR
- `data/` — 原始数据库、metadata/semantic layer/examples
- `scripts/` — 数据准备和资产构建
- `tests/` — 单元测试
- `docs/` — 架构图
