# RAG 150 条模拟 Query 召回实验执行说明

## 1. 本实验基于当前项目的什么内容

本实验严格沿用当前项目已有的 LangChain RAG 链路：

`knowledge/*.md -> LangChain Document -> OllamaEmbeddings(qwen3-embedding:0.6b) -> FAISS -> Retriever`

当前项目已有 `data/rag_eval/queries_30.json`，其中实际已经覆盖 10 类场景，每类 3 条。本次不新增脱离项目的“第 11 类”，而是在原 10 类基础上扩展为每类 15 条，共 150 条。

10 类为：

1. `no_mac`：接口 UP 但无目标 MAC
2. `vlan`：VLAN 证据不一致
3. `down`：接口 DOWN / 物理链路异常
4. `port`：资源登记端口与实际接入端口不一致
5. `upstream`：接入侧正常但业务仍异常
6. `gateway`：终端 IP / 网关配置异常
7. `link`：链路质量 / 错误计数异常
8. `arp`：MAC 存在但 ARP 缺失 / ARP 证据异常
9. `device`：资源登记设备与实时核查设备不一致
10. `normal`：接入证据一致 / 无明显接入侧异常

每类 15 条采用相同结构：直接故障描述 3 条、口语/同义改写 3 条、多证据组合 3 条、排障操作询问 3 条、不完整/带干扰信息 3 条。

## 2. 先修正/确认知识库目录

本次上传项目中实际存在的知识文件位于：

`knowledge/sanitized/`

但 `.env.example` 与 `app/core/config.py` 的默认值仍是：

`RAG_KNOWLEDGE_DIR=knowledge/demo`

因此运行前必须检查你本机项目根目录下的 `.env`。本实验建议明确设置：

```env
RAG_ENABLED=true
RAG_KNOWLEDGE_DIR=knowledge/sanitized
RAG_TOP_K=3
RAG_FAIL_OPEN=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=qwen3-embedding:0.6b
VECTOR_INDEX_PATH=runtime/vector_index/knowledge.faiss
VECTOR_METADATA_PATH=runtime/vector_index/metadata.json
```

如果仍指向 `knowledge/demo`，当前这个项目包会因为该目录不存在而无法正确构建知识索引。

## 3. 将实验文件复制到项目

把本实验包中的：

- `data/rag_eval/queries_150.json`
- `data/rag_eval/queries_150.csv`
- `scripts/evaluate_rag_retrieval_150.py`

按相同相对路径复制到你的项目根目录。

`queries_150.json` 是程序直接读取的数据集；`queries_150.csv` 用于你人工检查问题与 Gold Label，不参与程序运行。

## 4. 启动虚拟环境与 Ollama

PowerShell 进入项目根目录后：

```powershell
.\.venv\Scripts\Activate.ps1
ollama list
```

确认存在：

`qwen3-embedding:0.6b`

若没有：

```powershell
ollama pull qwen3-embedding:0.6b
```

检查 Ollama：

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

## 5. 重新构建当前知识库索引

因为知识目录与索引必须对应，建议本次实验重新构建：

```powershell
python -m scripts.build_vector_index
```

你应重点确认控制台显示的 Knowledge directory 是：

`knowledge\sanitized`

并看到知识文件数、Chunks 数和 embedding shape。

如果显示 `knowledge\demo`，先停止实验，检查 `.env`。

## 6. 先做最小检索自检

```powershell
python -m scripts.test_vector_retrieval
```

如果这一步失败，不要直接跑 150 条。

## 7. 先跑 150 条的快速版本

第一次只验证数据集与脚本能否运行：

```powershell
python -m scripts.evaluate_rag_retrieval_150 --dataset data/rag_eval/queries_150.json --top-k 5 --repeats 1 --warmup 1
```

为什么取 `top-k=5`：一次检索直接取得 Rank1~Rank5，然后离线同时计算 Hit@1、Hit@3、Hit@5 和 MRR。不要为了算三个指标分别检索三遍。

## 8. 人工检查 Gold Label

第一次快速运行后，打开：

`runtime/rag_eval_150/rag150_hit1_errors_*.csv`

逐条检查 Hit@1=0 的案例。

重点分辨两种情况：

- Retriever 的确把不相关知识排到前面；
- Retriever 返回的其实也合理，只是当前 Gold Label 漏标了另一个合理知识块。

如果发现 Gold Label 明显漏标，可以在“正式实验前”修正 `queries_150.json`。一旦完成 Gold 审核，就冻结数据集，不要再为了提高最终分数反复修改问题或标签。

## 9. 正式运行

Gold Label 确认后运行：

```powershell
python -m scripts.evaluate_rag_retrieval_150 --dataset data/rag_eval/queries_150.json --top-k 5 --repeats 3 --warmup 3
```

`repeats=3` 主要用于让检索延迟更稳定，脚本取每个 Query 三次调用的中位数；检索质量本身使用同一最终排名计算。

## 10. 结果文件

正式运行后主要看：

- `rag150_summary_*.csv`：总指标
- `rag150_per_category_*.csv`：10 类场景分别表现
- `rag150_per_expression_*.csv`：5 种问题表达方式分别表现
- `rag150_detail_*.csv`：150 条逐条结果与 Top5
- `rag150_hit1_errors_*.csv`：所有 Top1 失败案例
- `rag150_full_*.json`：完整机器可读结果

核心指标：

- Hit@1：第一条检索结果是否命中人工 Gold
- Hit@3：前三条是否至少有一条命中
- Hit@5：前五条是否至少有一条命中
- MRR：正确结果总体排位是否靠前
- Avg/P95 Latency：检索延迟
- Empty/Error Rate：是否出现空召回或 Ollama/FAISS 调用错误

## 11. 如何选最终 RAG_TOP_K

虽然实验用 `top-k=5` 获取完整排名，但生产 Demo 不一定要把 5 个片段都送进 LLM。

完成实验后比较 Hit@1 / Hit@3 / Hit@5：

- 如果 Hit@3 已经接近 Hit@5，继续保留 `RAG_TOP_K=3` 更合理，减少无关上下文；
- 如果 Hit@5 相比 Hit@3 有明显提升，再检查失败类别，判断是知识切分问题还是确实需要扩大 K；
- 不要只因为 Hit@5 数字更高就直接把运行时 K 改成 5。

## 12. 简历数据怎么写

只有正式实验跑完后，才把 `XX.X%` 替换为真实数据。例如：

“基于 LangChain、Ollama Embedding 与 FAISS 构建本地向量知识库，依据接入网排障流程整理 10 类脱敏排障场景，构造 150 条模拟 Query 进行 Top-K 召回评测，Hit@1/Hit@3 分别达到【实测】/【实测】；结合 Human-in-the-loop、异常回退和审计记录保留诊断依据与处理过程。”

不要把 150 条描述成真实生产工单；它们是依据脱敏知识和已有排障流程构造的模拟评测 Query。

## 13. 运行结果建议发回哪些文件

为了后续帮你判断结果是否足够写简历，优先提供：

- `rag150_summary_*.csv`
- `rag150_per_category_*.csv`
- `rag150_per_expression_*.csv`
- `rag150_hit1_errors_*.csv`

如果需要逐条分析，再提供 `rag150_detail_*.csv` 或完整 JSON。
