# NL2SQL Agent 调研结果

## 1. 调研目标

本次调研面向“自然语言转 SQL 的 Agent”建设，重点关注四类信息：

- 学术研究主线：Text-to-SQL / NL2SQL 的代表性方法和演进方向
- Benchmark 与数据集：用于建模、评测、回归测试的主流公开基准
- 开源项目与产品：已有框架、Agent、语义层方案与商用化路径
- 工程落地启发：如何把学术方法转化成一个可运行、可控、可迭代的 NL2SQL Agent

## 2. 执行摘要

当前 NL2SQL 已明显进入“LLM + Agent + 语义层 + 执行校验”的阶段。

核心结论如下：

1. 传统单次生成式 Text-to-SQL 已不足以覆盖真实企业场景。学术评测正在从 Spider 1.0 这类单轮跨域 SQL 生成，演进到 BIRD、Spider 2.0、BIRD-Interact、LiveSQLBench 这类更接近真实生产环境的长上下文、复杂 schema、多轮交互、Agent 工作流任务。
2. 纯靠“把全量 schema 扔给 LLM”通常不可扩展。工业界与最新论文都强调先做 domain scoping、schema pruning、metadata augmentation、semantic layer，再做 SQL 生成。
3. 现代高性能方法普遍不是单模型直出，而是“分解任务 + 多步推理 + 外部工具 + 自我修正”。代表路线包括 DIN-SQL 的 decomposition/self-correction、MAC-SQL/CHESS 的 multi-agent、PICARD 的 constrained decoding。
4. 工程系统里，准确率不再是唯一目标。还必须同时关注 SQL 有效性、执行效率、权限边界、可解释性、审计与成本。
5. 对当前项目而言，最值得优先建设的不是“更强的 prompt”，而是“更好的上下文选择与约束体系”。

## 3. 研究与基准演进

### 3.1 数据集 / Benchmark 主线

#### WikiSQL

- 早期大规模 Text-to-SQL 数据集，任务较简单，单表为主。
- 根据 Awesome-Text2SQL 汇总，WikiSQL 包含 80,654 个自然语言问题和 77,840 条 SQL，适合做入门训练，但对复杂 join、group by、嵌套查询等支持有限。
- 启发：适合做基础 SFT 或语法学习，不足以代表企业级真实场景。

#### Spider 1.0

来源：Yale 官方页面与原始论文页面。

- 10,181 个问题，5,693 个唯一复杂 SQL，覆盖 200 个数据库、138 个领域。
- 训练集和测试集的 SQL 模式与数据库 schema 不重合，强调对“未见 schema”的泛化能力。
- 是过去多年单轮跨域 Text-to-SQL 的核心基准。
- 2020 年后官方采用 Test Suite Accuracy 作为 Spider/SParC/CoSQL 的官方评测指标之一。
- 启发：如果你的 Agent 连 Spider 风格问题都处理不好，说明 schema linking 和 SQL 结构生成还不稳；但即便 Spider 做得很好，也不等于能落地真实企业场景。

#### SParC

来源：Yale 官方页面。

- Spider 的上下文 / 多轮版本。
- 包含 4,298 条连贯问题序列、12k+ 独立问题，覆盖同样的 200 个复杂数据库与 138 个领域。
- 重点考察多轮上下文依赖、历史问题承接、跨轮 schema/意图理解。
- 启发：如果你的系统需要 follow-up question、澄清追问或连续分析，SParC 是比 Spider 更接近真实交互的一步。

#### CoSQL

来源：Yale 官方页面。

- 对话式 Text-to-SQL 数据集。
- 30k+ turns，10k+ 标注 SQL，来自 3k 个对话，涉及 200 个复杂数据库、138 个领域。
- 与 SParC 相比，CoSQL 进一步引入了模糊问题澄清、无法回答问题、自然语言回复生成、用户对话行为预测。
- 它不只是“把多轮问题翻译成 SQL”，而是更接近完整的对话式数据库助手。
- 启发：如果你计划做真正的 Agent，而不是单轮 query translator，那么 CoSQL 的任务定义更有参考价值。

#### BIRD-SQL

来源：BIRD 官方页面。

- 全称 BIg Bench for LaRge-scale Database Grounded Text-to-SQL Evaluation。
- 包含 12,751 个唯一 question-SQL pair，95 个大型数据库，总体量 33.4 GB，覆盖 37+ 专业领域。
- 官方特别强调三个现实问题：
	- 数据值脏且格式复杂
	- 需要外部知识
	- 不仅要生成“正确 SQL”，还要考虑“高效 SQL”
- BIRD 引入了效率相关指标，如 R-VES，并持续扩展出 Mini-Dev、BIRD-Interact、BIRD-Critic、LiveSQLBench 等新方向。
- 启发：BIRD 更接近企业分析、生产数据与真实 schema；如果项目目标是“业务可用”，BIRD 比 Spider 更值得重视。

#### Spider 2.0

来源：Spider 2.0 官方页面。

- 面向真实企业级 Text-to-SQL workflow 的新一代评测框架。
- 官方说明包含 632 个真实工作流问题，数据库常包含上千列，涉及 BigQuery、Snowflake、SQLite 等多种环境；在具体 setting 中，Spider 2.0-Snow 和 Spider 2.0-Lite 各有 547 个样例，另有 Spider 2.0-DBT 68 个代码代理任务。
- 任务已明显超出“给定 schema 生成一条 SQL”的传统定义，开始要求：
	- 处理超长上下文
	- 搜索元数据和文档
	- 处理多 SQL、多步骤工作流
	- 适配多 SQL 方言
	- 在 repo / 项目级上下文中完成任务
- 官方对比给出：传统 Spider 1.0 上很强的模型，在 Spider 2.0 上成功率会大幅下降。
- 启发：如果你的目标是 NL2SQL Agent，而不是单一模型 benchmark，Spider 2.0 的任务定义最值得对齐。

### 3.2 调研中的总体趋势

从数据集演进可以看出，Text-to-SQL 正在从以下方向升级：

- 从单轮到多轮
- 从学术数据库到企业数据库
- 从中小 schema 到超大 schema
- 从“只要 SQL 正确”到“还要高效、可执行、可治理”
- 从模型能力测试到 Agent 工作流测试

## 4. 学术研究脉络

### 4.1 综述 / Survey

#### A Survey on Text-to-SQL Parsing: Concepts, Methods, and Future Directions

- arXiv:2208.13629
- 定位：总结深度学习时代的 Text-to-SQL parsing 方法，覆盖单轮、多轮数据集、预训练语言模型、典型挑战和未来方向。
- 价值：适合理解 LLM 爆发前的技术基础，包括 schema linking、decoder 设计、结构约束和泛化问题。

#### Next-Generation Database Interfaces: A Survey of LLM-based Text-to-SQL

- arXiv:2406.08426，后续被 IEEE TKDE 2025 接收。
- 定位：系统梳理 LLM-based Text-to-SQL 的挑战、数据集、评测指标与最近进展。
- 论文明确把“研究论文、benchmark、开源项目”整合到一个资源库里。
- 价值：适合快速建立“LLM 化之后 Text-to-SQL 发生了什么变化”的全局视角。

#### A Survey of Text-to-SQL in the Era of LLMs: Where are we, and where are we going?

- arXiv:2408.05109，TKDE 2025。
- 从四个维度组织 Text-to-SQL 生命周期：
	- Model
	- Data
	- Evaluation
	- Error Analysis
- 论文还给出了开发 Text-to-SQL 系统的 rule of thumb。
- 价值：对工程系统尤其有帮助，因为它不只讲模型，还讲数据和错误分析。

### 4.2 代表性方法与启发

#### SQLNet / SyntaxSQLNet / IRNet

来源：Awesome-Text2SQL 汇总。

- SQLNet 代表了 sketch-based 解码方向。
- SyntaxSQLNet 强调显式 SQL 语法结构。
- IRNet 通过中间表示降低直接生成复杂 SQL 的难度。
- 启发：把“直接出最终 SQL”改造成“先出中间结构，再翻译成 SQL”，至今仍有价值，尤其适合复杂查询和多步骤生成。

#### RAT-SQL

- arXiv:1911.04942
- 核心问题：如何在未见过的新 schema 上泛化。
- 核心做法：基于 relation-aware self-attention，把 schema encoding、schema linking、feature representation 统一建模。
- 贡献：把 schema 关系显式编码进模型结构，是 Spider 时代最重要的方法之一。
- 对 Agent 的启发：无论是否使用专门训练的 RAT-SQL，现代系统仍然必须重视“关系感知的 schema 表示”和“schema linking 质量”。

#### PICARD

- arXiv:2109.05093
- 核心问题：预训练语言模型在 SQL 这类受约束形式语言中容易生成非法 token 序列。
- 核心做法：在解码过程中做 incremental parsing，拒绝不合法 token。
- 价值：把“生成前约束”变成“生成中约束”，大幅降低无效 SQL。
- 对 Agent 的启发：即便你不复现 PICARD，也应该在生成链路中引入 SQL parser / grammar checker / AST validator。

#### DIN-SQL

- arXiv:2304.11015
- 核心问题：LLM prompting 在复杂 Text-to-SQL 任务上推理不稳定。
- 核心做法：把 Text-to-SQL 分解成更小的子问题，并加入 self-correction。
- 结果：在 Spider 和 BIRD 上都显著提升了基于 LLM 的 prompting 性能。
- 对 Agent 的启发：不要把生成过程看作一步完成，应该把它拆成子任务，例如：问题理解、schema 选择、候选 SQL、纠错、执行校验。

#### MAC-SQL

- arXiv:2312.11242
- 核心问题：在巨大数据库和复杂问题上，单个 LLM 性能显著下降。
- 核心做法：构建多 Agent 协作框架，一个 decomposer agent + 两个辅助 agent，通过外部工具或附加模型获取子数据库、修复 SQL。
- 结果：在 BIRD 上达到当时的 SOTA。
- 对 Agent 的启发：多 Agent 不一定是噱头；在大 schema、复杂问题、需要外部工具时，多角色拆分是合理路线。

#### CHESS

- arXiv:2405.16755
- 核心问题：数据库 catalog 太大、schema 太大、自然语言歧义强、查询有效性难保证。
- 核心做法：四个专职 Agent：
	- Information Retriever
	- Schema Selector
	- Candidate Generator
	- Unit Tester
- 特点：强调 schema pruning、候选迭代、以及用自然语言 unit test 验证 SQL。
- 对 Agent 的启发：现代 NL2SQL Agent 可以把“检索器、裁剪器、生成器、验证器”设计成显式模块，而不是一个超长 prompt。

### 4.3 当前研究热点

结合 survey、Awesome-Text2SQL 和最新 benchmark，当前研究热点可归纳为：

- 大 schema 下的 schema pruning / routing / domain scoping
- 多轮、多 Agent、交互式 Text-to-SQL
- 自纠错与执行反馈
- SQL 生成的效率优化，而不是只看 correctness
- 将业务语义、文档、知识库、外部知识注入 Text-to-SQL
- 隐私友好 / 可本地部署的小模型方案

## 5. 开源项目与产品调研

### 5.1 资源汇总型项目

#### Awesome-Text2SQL

- GitHub: eosphoros-ai/Awesome-Text2SQL
- 价值：不是执行框架，而是高质量入口。
- 内容覆盖：survey、classic models、datasets、leaderboards、libraries、practice projects。
- 优点：快速建立研究全景，适合持续跟踪方法与 benchmark 演进。

### 5.2 Agent / 应用型开源项目

#### DB-GPT

- 定位：Open-source agentic AI data assistant。
- 能力：连接数据库、CSV/Excel、知识库；自然语言问答；自动写 SQL 和代码；执行分析工作流；生成图表、报告、仪表板。
- 架构关键词：Agent、AWEL、RAG、skills、sandboxed execution。
- 适用场景：希望构建完整 AI + Data 应用，而不是只做 SQL 生成模块。
- 启发：如果你的项目目标会扩展到“SQL + Python + report + workflow”，DB-GPT 是值得借鉴的产品化形态。

#### Vanna

- 定位：Natural language -> SQL -> Answers，强调 production-ready 和 user-aware。
- 特点：
	- Agent 化接口
	- 用户权限贯穿系统 prompt、tool execution 和 SQL filtering
	- 自带前端组件 `<vanna-chat>`
	- 流式返回 SQL、表格、图表、自然语言总结
- 更偏“应用框架 + 企业交互层”。
- 启发：权限、审计、多租户、UI 集成不应等到后期再补，而应在架构上提前考虑。

#### SuperSonic

- 定位：融合 Chat BI 和 Headless BI 的 AI+BI 平台。
- 它的核心思想非常值得参考：
	- 用 semantic layer 给 LLM 注入业务语义
	- 把复杂 join、公式、业务指标等从 LLM 里“卸载”到语义层
- 组件包括：Knowledge Base、Schema Mapper、Semantic Parser、Semantic Corrector、Semantic Translator、Chat Memory 等。
- 启发：如果你的数据是典型 BI / 指标分析场景，语义层几乎是必要项，而不是可选项。

#### AWS Natural Language Data Retriever 示例仓库

- 定位：伴随 AWS 企业级 NL2SQL 文章的示例仓库。
- 核心思想：把 NL2SQL 拆成多个小步骤，包括预处理、命名实体 / 标识符解析、prompt 组装、SQL 执行。
- 优点：结构清晰、容易作为自研 Agent 的模板。
- 启发：这是“domain-scoped、可组合、可扩展”的典型工程实现骨架。

### 5.3 工具 / 框架型项目

#### LangChain SQLDatabaseToolkit

- 定位：给 Agent 提供 SQL 数据库相关工具集，而不是一个完整的 NL2SQL 产品。
- 典型工具：
	- list tables
	- inspect schema
	- query database
	- query checker
- 官方示例清楚展示了 Agent 如何在 SQL 执行报错后，回退到重新看 schema，再修正 SQL。
- 风险提示也很明确：模型可能生成写操作或高代价查询，数据库权限必须严格限制。
- 启发：如果你只想先做一个可编排的原型 Agent，而不是做整套产品，LangChain 是低门槛起点。

#### SQLCoder

- 定位：专注 NL2SQL 的专用模型家族。
- 卖点：在 Defog 的 sql-eval 上表现很强，强调对未见 schema 的泛化。
- 更像“模型能力底座”，而不是一个完整 Agent。
- 启发：如果后续你希望做本地化 / 私有化 / 专模路线，SQLCoder 这类模型值得纳入候选。

### 5.4 平台 / 产品型方案

#### Snowflake Cortex Analyst

- 定位：Snowflake 提供的 fully-managed、LLM-powered Text-to-SQL 服务。
- 核心差异点：Semantic Views / semantic model。
- 它明确指出：仅靠数据库 schema 无法支撑高精度 Text-to-SQL，需要业务概念、指标、关系、示例问答等语义信息。
- 优点：
	- REST API 形式，便于嵌入现有系统
	- 数据不用于跨客户训练
	- 与 Snowflake RBAC、治理、权限体系深度集成
	- 能自动选择模型组合
- 已知限制：多轮对话时不能访问前一次 SQL 的执行结果本身；长对话与意图漂移会影响效果。
- 启发：对企业环境而言，“语义模型 + 权限治理 + 托管化服务”是非常现实的路线。

#### AWS 两篇文章的工程模式

- 2024 文章偏通用 best practice：prompt engineering、fine-tuning、RAG、catalog、materialized views、monitoring、caching。
- 2025 文章偏企业级落地：domain scoping、metadata augmentation、identifier resolution、temporary views/tables、few-shot per domain、轻量模型低延迟推理。
- 启发：如果你的目标是企业场景，AWS 给出的思路比“直接选个更强模型”更务实。

## 6. 关键技术主题总结

### 6.1 Schema Linking 仍然是根问题

无论是 RAT-SQL、BIRD、SuperSonic 还是 Cortex Analyst，核心都指向同一个事实：

- 用户问题里的业务词汇，往往和数据库里的表名、列名、值域、枚举、别名并不一致。
- 如果 linking 做不好，再强的生成模型也容易 hallucinate。

因此，一个可靠的 NL2SQL Agent 至少需要：

- 表/列/值的 alias/synonym 管理
- schema 关系图或 join hints
- 指标、维度、实体等业务概念映射
- 历史问法到 schema 命中的示例积累

### 6.2 不要把问题一次性丢给模型

现代高质量方法几乎都在做 task decomposition，例如：

- 先路由 domain
- 再裁剪 schema
- 再做候选 SQL 生成
- 再做 checker / self-correction
- 最后做执行验证

这比单次超长 prompt 更稳定，也更易观测与调试。

### 6.3 语义层是企业场景的高性价比方案

语义层的价值主要体现在：

- 降低 LLM 直接理解物理表结构的负担
- 把复杂 join / metric 逻辑固化在系统内
- 让权限、业务术语和分析口径保持一致
- 提升多团队共享与治理能力

如果你的数据以分析型问答为主，这通常比单纯做 RAG 更稳。

### 6.4 执行校验和安全边界不能后补

调研中反复出现的工程要求包括：

- 只读数据库账号
- SQL parser / grammar validator
- query checker
- 超时与 LIMIT 注入策略
- 高风险关键字拦截
- 审计日志
- 用户权限透传

对 Agent 而言，这些不是“上线前补充项”，而是核心架构的一部分。

## 7. 对当前项目的落地建议

结合以上调研，如果在本项目中构建一个实用的 NL2SQL Agent，推荐优先采用下面的最小可行架构。

### 7.1 推荐的一阶段架构

#### 模块 1：问题理解与域路由

- 输入：用户自然语言问题
- 输出：
	- 业务域 / 数据域
	- 是否需要澄清
	- 候选数据源
- 作用：缩小 schema 范围，减少 prompt 长度与 hallucination

#### 模块 2：Schema / Metadata 检索

- 从 schema catalog、数据字典、注释、业务术语表、历史 SQL 中检索相关上下文
- 最终组织成“候选表、候选列、join 关系、业务规则、示例问题”的上下文包

#### 模块 3：候选 SQL 生成

- 使用 LLM 根据上下文包生成 1 到 N 条候选 SQL
- 推荐采用 decomposition prompt，而不是一步直出

#### 模块 4：SQL 校验与修正

- 语法检查
- schema existence 检查
- 只读约束检查
- 可选：模拟执行 / explain / 小样本执行
- 如果失败，回退给修正器继续生成

#### 模块 5：执行与结果解释

- 在只读连接上执行 SQL
- 返回：SQL、结果表、自然语言解释、可选图表

### 7.2 推荐的二阶段增强方向

- 增加澄清问答机制，处理模糊时间范围、指标口径、维度歧义
- 增加 semantic layer 或 metric layer
- 增加 query memory / few-shot memory
- 增加 benchmark 回放与离线评测
- 增加多 Agent 角色分工：router、retriever、generator、checker、explainer

### 7.3 不建议一开始就做的事情

- 直接端到端 fine-tune 一个大模型，跳过检索与约束层
- 在没有 benchmark 和回归集之前频繁调 prompt
- 默认允许模型执行写操作或全库扫描
- 把全量 schema 无差别塞进 prompt

## 8. 可参考的实现路线

### 路线 A：快速原型

- 编排：LangChain / 自写简单 Agent orchestration
- 检索：schema + comments + examples 的轻量检索
- 生成：通用大模型 + decomposition prompt
- 校验：SQL parser + 只读执行 + 错误重试

适合：先做 demo，尽快验证 end-to-end 流程。

### 路线 B：面向 BI / 业务分析

- 核心：semantic layer
- 参考：SuperSonic、Snowflake Cortex Analyst
- 强调指标口径、维度治理、权限控制、一致性

适合：企业分析问答、管理看板、运营 BI。

### 路线 C：面向复杂 Agent 场景

- 核心：multi-agent + tool use
- 参考：MAC-SQL、CHESS、Spider 2.0 思路
- 强调大 schema 裁剪、文档检索、多步骤 workflow、外部工具

适合：复杂数据库、异构数据源、带工作流的任务。

## 9. 对本项目最重要的结论

如果只保留最关键的几条：

1. 先做 domain scoping 和 schema retrieval，再做 SQL generation。
2. 先做可观测、可回退、可校验的链路，再谈更强模型。
3. 如果场景偏 BI，尽早考虑语义层。
4. 如果场景偏复杂企业数据库，Spider 2.0 / BIRD 比 Spider 1.0 更值得对齐。
5. 你的 NL2SQL Agent 不应被设计成“一个 prompt”，而应被设计成“一个受约束的工作流系统”。

## 10. 主要来源

### 官方 benchmark / dataset

- Spider 1.0: https://yale-lily.github.io/spider
- SParC: https://yale-lily.github.io/sparc
- CoSQL: https://yale-lily.github.io/cosql
- Spider 2.0: https://spider2-sql.github.io/
- BIRD-SQL: https://bird-bench.github.io/

### Survey / 综述

- https://arxiv.org/abs/2208.13629
- https://arxiv.org/abs/2406.08426
- https://arxiv.org/abs/2408.05109

### 代表性论文

- RAT-SQL: https://arxiv.org/abs/1911.04942
- PICARD: https://arxiv.org/abs/2109.05093
- DIN-SQL: https://arxiv.org/abs/2304.11015
- MAC-SQL: https://arxiv.org/abs/2312.11242
- CHESS: https://arxiv.org/abs/2405.16755

### 项目 / 产品 / 工具

- Awesome-Text2SQL: https://github.com/eosphoros-ai/Awesome-Text2SQL
- DB-GPT: https://github.com/eosphoros-ai/DB-GPT
- Vanna: https://github.com/vanna-ai/vanna
- SuperSonic: https://github.com/tencentmusic/supersonic
- SQLCoder: https://github.com/defog-ai/sqlcoder
- LangChain SQLDatabaseToolkit: https://docs.langchain.com/oss/python/integrations/tools/sql_database
- Snowflake Cortex Analyst: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst
- AWS 企业级 NL2SQL 文章: https://aws.amazon.com/blogs/machine-learning/enterprise-grade-natural-language-to-sql-generation-using-llms-balancing-accuracy-latency-and-scale/
- AWS Text2SQL best practices: https://aws.amazon.com/blogs/machine-learning/generating-value-from-enterprise-data-best-practices-for-text2sql-and-generative-ai/
- AWS 示例仓库: https://github.com/aws-samples/blog-natural-language-data-retrieval

## 11. 后续建议

基于本次调研，下一步最合理的动作是：

1. 先定义你这个项目的目标场景：单轮问答、BI 分析、多轮助手，还是企业级 workflow agent。
2. 根据目标场景选定第一版技术路线：轻量原型、语义层优先，还是 multi-agent。
3. 先建立一套你自己的评测集，再开始写 Agent 核心流程。