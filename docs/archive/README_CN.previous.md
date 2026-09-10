> 旧版中文译文，保留你的原始工作。此处的 100 条标注要求已不再是当前必做任务。请从根目录 README_CN.md 开始。以下旧译文中的相对链接按原先的仓库根目录解释。

# 上下文感知的实体消歧与 LLM 生成知识的事实性审计

**研究原型作者：Yifan Li · 计算机科学硕士 · 德累斯顿工业大学（TU Dresden）**

关系上下文（relational context）是否有助于区分*作为行星的 Mercury（水星）*与*作为化学元素的 mercury（水）*？
当 LLM 对生成的某条事实做出判断时，其决策是否与阅读相同证据的人类保持一致？
本项目通过明确的候选集、版本化的提示词（prompts）、可追溯的证据链以及可复现的评估流程，使上述问题变得可测试。

**当前状态：研究基础设施已实现并完成测试；人类验证及付费实验待开展。**
科学 MVP（最小可行性产品）**尚未完成**：现有 40 个已完成来源核查的实体案例**草案**、113 条待评审的公开 KB（知识库）断言，以及 **0 个人类验证案例 / 0 个人类标注标签**。目前尚未调用任何付费 LLM 服务。绝不能将 Mock（模拟）输出作为模型性能的依据。

## 立项动机与相关工作

[Hu 等人 (ACL 2025)](https://aclanthology.org/2025.acl-long.789/) 提出了将事实性知识诱导提取为三元组（triples）的动机，从而实现了超越预选问答任务的深层分析。[GPTKB 2.0 构建工作](https://arxiv.org/abs/2608.03729v3) 解决了规范化（canonicalization）和实体歧义问题；其[审计 Demo](https://arxiv.org/abs/2608.06992v2) 揭示了实体消歧决策的出处与出处追溯（provenance）。[Giordano 与 Razniewski](https://arxiv.org/abs/2605.26937v2) 推动了开放知识评估的发展。本项目研究的是该议题中一个具有明确边界的子模块。
**本项目是一项外部 Wikidata 链接实验，并非对 GPTKB 内部规范化或百万级构建规模的复现。** 参考文献见：[references.bib](https://www.google.com/search?q=docs/references.bib)。

## 研究问题（Research Questions）

1. 相比于仅基于字符串（strings alone），上下文能否提高 Top-1 实体链接（entity linking）的准确率？
2. 它能否有效区分同音/同形异义词（homonyms），并正确合并同义提及（synonymous mentions）？
3. 基于证据（evidence-grounded）的裁判模型（judge）能否区分蕴涵（entailed）、矛盾（contradicted）和支持证据不足（insufficiently supported）的断言？
4. 裁判模型的决策与独立的人类标注（human annotations）之间的一致性如何？
5. 在准确率（accuracy）、覆盖率（coverage）、时延（latency）、Token 消耗、成本（cost）以及输出有效性（output-validity）之间存在怎样的权衡（trade-offs）？

## 运行离线 Demo

环境要求：Python 3.11+；本地检查基于 Python 3.12 完成。
项目中提交的 `uv.lock` 锁定并固定了直接与间接（transitive）依赖项。

```bash
uv sync --frozen --extra dev --extra plots
source .venv/bin/activate
pytest
ruff check .
mypy src
llmka validate-data --config configs/mock.yaml
llmka run-all --config configs/mock.yaml

```

安装过程需要一次网络访问以获取依赖包。安装完成后，Mock 运行**既不需要 API Key，也不需要任何网络连接**。测试套件通过 `pytest-socket` 拦截并禁用了 Socket 连接。如果使用 pip，请运行：`python -m pip install -e '.[dev,plots]'`（使用兼容的版本区间；如需精确复现请使用 lockfile）。
请在项目根目录下执行命令。YAML 中的配置路径是相对于仓库根目录解析的，而非终端的工作目录。[scripts/](https://www.google.com/search?q=scripts/) 中的 Shell 脚本为便捷包装工具。

命令行界面（CLI）会输出一个新的 `results/mock/<run-id>/` 目录。请打开其中的 `report.md` 和 `evaluate.json`。该目录还包含各阶段产物（stage artifacts）、清单（manifest）、遥测数据（telemetry）、检查点（checkpoints）以及双盲标注包（blinded annotation packet）。
一次干净的 Demo 运行目前会在 29 个已消歧实体的并集中生成 145 条合成三元组。这些均属于桩数据断言（fixture claims，例如 `demo_value=alpha`），**并非断言为真实世界的真实事实**。Mock 消歧器（resolver）基于词汇重叠（lexical overlap）机制，并非 LLM。所有 Mock 的时延/Token/成本计数器均硬编码定义为 0；请勿将测量到的系统运行速度视为模型性能。[已保存的 Demo 报告](https://www.google.com/search?q=docs/mock_demo/report.md)。

## 数据与方法

数据草案包含 20 个同音/同形异义词案例（10 对）和 20 个同义词案例（10 对），覆盖 30 个规范实体（canonical entities）和 9 个领域。所有 QID 的标签/描述均检索自 Wikidata。在完成人类验证之前，Gold 字段（标准答案）仅作为拟定的目标值。每条记录均保留了其来源 URL 和检索时间。详见[数据卡（data card）](docs/data_card.md)和[评审说明](data/benchmark/README.md)。

本项目刻意区分并隔离了两种候选源（Candidate Sources）：

* **受控 Mock 桩数据（Controlled mock fixture）**：一个由元数据支撑的小型候选池，专门用于测试。
* **公开搜索快照（Public search snapshot）**：实际的 `wbsearchentities` 排序结果，补充了别名与描述信息。标准答案 ID（Gold IDs）绝不会被硬编码插入其中。来源核查显示，在 40 个草案案例中，有 38 个的拟定实体位于搜索结果的前十名；这属于临时性的数据集收集检查，并不代表经过验证的基准召回率（verified benchmark recall）。

字符串基线（string baseline）仅能感知表层形式（surface form）以及候选标签/别名。其排序由 NFKC 规范化、大小写折叠（case folding）、标点符号规范化以及 RapidFuzz 相似度计算共同决定。对于精确同分（exact ties）的情况，使用 QID 的字典序进行打破。上下文和描述信息无法传入其类型化的输入中。
上下文方法（context method）则将表层形式、独立撰写的上下文、来源三元组以及候选元的元数据一并发送至可配置的 Provider。它仅接受候选 QID 或 null，并附带有限的置信度和简短的理由（rationale）。系统设置了阈值以支持弃权（abstention）。两种方法均不会接收到 Gold 字段。

### 流水线架构（Pipeline）

```text
草案/已评审案例 → Wikidata 候选元 → 字符串 + 上下文消歧
                                        ↓
                       实际消歧出的规范实体的并集
                                        ↓
                    经过 Schema 校验的生成 → 去重
                                        ↓
                     规范维基百科 Sitelink → 排序后的 API 段落
                                        ↓
                      仅基于证据的裁判 → 双盲人类评审
                                        ↓
                           指标计算 → 错误分析 → 报告生成

```

对于每个规范实体，知识生成步骤仅执行一次，并链接到每个产生该实体的消歧方法/案例。这避免了重复生成，并使得基于方法条件的审计具备可追溯性。实体链接与事实真伪是解耦的：关于错误语义（wrong sense）的正确三元组，不能算作联合成功（joint success）。
当前 MVP 仅对规范的主体（subject）进行审计；生成的客体提及（object mentions）不会单独进行实体链接。

维基百科证据通过官方 API 获取，使用的是所选 QID 对应的英文 sitelink、修订 ID（revision IDs）、串行请求、显式超时设置、仅限瞬态错误的重试、速率限制以及原始响应缓存。完整段落会在字符预算限制内完成去重与筛选。缺失证据将直接判定为 NEI（信息不足）；格式错误的输出或模型拒绝回答均视为失败（failure），绝不会隐式转换为有效判定。
证据冲突已包含在裁判模型的提示词指令和合成测试集中；语义层面的冲突检测仍依赖于裁判模型和人类评审。已实现兼容 OpenAI 的 JSON-schema 请求格式；Provider 的兼容性已完成传输层测试（transport-tested），尚未进行付费实测。

## 独立阶段与断点续传（Resume）

```bash
llmka collect-candidates --config configs/mock.yaml
llmka disambiguate --method string --config configs/mock.yaml
llmka disambiguate --method context --config configs/mock.yaml
llmka generate-triples --config configs/mock.yaml
llmka retrieve-evidence --config configs/mock.yaml
llmka judge --config configs/mock.yaml
llmka evaluate --config configs/mock.yaml
llmka build-report --config configs/mock.yaml
llmka run-all --config configs/mock.yaml --resume results/mock/<previous-run-id>

```

每次调用 CLI 都会创建一个**全新的目录**。某个阶段在运行时会自动执行其缺失的前置依赖阶段。
使用 `--resume` 参数可以复制上一阶段成功生成的不可变产物/检查点，且**绝不会修改**父级运行目录。如果变更了配置文件、源代码或基准输入数据，系统将拒绝续传。但允许变更人类标注数据：此时评估和报告阶段会重新计算，而模型生成的产物则保持冻结状态。断点续传还会继承并带入保守的预算预留记录，包括中断前已尝试发送的请求。文件级别的缓存机制允许新的运行复用之前已完成的完全相同的请求。若要刷新公开数据，必须指定全新的缓存目录并生成新的数据集版本；实验过程绝不会覆写 Gold 数据。

## 人类标注（Human Annotation）

[data/annotations/human_annotations.template.jsonl](data/annotations/human_annotations.template.jsonl) 中包含 **113 条空白记录**，它们与公开 KB 的评审包相绑定。这些是源自数据源的正向偏置练习记录（positive-biased practice records），**并非 LLM 生成的测试集**，也不代表已完成的人类标注研究。实际的人类标注文件目前为空。

每次模型运行都会生成专属的 `annotations.template.jsonl` 和 `annotation_packet.json`，其中仅包含裁判模型所看到的证据，并剔除了裁判模型的预测结果。请根据[标注指南（annotation guidelines）](docs/annotation_guidelines.md)至少评审 100 条实际由 LLM 生成的三元组。填写评审员身份、日期、备注、证据 ID 及对应标签；同时需保留三元组与证据的哈希值。将未修改配置中的标注文件路径指向这些记录，然后恢复评估流程。切勿将标注标签替换为桩数据输出或裁判模型的输出。系统会自动拒绝不同的证据快照或重复的 ID。

## 评价指标与解读

评估指标体系包括：

* 候选元 Recall@k / MRR；
* Top-1 准确率、弃权率（abstention）及条件准确率（conditional accuracy）；
* 同音词分离/混淆率、同义词合并率；
* 分领域错误率；
* 有效 JSON/Schema 比例、去重率及单 Seed 生成三元组数；
* 事实标签比例、严格精确率（strict precision）与决断精确率（decisive precision）；
* 裁判模型准确率、Macro P/R/F1、混淆矩阵以及 Cohen's kappa 一致性系数；
* 时延分位数（latency percentiles）、API 请求数、Token 消耗量、预估成本、重试与失败次数。

每个比率指标均会显式标明其分子与分母；无法获取的数据项显示为 null。由于歧义组之间存在依赖关系，案例级的 Wilson 置信区间仅作为描述性参考。Macro 指标涵盖全部三个标签，并采用了显式的除零处理约定。详见[指标定义文档](https://www.google.com/search?q=docs/metrics.md)。

自动标记的错误示例仅从实际运行记录中生成。“幻觉关系（hallucinated relation）”和“时间错配（temporal mismatch）”等类别在经过人工评审之前，将保持标注为**需要人工错误评审（requires human error review）**；空标记列表并不代表零错误。

## 真实 Pilot 实验：需要显式授权

```bash
llmka pilot-plan --config configs/pilot.yaml

```

[Pilot 提案](docs/pilot_proposal.md)中详细规定了 5 个测试案例、精确的模型快照、调用/Token 预估以及 2 美元的成本上限。请首先评审这 5 个案例记录。在环境变量中设置 `LLMKA_API_KEY`（注意避免在终端打印或泄露）。获得显式授权后，执行：

```bash
llmka run-all --config configs/pilot.yaml --approve-paid

```

项目中未包含任何保存的密钥或 `.env` 自动加载机制。应用程序将拒绝未经授权且未缓存的 API 调用，并在每次请求尝试前预留保守的成本预算，同时严格执行请求次数和预算上限。在执行前必须重新核对价格预估。预算预留机制可能会导致运行提前终止，即便实际消耗尚未达到上限。对于重放（replay）测试，请在新的配置文件中设置 `offline: true` 并使用缓存的请求数据。初始的 5 案例 Pilot 仅作为技术维度的冒烟测试（smoke experiment），不具备统计学说服力。

一旦产生了真实运行结果，执行 `llmka plot --run-dir results/real/<run-id>` 将会在新的图表目录中生成 PNG 图片及机器可读的源文件。Mock 运行将被拒绝生成图表。在存在真实标注之前，人类混淆矩阵将被忽略。目前尚未产生任何基于真实结果的图表或可写入简历（CV）的成果数据。

## 实现状态总结（Implemented, Completed, and Pending）

| 分类 | 状态 |
| --- | --- |
| 类型化流水线、Provider、缓存、CLI、断点续传、指标计算、报告生成 | 已实现并在离线环境下完成测试 |
| 公开候选元 / 来源元数据 | 已采集；保存了数据出处（provenance） |
| 基准数据验证（Benchmark verification） | 0/40 完成人类验证；待开展 |
| 公开断言评审模板（Public-claim review template） | 113 条未标注记录；就绪待评审 |
| LLM 生成事实性审计实验 | 待授权与执行 |
| 人类标注研究（Human annotation study） | 已完成 0 条；至少需要 100 条生成的标注三元组 |
| 真实图表与可测量的 CV 成果 | 待获取真实结果 |

[论文样式报告](docs/paper_report.md) · [研究计划](docs/research_plan.md) · [实验协议](docs/experiment_protocol.md) · [局限性说明](docs/limitations.md)。

## 伦理与开源许可

本项目代码基于 MIT 许可证从零独立编写。未使用任何专有的雇主代码、提示词、数据、接口端点或架构。本仓库既未修改也未引入邻近的 GPTKB 源代码。Wikidata 结构化数据遵循 CC0 许可；Wikipedia 文本保留其原有的 CC BY-SA 署名及来源历史。详见 [DATA_LICENSE.md](DATA_LICENSE.md)。
LLM 的输出应视为假设（hypotheses）而非绝对真理；人类评审必须明确区分证据支持（evidential support）与通用事实性（universal factuality）。Provider 的输出和大型缓存文件已被 Git 忽略。在公开发布前，请务必审查相关的产物文件。本仓库未设置任何自动化发布或推送机制。