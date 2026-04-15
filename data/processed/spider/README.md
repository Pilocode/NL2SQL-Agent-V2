Spider 处理产物说明

本目录用于存放 Spider 接入后的中间资产：

- metadata/: 每个 Spider 子数据库各自的 metadata JSON
- semantic_layers/: 每个 Spider 子数据库各自的 semantic layer JSON
- examples.json: 汇总后的 Spider 训练/验证样例，用于 example RAG

当前项目会自动扫描这些文件，并将其注册为可路由数据库资源。