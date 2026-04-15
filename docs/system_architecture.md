# NL2SQL Agent 系统架构图

## 绘图工具选择

本项目选用 Mermaid 作为架构图工具，原因如下：

- 文本化存储，适合和课程项目代码一起纳入版本管理
- 修改成本低，后续迭代模块时不需要重画图片
- 可以直接嵌入 Markdown，便于写报告和答辩材料
- 对当前这种分层架构和流程闭环表达非常合适

## 系统架构图

```mermaid
flowchart LR
    user[用户]
    ui[Web UI<br/>Streamlit]

    subgraph app[应用编排层]
        orchestrator[Agent Orchestrator<br/>查询流程编排]
        memory[Conversation Context<br/>多轮上下文与查询历史]
        logger[Logs and Metrics<br/>日志与观测]
    end

    subgraph core[核心能力层]
        analyzer[Query Analyzer<br/>问题理解]
        retriever[Schema Retriever<br/>Schema 检索与裁剪]
        mapper[Semantic Mapper<br/>业务术语映射]
        builder[Prompt Builder<br/>上下文构造]
        generator[SQL Generator<br/>候选 SQL 生成]
        validator[SQL Validator<br/>AST 与安全校验]
        repairer[SQL Repairer<br/>错误修正]
        executor[SQL Executor<br/>查询执行]
        explainer[Result Explainer<br/>结果解释与图表建议]
    end

    subgraph data[数据与知识层]
        db[(Demo Database<br/>SQLite or DuckDB)]
        metadata[(Schema Metadata<br/>表字段注释/别名)]
        semantic[(Semantic Layer<br/>指标/维度/同义词)]
        examples[(Few-shot Examples<br/>问答样例库)]
    end

    subgraph model[模型与外部服务]
        llm[LLM Adapter<br/>统一模型接口]
    end

    user --> ui
    ui --> orchestrator
    orchestrator <--> memory
    orchestrator --> analyzer
    analyzer --> retriever
    analyzer --> mapper
    retriever --> metadata
    mapper --> semantic
    retriever --> builder
    mapper --> builder
    builder --> examples
    builder --> generator
    generator --> llm
    llm --> generator
    generator --> validator
    validator -->|通过| executor
    validator -->|失败| repairer
    repairer --> builder
    executor --> db
    db --> executor
    executor --> explainer
    explainer --> orchestrator
    orchestrator --> ui
    orchestrator --> logger
    validator --> logger
    executor --> logger
```

## 图中重点说明

### 1. 不是单次直出 SQL

系统不是“问题直接丢给模型”，而是先经过：

- 问题理解
- schema 检索
- 语义映射
- prompt 构造
- SQL 校验
- 执行反馈修正

这体现了项目的技术深度。

### 2. 校验与修正形成闭环

SQL Validator 失败后不会直接结束，而是进入 SQL Repairer，再回到 Prompt Builder 和 SQL Generator 继续修复。这是系统稳定性的关键设计。

### 3. 数据层不是只有数据库

除了数据库本身，系统还依赖：

- Schema Metadata
- Semantic Layer
- Few-shot Examples

这三部分共同构成“不是纯 API 调用”的核心上下文系统。

### 4. 适合课程展示

这张图同时体现了：

- 分层架构
- 核心模块
- 数据流闭环
- 错误恢复机制

非常适合直接放进课程报告或答辩 PPT。