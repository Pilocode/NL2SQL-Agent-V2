Spider 原始数据接入说明

将 Spider 原始数据放到当前目录下，推荐结构如下：

- tables.json
- train_spider.json
- dev.json
- database/

其中 database 目录下应包含每个 Spider 子库，例如：

- database/concert_singer/concert_singer.sqlite
- database/student_transcripts_tracking/student_transcripts_tracking.sqlite

当这些文件准备完成后，执行以下命令生成多数据库 metadata、semantic layer 和 example 语料：

python scripts/build_spider_assets.py

生成结果会输出到 data/processed/spider 下。