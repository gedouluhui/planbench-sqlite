# PlanBench SQLite

**给查询加索引，先确认答案没变，再看 SQLite 走了哪条路。**

本工具把同一 SQLite 快照复制成两个临时数据库，对比原查询与候选查询／索引，检查结果是否一致，并生成可直接打开、无外部依赖的 HTML 报告。无需 API key、服务器或第三方运行时包。

## 直接体验

需要 Python 3.11+（含 SQLite）。在项目目录安装并运行：

```sh
python -m pip install .
planbench-sqlite demo --out demo-output
```

打开 `demo-output/report.html`。演示数据库由程序确定性生成，不下载、不使用私人数据。输出目录必须是新目录，避免覆盖已有文件。

```sh
planbench-sqlite compare demo-output/different.json
planbench-sqlite compare demo-output/limited.json
```

第一条故意修改查询条件，退出码为 1，结果不同；第二条故意耗尽行数预算，退出码为 2，只能判定“无法确认”，不能把截断的相同前缀当成结果一致。

## 用于自己的数据库

参照 [英文 README](README.md) 的 JSON 格式，填写数据库相对路径、两个 SELECT、位置参数，以及候选方案的普通索引。然后运行：

```sh
planbench-sqlite compare case.json --json report.json --html report.html
```

数据库路径相对于配置文件，不是命令所在目录。已有报告默认拒绝覆盖；`--force` 也不能覆盖输入数据库、配置文件及 SQLite 侧文件。

| 状态 | 退出码 | 含义 |
|---|---:|---|
| equivalent | 0 | 两边完整执行，列名／列数与指定方式下的类型化结果一致 |
| different | 1 | 两边完整执行，但列结构、值、重复次数或要求的顺序不同 |
| inconclusive | 2 | 有一边失败、被拒绝或耗尽预算，不能判断一致 |

`ordered` 比较完整行序列；`multiset` 忽略顺序但保留重复次数。整数 1、实数 1.0、文本 '1' 与字节串不是同一种结果。报告中的哈希只用于留档，不作为相等判据。

## 为什么不直接看一次耗时

进度回调次数不等于精确 VM 指令数；开启观测会增加开销。报告中的耗时包含观测和结果编码，不代表生产环境加速。执行计划的文本会随 SQLite 版本改变，不能仅凭 SCAN／SEARCH 字样自动评优。

这个工具的增量是“同快照、两方案、真实执行、完整结果核对、可分享报告”的完整流程，而不是新数据库算法，也不替代 SQLite CLI、sqlite-utils 或 Datasette。

## 必须知道的边界

- 只针对可信本地普通 SQLite 数据库，不是恶意数据库／SQL 的进程沙箱。资源限制是协作式的，不承诺硬墙钟或进程峰值内存上限。
- 源库以只读方式打开，候选索引只建在临时副本上；SQLite 在读取 WAL 时仍可能管理共享内存侧文件。
- 相同结果只证明这一快照、这一组参数下相同，不证明所有数据上 SQL 等价。无序 LIMIT、相同排序键和顺序敏感聚合可能因索引改变结果。
- 不支持虚表、扩展、用户自定义函数、非有限 REAL 或任意 DDL。未知函数默认拒绝。
- 报告不含结果行和绑定参数，但包含 SQL 文本、SQL 中的字面量、标识符与数据库文件名。分享前请自行审查这些内容。
- 当前是早期开发者工具；没有把本机测试包装成生产性能、真实用户或星数保证。

开发测试：`python -m unittest discover -s tests -v`。详见 [精确契约](docs/CONTRACT.md)。代码与自制演示数据采用 MIT；开发由 AI 辅助，正确性以可复跑证据为准。
