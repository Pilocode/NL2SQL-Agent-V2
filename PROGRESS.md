# PROGRESS

## 2026-04-13

- 初始化任务：为当前工作区开展 NL2SQL Agent 的网页调研。
- 明确产出：
  - `search_result.md`：汇总研究论文、数据集、开源项目、工业方案与实现建议。
  - `PROGRESS.md`：持续记录每一步任务进展。
- 当前状态：已确认工作区为空，正在开始外部资料检索。
- 计划中的调研方向：
  - Text-to-SQL / NL2SQL 学术研究与代表性论文
  - 常用 benchmark 与数据集
  - 开源项目与 Agent 型实现
  - 工业界产品、云厂商方案与架构实践

## 当前进展补充

- 已完成第一批搜索引擎检索，覆盖以下关键词：
  - `NL2SQL survey text-to-sql research`
  - `Spider text-to-sql benchmark`
  - `awesome text-to-sql github`
  - `enterprise nl2sql aws blog`
- 已筛出的高价值来源：
  - Spider 1.0 / Spider 2.0 benchmark 页面
  - SParC 数据集页面
  - Awesome-Text2SQL GitHub 汇总仓库
  - AWS 企业级 NL2SQL 架构文章
- 下一步：直接读取这些来源，并补充近年 survey、代表模型、开源 Agent 与工业产品资料。

## 调研来源扩展

- 已补充读取的 benchmark / dataset 来源：
  - Spider 1.0
  - Spider 2.0
  - SParC
  - CoSQL
  - BIRD-SQL
- 已补充读取的 survey / 综述来源：
  - Next-Generation Database Interfaces: A Survey of LLM-based Text-to-SQL
  - A Survey of Text-to-SQL in the Era of LLMs: Where are we, and where are we going?
  - A Survey on Text-to-SQL Parsing: Concepts, Methods, and Future Directions
- 已补充读取的代表性研究论文：
  - RAT-SQL
  - PICARD
  - DIN-SQL
  - MAC-SQL
  - CHESS
- 已补充读取的开源项目 / 产品资料：
  - Awesome-Text2SQL
  - DB-GPT
  - Vanna
  - SuperSonic
  - SQLCoder
  - LangChain SQLDatabaseToolkit
  - Snowflake Cortex Analyst
  - AWS Text2SQL / enterprise NL2SQL 相关文章与示例仓库

## 已形成的中间判断

- 学术趋势：从单轮 Text-to-SQL 逐步转向多轮、交互式、企业级、长上下文和 agentic workflow。
- 技术主线：从 schema linking / constrained decoding，演进到 decomposition、self-correction、tool use、multi-agent collaboration。
- 工程共识：纯“把全量 schema 塞给模型”不可扩展，实际系统普遍需要 domain scoping、metadata augmentation、semantic layer、execution validation 和权限控制。
- 对项目启发：自建 NL2SQL Agent 时应优先关注“检索与约束”而非单次 SQL 生成能力本身。

## 当前状态

- 学术与项目资料收集已完成。
- 正在整理 `search_result.md` 的结构化结论、来源清单和落地建议。

## 完成情况

- 已完成 `search_result.md` 编写，内容包括：
  - benchmark / dataset 主线
  - survey 与代表性论文
  - 开源项目与产品方案
  - 对当前 NL2SQL Agent 项目的架构建议
- 已完成 `PROGRESS.md` 持续记录。
- 已检查 `search_result.md` 与 `PROGRESS.md`，未发现问题。
- 尝试访问用户偏好中的外部记录路径 `d:\vscodings\RAG-Agent\WritingTutor` 以追加摘要，但该步骤未执行成功，因此本次未能同步外部 `memory.md`。

## 追加任务：课程项目设计方案

- 新目标：基于已完成调研，补充一份面向“课程大作业级别”的项目设计方案 `plan.md`。
- 新约束：后续不再尝试向任何外部项目目录写入 memory 文件；当前项目与其他项目独立。
- 当前工作：正在将评分关注点拆解为可执行方案，重点覆盖功能完整性、技术深度、系统设计和展示稳定性。

## 课程项目设计方案完成情况

- 已新增 `plan.md`，面向课程大作业场景补充了完整设计方案。
- `plan.md` 已覆盖：
  - 评分导向拆解
  - 推荐系统架构
  - 核心模块与技术亮点
  - 技术选型与目录结构
  - 演示稳定性策略
  - 评测、验收与开发阶段规划
- 已验证 `plan.md`、`PROGRESS.md`、`search_result.md`，均未发现问题。

## 追加任务：系统架构图

- 已选定 Mermaid 作为系统架构图工具。
- 选择原因：文本化、便于版本管理、适合嵌入 Markdown 和课程文档、后续迭代成本低。
- 已新增文件：`docs/system_architecture.md`。
- 架构图内容已覆盖：
  - 表现层
  - 应用编排层
  - 核心能力层
  - 数据与知识层
  - 模型与外部服务层
  - SQL 校验失败后的修正闭环
- 已完成 Mermaid 渲染校验，图稿可用于报告和答辩展示。

## 追加任务：答辩 PPT 简化图

- 已新增 `docs/system_architecture_ppt.md`，用于答辩 PPT 的简化架构图版本。
- 简化原则：减少实现细节，保留主流程、关键技术点和失败重试闭环。
- 已完成 Mermaid 渲染校验，适合直接放入 PPT 或答辩文稿。

## 追加任务：项目代码骨架与外部数据

- 已创建首版项目骨架目录：`app/`、`core/`、`data/`、`scripts/`、`tests/`。
- 已补齐演示数据库外部数据：`data/raw/chinook/Chinook_Sqlite.sqlite` 与 `data/raw/chinook/Chinook_Sqlite.sql`。
- 已新增并接通基础文件：
  - `app/config.py`
  - `app/main.py`
  - `app/orchestrator.py`
  - `app/ui.py`
  - `core/query_analyzer.py`
  - `core/schema_loader.py`
  - `core/schema_retriever.py`
  - `core/sql_executor.py`
  - `scripts/generate_metadata.py`
  - `tests/test_schema_retriever.py`
- 当前骨架目标：先打通数据加载、schema 召回、固定 demo SQL 执行，再逐步接入 SQL 生成与修正闭环。

## 依赖安装与环境修复

- 已确认当前项目使用本地虚拟环境 `.venv`，Python 版本为 3.11.9。
- 已按 pip 方式安装核心依赖：
  - `streamlit`
  - `pandas`
  - `sqlglot`
- 为运行测试，已补充安装 `pytest`。

## 数据处理与基础验证

- 已运行 `scripts/generate_metadata.py`，成功生成 `data/processed/schema_metadata.json`。
- 已准备 `data/processed/semantic_layer.json` 与 `data/processed/demo_questions.json`，作为 schema 检索和固定演示问题的数据基础。
- 已定位并修复中文召回问题：消费类问题原本只能召回 `Customer`，无法稳定召回 `Invoice`。
- 修复方式：在 `data/processed/semantic_layer.json` 中补充 `Invoice` 与 `Invoice.Total` 对“消费”的直接语义映射。
- 回归结果：`tests/test_schema_retriever.py` 已通过，当前为 2/2 测试通过。

## 当前状态

- 文档、架构图、代码骨架、基础数据和首轮检索测试已全部接通。
- 已完成最小运行验证：`NL2SQLOrchestrator` 可正常初始化，并能对“消费最高的 5 位客户是谁”返回有效分析结果。
- 当前最小运行验证结果：候选表前 3 项包含 `Invoice`、`Customer`，意图识别结果为 `ranking` + `sum`。
- 已完成 Streamlit 启动验证：应用可正常启动并暴露本地访问地址，说明 `app/main.py` 启动链路已打通。
- 下一阶段重点：
  - 继续验证 Streamlit 页面交互主流程
  - 接入结果解释与可视化展示
  - 继续补齐更稳定的演示样例与结果展示

## 追加任务：SQL 生成、校验与自动修正闭环

- 已完成 `core/sql_generator.py` 重写：新增基于演示样例复用与规则模板的 SQL 生成器。
- 当前已覆盖的规则化问题类型包括：
  - 客户消费排行
  - 国家销售额排行
  - 艺人歌曲数排行
  - 媒体类型歌曲数统计
  - 播放列表歌曲数排行
  - 年度订单统计
  - 流派平均时长排行
  - 歌曲单价排行
- 已完成 `core/sql_validator.py` 增强：
  - 拦截 `INSERT/UPDATE/DELETE/DDL` 等非只读语句
  - 保留 `SELECT` 查询白名单约束
  - 对包含 `ORDER BY` 但缺失 `LIMIT` 的查询自动补 `LIMIT 100`
- 已完成 `core/sql_repairer.py` 重写：
  - 支持 SQL 代码块清洗
  - 支持空 SQL 回退重生成
  - 支持常见 schema 错误后的安全模板重生成
- 已完成 `app/orchestrator.py` 扩展：
  - 新增 `answer_question()` 闭环入口
  - 串联 Prompt 构建、SQL 生成、校验、执行与失败修复
  - 输出包含最终 SQL、修复记录和执行结果的结构化流水线结果
- 已完成 `app/ui.py` 升级：
  - 新增“生成并执行 SQL”按钮
  - 页面可展示 Prompt、生成 SQL、校验结果、自动修复记录、最终 SQL 与执行结果表格

## 测试与运行验证更新

- 已新增 `tests/test_sql_pipeline.py`，覆盖：
  - 端到端客户消费问题执行
  - 只读校验拦截写操作
  - 排序查询自动补 `LIMIT`
- 全量测试结果：`pytest` 共 5 项，当前为 5/5 通过。
- 已完成闭环运行验证：问题“每种媒体类型有多少首歌曲”可成功生成 SQL、通过校验并返回查询结果。
- 已再次完成 Streamlit 启动验证，说明新增闭环逻辑未破坏页面启动链路。

## 追加任务：运行 UI 并进行人工调试

- 已启动 Streamlit UI，并在浏览器中对主流程和固定演示面板进行人工交互验证。
- 人工调试中发现两个真实问题：
  - 空输入时仍可能回退到示例 SQL 并执行，容易产生误导性结果。
  - 页面发生 rerun 后，左侧分析结果和执行结果容易丢失，交互稳定性不足。
- 已完成修复：
  - 在 `app/orchestrator.py` 中增加空问题保护，空输入时直接返回失败状态，不再执行示例 SQL。
  - 在 `app/ui.py` 中引入 `st.session_state`，持久化分析结果、运行结果、demo 执行结果和提示消息。
  - UI 现在会在空输入时给出明确 warning，并在右侧操作后保留左侧主流程结果。
- 修复后验证结果：
  - 空输入点击“生成并执行 SQL”时，页面会提示“请输入自然语言问题后再执行”。
  - 输入“每年有多少笔订单”后，主流程可稳定生成并执行 SQL。
  - 继续点击右侧“执行演示 SQL”后，左侧主流程结果仍会保留，说明状态管理修复生效。

## 追加任务：增强分析能力、接入 LLM 多 agent、重构 chat UI

- 已完成 `core/query_analyzer.py` 重写：
  - 基于 semantic layer 抽取关键词、指标提示、实体提示、时间粒度和 top-k。
  - 对“最多/最少”这类隐式计数问题补充 `count` 意图识别。
- 已完成 `core/schema_retriever.py` 增强：
  - 召回时可利用 `metric_hints`、`entity_hints`、`time_grain` 和 `top_k` 做语义加权。
- 已新增 `core/llm_client.py`：
  - 支持 OpenAI 兼容接口调用。
  - 通过环境变量 `NL2SQL_API_KEY` / `OPENAI_API_KEY`、`NL2SQL_BASE_URL` / `OPENAI_BASE_URL`、`NL2SQL_MODEL` / `OPENAI_MODEL` 控制。
- 已新增 `core/multi_agent.py`：
  - `SQLGenerationAgent`：优先使用 LLM 生成 SQL，失败时回退到本地规则与样例。
  - `SQLRepairAgent`：优先使用 LLM 做 SQL 修复，失败时回退到本地规则修复。
  - `AnswerAgent`：优先使用 LLM 解释结果，失败时回退到本地解释器。
- 已新增 `core/result_explainer.py`，用于无 LLM 时生成自然语言回答。
- 已完成 `app/orchestrator.py` 重写：
  - 以 supervisor 方式串联 analysis agent、generation agent、repair agent、answer agent。
  - 在响应中保留 `agent_traces`，便于 UI 折叠展示调试信息。
- 已完成 `core/prompt_builder.py` 改造：
  - 分离 SQL 生成 prompt、SQL 修复 prompt、结果解释 prompt。
- 已扩充 `data/processed/semantic_layer.json`：
  - 新增更多表别名、字段别名和指标模板。
- 已扩充 `data/processed/demo_questions.json`：
  - 样例数从原始演示集扩到更丰富的聚合、排行、过滤和时间类问题。
- 已扩充 `core/sql_generator.py` fallback 规则覆盖范围：
  - 新增国家/城市客户数、艺人专辑数、客服负责客户数、平均消费、最长歌曲、年份过滤、空值筛选等模式。
- 已完成 `app/ui.py` 重构：
  - 页面从按钮式分析面板改为 chat 界面。
  - 用户只需输入自然语言问题，主区直接返回答案和结果表。
  - SQL、Schema、Prompt、修复记录、Agent Trace 收纳到右侧折叠详情面板。
- 已补充测试：
  - 新增 `tests/test_query_analyzer.py`
  - 更新 `tests/test_sql_pipeline.py` 验证 `answer_text` 与 `agent_traces`
- 当前测试结果：`pytest` 共 7 项，当前为 7/7 通过。
- 已完成新版 UI 人工验证：
  - chat 界面可正常输入并回答问题。
  - 问题“客户最多的 5 个国家有哪些？”已验证可返回正确结果。
  - 右侧折叠详情面板可正常展开查看 SQL 生成来源、最终 SQL 与 agent trace。

## 追加任务：接入真实模型提供方并打通 LLM 路径

- 已在外部项目中定位到实际模型接入方式：
  - 提供方为阿里云百炼 DashScope 兼容接口。
  - 当前环境变量中已存在 `DASHSCOPE_API_KEY`。
  - 外部示例脚本默认使用 `https://dashscope.aliyuncs.com/compatible-mode/v1`。
- 已完成当前项目配置改造：
  - `app/config.py` 现在会自动优先复用 `DASHSCOPE_API_KEY`。
  - 未显式指定模型时，会默认使用 `qwen3.5-flash-2026-02-23`。
  - 对 DashScope 路径默认开启 `enable_thinking`。
- 已完成 `core/llm_client.py` 增强：
  - 支持 DashScope/Qwen 的 `extra_body.enable_thinking`。
  - 更稳健地处理返回内容格式。
- 已将 `enable_thinking` 配置透传到 orchestrator 的真实 LLM 客户端初始化中。
- 已完成真实调用验证：
  - 当前配置下 `settings.llm_base_url` 为 DashScope 兼容地址。
  - 当前配置下 `settings.llm_model` 为 `qwen3.5-flash-2026-02-23`。
  - `generation_agent` 已实际命中 `llm` 策略。
  - `answer_agent` 已实际命中 `llm` 策略。
- 已完成回归验证：`pytest` 共 7 项，当前为 7/7 通过。
- 已完成 UI 侧验证：新版页面右侧已显示“LLM 状态：已启用”。

## 追加任务：为模糊语义增加 thinking 层，并优化各层 LLM 调用效率

- 已完成 `core/models.py` 扩展：
  - 为 `QueryAnalysis` 增加 `ambiguous_terms`。
  - 新增 `SemanticInterpretation`，用于承载 thinking 层对模糊问题的解释结果。
- 已完成 `core/query_analyzer.py` 增强：
  - 可显式识别“火 / 最火 / 热门 / 经典 / 受欢迎 / 最好 / 最差”等模糊词。
- 已完成 `core/prompt_builder.py` 扩展：
  - 新增 `build_thinking_prompt()`，专门让 thinking agent 输出结构化 JSON 语义解释。
  - 生成与修复 prompt 现在会接收并利用 `semantic_interpretation`。
- 已完成 `core/llm_client.py` 重构：
  - 底层从手写 HTTP 调用切换为官方 `openai` 兼容 SDK。
  - 新增 `LLMProfile`，实现按角色区分模型、token 上限、温度和 thinking 开关。
  - 当前策略：thinking 层保留 reasoning，生成/修复/回答层使用更轻的非 thinking 配置以提速。
- 已完成 `core/multi_agent.py` 重写：
  - 新增 `SemanticThinkingAgent`，先把模糊问题重写成明确业务语义，再交给 SQL 生成层。
  - thinking 失败时仍会回退到本地模糊语义解释规则。
- 已完成 `app/orchestrator.py` 增强：
  - 在 analysis 后增加 thinking 步骤。
  - 若问题被重写，则会基于重写问题进行二次分析、二次 schema 召回和二次示例匹配。
- 已完成 `core/sql_generator.py` 增强：
  - 支持消费 `semantic_interpretation` 的重写问题。
  - 新增“热门/最火专辑”规则，将热度默认解释为购买次数优先、销售额次之。
- 已扩充 `data/processed/demo_questions.json`：
  - 新增“销量最高的 5 个专辑”样例，避免模糊热度问题被错误示例带偏。
- 已更新 `requirements.txt`：新增 `openai>=1.76,<2.0`。
- 已补充回归测试：
  - `tests/test_query_analyzer.py` 新增模糊词识别测试。
  - `tests/test_sql_pipeline.py` 新增“最火的 5 个专辑”端到端回归测试。
- 当前测试结果：`pytest` 共 9 项，当前为 9/9 通过。
- 已完成真实模型验证：
  - 问题“帮我查一下最火的5个专辑”可由 thinking LLM 先解释为销量语义。
  - 之后 generation agent 使用 LLM 生成基于 `Album + Track + InvoiceLine` 的销售 SQL。

## 追加任务：将 query_analyzer 从硬编码改为 agent 主导

- 已完成分析阶段重构：
  - 新增 `QueryAnalysisAgent`，由 LLM 优先输出 `QueryAnalysis` 所需的结构化语义槽位。
  - 当前 analysis agent 会覆盖 `tokens`、`intent_tags`、`metric_hints`、`entity_hints`、`ambiguous_terms`、`time_grain`、`top_k`、`is_follow_up`。
- 已调整主流程编排：
  - `app/orchestrator.py` 不再直接依赖硬编码 `query_analyzer` 作为主分析入口。
  - 当前链路改为：`analysis agent -> schema retrieval -> thinking agent -> generation/repair/answer agents`。
  - 如果 thinking 改写了问题，会再次通过 analysis agent 对改写后的问题重新分析并刷新召回。
- 已保留稳定性兜底：
  - 原 `core/query_analyzer.py` 仍保留为 fallback analyzer，仅在 LLM 不可用或 analysis JSON 解析失败时接管。
  - 这样可以避免完全依赖硬编码，同时保证离线测试和无 key 场景可运行。
- 已完成 prompt 与配置补充：
  - `core/prompt_builder.py` 新增 `build_analysis_prompt()`，让 analysis agent 可以结合领域语义自由理解问题，而不是机械关键词匹配。
  - `app/config.py` 新增 `llm_analysis_model` 配置，支持单独为分析层指定模型。
- 已完成回归验证：
  - 更新测试以兼容新的 analysis agent 配置。
  - 当前 `pytest` 共 9 项，结果为 9/9 通过。

## 追加任务：为慢查询增加阶段输出，并在最终回答中展示 SQL

- 已完成交互链路增强：
  - `app/orchestrator.py` 新增阶段化输出能力，按分析、语义解释、召回刷新、SQL 生成、校验、修复、执行、结果解释逐步返回阶段消息。
  - `core/models.py` 新增 `StageUpdate`，并在 `NL2SQLResponse` 中保留完整阶段记录。
- 已完成前端展示改造：
  - `app/ui.py` 现在会在查询执行过程中逐阶段输出提示，而不是长时间无反馈。
  - 每个阶段完成后都会在 chat 区立即显示阶段性进展。
  - 最终回答中会追加展示 `最终 SQL`，用于直观体现 NL2SQL 效果。

## 追加任务：优化阶段提示样式，并补充数据介绍卡片

- 已完成阶段提示样式优化：
  - `app/ui.py` 为阶段提示新增自定义样式，不再使用简单列表。
  - 现在阶段进展会以连续聊天气泡样式显示，并高亮当前最新阶段。
- 已完成数据介绍卡片：
  - 在右侧详情区新增可折叠的“数据介绍”格子。
  - 内容基于 `schema_metadata.json` 动态提炼，包含数据主题、数据库类型、表数量、总记录量、常用核心表、常见分析对象和常见查询指标。
- 已完成运行验证：
  - `app.ui` 导入验证通过。
  - 页面重启后已可看到新的“数据介绍”折叠项。

## 追加任务：落地 Spider 多库骨架与 example RAG

- 已完成多数据库代码骨架：
  - `app/config.py` 新增 Spider 相关路径与 `enable_spider_rag` 开关。
  - `core/models.py` 新增 `DatabaseProfile`、`RoutedDatabase`，并为 `ExampleCandidate` 增加 `database_id` 与 `source`。
  - `core/database_registry.py` 新增数据库注册中心，当前默认注册 Chinook，并支持自动扫描 `data/processed/spider/metadata` 与 `data/processed/spider/examples.json` 中的 Spider 资源。
  - `core/database_router.py` 新增库级路由器，用于在多个数据库之间做问题路由。
- 已完成 Spider example RAG 骨架：
  - `core/example_retriever.py` 新增分库样例检索器，只会在当前路由数据库内检索 example，避免跨库污染。
  - `app/orchestrator.py` 已改为“先库路由，再按数据库加载 analysis/schema/example/generation/repair 组件”。
  - `core/sql_generator.py` 现在仅对 Chinook 使用规则模板；非 Chinook 数据库会优先走 LLM 与 example RAG。
- 已完成 Spider 资产构建脚本：
  - 新增 `scripts/build_spider_assets.py`，可在 Spider 原始数据就位后自动生成分库 metadata、semantic layer 和 examples 语料。
  - 新增 `data/raw/spider/README.md` 与 `data/processed/spider/README.md`，说明原始数据与处理中间产物的目录约定。
- 当前运行状态：
  - 项目现在仍默认可稳定运行 Chinook。
  - 当 Spider 原始数据与处理产物补齐后，可直接启用分库路由与 Spider example RAG。
- 已完成回归验证：
  - 新增 `tests/test_database_router.py` 与 `tests/test_example_retriever.py`。
  - 全量 `pytest` 当前为 12/12 通过。

## 追加任务：为摘要增强补充离线评测，并写入进度文档

- 已新增三级摘要驱动的小型 schema retrieval 评测集：
  - 新增 `data/evals/retrieval_summary_benchmark.json`，当前包含 8 条本地库问题，覆盖 `sales`、`hr`、`books` 三个导入示例库。
  - 样本刻意偏向“自然语言业务表述”，例如“销售流水情况”“员工薪资情况”“图书销量排名”，用于衡量三级摘要对英文表名/字段名数据库的召回增益。
- 已新增可复跑评测脚本：
  - 新增 `scripts/evaluate_retrieval_summary.py`。
  - 脚本会分别跑两套链路：
    - `baseline`：去掉 `database_summary / table_descriptions / column_descriptions / summary_terms`，模拟未接入摘要增强的召回。
    - `enhanced`：保留三级摘要与摘要词项，评估当前增强后的召回效果。
  - 指标输出为 `Top-1 / Top-3 / Top-5` 命中率，并附每条 case 的 Top-5 候选表和命中名次。
- 已完成一次实际评测并记录结果：
  - 运行命令：`python scripts/evaluate_retrieval_summary.py`
  - 当前小型评测集结果：
    - `baseline`：Top-1 = `0/8 = 0.0000`，Top-3 = `1/8 = 0.1250`，Top-5 = `1/8 = 0.1250`
    - `enhanced`：Top-1 = `8/8 = 1.0000`，Top-3 = `8/8 = 1.0000`，Top-5 = `8/8 = 1.0000`
  - 说明三级摘要已不只是 UI 展示，而是对本地导入库的 schema retrieval 产生了可量化提升。
- 已针对评测结果补强 analyzer 词表：
  - 在 `core/query_analyzer.py` 中补充了 `图书 / 书籍 / 书名 / 作者 / 销量 / 销售 / 流水 / 薪资 / 工资 / 部门` 等业务词，避免中文问题在本地英文 schema 库上过度依赖表名直译。
- 当前验证状态：
  - 相关测试集 `tests/test_schema_retriever.py`、`tests/test_local_db_assets.py`、`tests/test_sql_pipeline.py`、`tests/test_database_router.py`、`tests/test_example_retriever.py` 当前为 `11/11` 通过。

## 追加任务：支持 DDL / DML 双模式数据库操作

- 已完成共享操作模型扩展：
  - `core/models.py` 新增 `query / dml / ddl` 三种 operation mode 常量。
  - `PipelineResult`、`ValidationResult`、`QueryExecution`、`NL2SQLResponse` 现在都会保留当前操作模式与语句类型，便于 UI 和后续调试使用。
- 已完成 SQL 校验与执行层改造：
  - `core/sql_validator.py` 现在会先识别语句类型，再按模式限制可执行范围：`query` 仅允许 `SELECT`，`dml` 允许 `SELECT/INSERT/UPDATE/DELETE`，`ddl` 允许 `CREATE/ALTER/DROP`。
  - `core/sql_executor.py` 新增统一 `execute()`，可执行查询、写入和结构变更；同时修复了 SQLite 连接在 Windows 下未显式关闭导致临时库文件被锁的问题。
  - `core/result_explainer.py` 已补齐非查询语句的自然语言解释，可直接回答“影响多少行数据”或“数据库结构已变更”。
- 已完成 prompt、agent 与编排层改造：
  - `core/prompt_builder.py`、`core/query_analyzer.py`、`core/multi_agent.py` 现在均按 operation mode 生成提示词、识别 `insert/update/delete/create/alter/drop` 意图，并抽取对应 SQL。
  - `app/orchestrator.py` 已把 operation mode 贯穿到 analysis、thinking、generation、validation、repair、execution、answer 全链路；对 DDL 和显式写操作会跳过不必要的 thinking 改写。
- 已完成 UI 双模式切换：
  - `app/ui.py` 顶部新增 `DML / DDL` 模式切换与模式徽标。
  - 切换模式或切换数据库时会自动清空旧对话，避免把查询上下文误带到建表/写入场景。
  - 输入框占位文案、欢迎语和“使用建议”示例会按模式动态变化。
  - 仅在 `SELECT` 场景渲染结果表格，写操作和 DDL 则展示文本化执行结果，避免空表格误导。
- 已补充轻量验证：
  - 新增 `tests/test_operation_modes.py`，覆盖 DML 插入执行、DDL 建表执行以及 validator 的模式边界。
  - 回归 `tests/test_sql_pipeline.py` 后通过。
  - 全量测试结果：`pytest` 共 `17` 项，当前为 `17/17` 通过。

## 追加任务：让“当前库表结构摘要”随表结构变更自动刷新

- 已定位根因：
  - 右侧“当前库表结构摘要”读取的是本地 metadata / semantic layer 文件，并受 `schema_loader` 的 LRU 缓存影响。
  - 之前只有导入数据库、切库或手动点击“刷新数据库列表”时才会重建这些资产；执行 `INSERT/UPDATE/DELETE/CREATE/ALTER/DROP` 后不会自动同步，所以摘要可能落后于真实库结构。
- 已完成修复：
  - `core/local_db_assets.py` 新增 `refresh_local_database_assets()`，会在不丢失已有数据库简介、表简介、字段角色简介的前提下，重新扫描当前 SQLite 数据库的实时表结构、字段和行数，并更新 metadata / semantic layer。
  - `app/ui.py` 现在会在本地数据库执行成功且语句类型不是 `SELECT` 时，自动触发资产刷新并清空 schema loader 缓存。
  - 执行完成后，右侧“数据资源”区域会出现提示：`已根据最新 SQL 执行结果刷新 ... 的库表结构摘要`。
- 已完成验证：
  - 新增 `tests/test_local_db_assets.py` 回归用例，覆盖“先建资产，再插入数据/新增表，然后刷新资产后应立即反映最新行数和表结构”。
  - 全量 `pytest` 结果已更新为 `18/18` 通过。
  - 在运行中的 Streamlit 页面上已实际验证：对 `library_demo` 执行 `ALTER TABLE Student ADD COLUMN Age INTEGER DEFAULT 18` 后，页面提示摘要已刷新，数据库和最新 metadata 中均已出现 `Student.Age` 字段。

## 追加任务：将自动摘要刷新扩展到默认 Chinook 等非本地 SQLite 数据库

- 已完成刷新能力抽象：
  - `core/local_db_assets.py` 新增通用 `refresh_database_assets()`，不再只限定本地导入库。
  - 该函数会在刷新实时表结构和行数时，保留已有 `source`、`table_aliases`、`column_aliases`、`metric_templates`、examples 等现有资产配置，避免把 Chinook 的既有语义层覆盖掉。
  - 原 `refresh_local_database_assets()` 现在退化为对通用刷新函数的本地库包装。
- 已完成 UI 接入：
  - `app/ui.py` 现在对任意 SQLite 数据库都会在成功执行非 `SELECT` SQL 后自动刷新摘要资产，不再只对 `data/local_dbs/` 下的库生效。
  - 因此默认 Chinook 这类内置 SQLite 库，在执行写操作或 DDL 后也会自动同步“当前库表结构摘要”。
- 已补充验证：
  - `tests/test_local_db_assets.py` 新增一条“非本地 SQLite 资产刷新”回归测试，模拟 Chinook 风格的 metadata / semantic layer / examples 文件，并验证刷新后仍保留语义别名和指标模板。
  - 全量 `pytest` 结果已更新为 `19/19` 通过。
  - Streamlit 已重启到最新版本，当前本地访问地址仍为 `http://localhost:8501`。
