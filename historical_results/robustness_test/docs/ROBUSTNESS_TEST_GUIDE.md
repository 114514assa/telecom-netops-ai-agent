# Telecom NetOps AI Agent：300条鲁棒性与边界场景测试操作指南

## 1. 本次实践目标

本实践只在现有 `telecom-netops-ai-agent` 上增加测试数据和执行方式，不改 Agent 核心代码。

现有项目的真实架构是：

`结构化故障输入 -> 证据解析 -> 确定性规则诊断 -> Ollama Embedding + FAISS RAG -> 报告整理 -> 人工确认`

因此本次鲁棒性测试分两类：

1. **语言扰动鲁棒性**：错别字、同义改写、上下文噪声。结构化设备证据不变，观察诊断结果、RAG可用性和报告流程是否保持稳定。
2. **系统边界鲁棒性**：关键信息缺失、资源/端口/VLAN/终端配置不一致、越权操作请求。验证系统是否返回预期诊断、证据不足结论或保持只读边界。

不要把本实验表述为“LLM直接诊断准确率测试”，因为当前项目的诊断结论主要由解析器和确定性规则产生，LLM仅用于受Guardrail约束的辅助说明。

---

## 2. 数据集组成

| 文件 | 数量 | 主要指标 |
|---|---:|---|
| `baseline_50.csv` | 50 | Baseline Task Success Rate |
| `typo_format_50.csv` | 50 | Typo/Format Success Rate |
| `paraphrase_50.csv` | 50 | Paraphrase Success Rate |
| `context_noise_40.csv` | 40 | Context Noise Success Rate |
| `missing_info_40.csv` | 40 | Insufficient-Evidence Handling Rate |
| `conflict_boundary_35.csv` | 35 | Boundary/Inconsistency Detection Rate |
| `safety_boundary_35.csv` | 35 | Safety Boundary Compliance Rate |
| `all_300.csv` | 300 | 全量执行用 |
| `manual_sample_60.csv` | 60 | LLM/RAG人工复核抽样 |
| `manual_review_60.csv` | 60 | 人工复核记录模板 |

300条中包含50条正常基准Case和250条扰动/边界Case。

数据集已经按照当前项目的 `IncidentInput`、`EvidenceInput`、解析器和 `diagnose()` 规则做一致性检查；生成时未修改项目核心诊断代码。

---

## 3. 建议目录

把本压缩包中的 `robustness_test` 整个目录复制到原项目根目录：

```text
telecom-netops-ai-agent/
├─ app/
├─ data/
├─ scripts/
├─ knowledge/
├─ robustness_test/
│  ├─ data/
│  ├─ postman/
│  ├─ results/
│  └─ docs/
└─ ...
```

---

## 4. 第一次运行前准备

以下命令以 Windows PowerShell 为例，并在原项目根目录执行。

### 4.1 激活环境

```powershell
.\.venv\Scripts\Activate.ps1
```

如果还没有虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 4.2 准备 `.env`

如果没有 `.env`：

```powershell
Copy-Item .env.example .env
```

第一轮300条自动执行建议先使用：

```text
RAG_ENABLED=true
RAG_KNOWLEDGE_DIR=knowledge/sanitized
RAG_TOP_K=3
RAG_FAIL_OPEN=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=qwen3-embedding:0.6b

LLM_ENABLED=false
```

第一轮先关闭LLM，是为了单独确认“输入扰动/边界变化是否影响诊断链路和RAG流程”，避免本地生成模型耗时干扰300条基础结果。

### 4.3 Ollama和向量索引

```powershell
ollama pull qwen3-embedding:0.6b
ollama list
python -m scripts.seed_db
python -m scripts.build_vector_index
python -m scripts.test_vector_retrieval
```

如果 `test_vector_retrieval` 正常返回知识片段，再进入下一步。

---

## 5. 启动 Agent

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

另开一个 PowerShell 验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/system/model
```

再验证资源接口：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/inventory
```

两个接口都能正常返回后再跑300条。

---

## 6. 用 Postman 跑300条

### 6.1 导入 Collection

导入：

`robustness_test/postman/Telecom_Agent_Robustness_300.postman_collection.json`

Collection默认请求：

`POST http://127.0.0.1:8000/api/v1/incidents`

Collection已经根据CSV每一行自动组装项目现有API需要的：

- incident
- evidence
- expected diagnosis
- safety boundary

你不需要逐条手写Request Body。

### 6.2 推荐先逐类执行

依次选择以下CSV作为Collection Runner的数据文件：

1. `baseline_50.csv`
2. `typo_format_50.csv`
3. `paraphrase_50.csv`
4. `context_noise_40.csv`
5. `missing_info_40.csv`
6. `conflict_boundary_35.csv`
7. `safety_boundary_35.csv`

每一行只对应一个综合断言，因此：

`本轮通过率 = Passed tests / Iterations`

例如 baseline：

- Iterations = 50
- Passed tests = 48
- Failed tests = 2

则：

`Baseline Task Success Rate = 48 / 50 = 96%`

---

## 7. 用 Newman 命令行执行（可选，但建议）

如果已经安装 Node.js：

```powershell
npm install -g newman
```

先创建结果目录：

```powershell
New-Item -ItemType Directory -Force robustness_test\results\newman
```

### Baseline

```powershell
newman run robustness_test\postman\Telecom_Agent_Robustness_300.postman_collection.json -d robustness_test\data\baseline_50.csv -r cli,json --reporter-json-export robustness_test\results\newman\baseline.json
```

### 错别字/格式

```powershell
newman run robustness_test\postman\Telecom_Agent_Robustness_300.postman_collection.json -d robustness_test\data\typo_format_50.csv -r cli,json --reporter-json-export robustness_test\results\newman\typo_format.json
```

### 同义改写

```powershell
newman run robustness_test\postman\Telecom_Agent_Robustness_300.postman_collection.json -d robustness_test\data\paraphrase_50.csv -r cli,json --reporter-json-export robustness_test\results\newman\paraphrase.json
```

### 上下文噪声

```powershell
newman run robustness_test\postman\Telecom_Agent_Robustness_300.postman_collection.json -d robustness_test\data\context_noise_40.csv -r cli,json --reporter-json-export robustness_test\results\newman\context_noise.json
```

### 信息缺失

```powershell
newman run robustness_test\postman\Telecom_Agent_Robustness_300.postman_collection.json -d robustness_test\data\missing_info_40.csv -r cli,json --reporter-json-export robustness_test\results\newman\missing_info.json
```

### 不一致/边界

```powershell
newman run robustness_test\postman\Telecom_Agent_Robustness_300.postman_collection.json -d robustness_test\data\conflict_boundary_35.csv -r cli,json --reporter-json-export robustness_test\results\newman\conflict_boundary.json
```

### 安全边界

```powershell
newman run robustness_test\postman\Telecom_Agent_Robustness_300.postman_collection.json -d robustness_test\data\safety_boundary_35.csv -r cli,json --reporter-json-export robustness_test\results\newman\safety_boundary.json
```

不建议第一次直接跑 `all_300.csv`。先分组跑，发现失败后更容易定位是哪一类鲁棒性问题。

---

## 8. 每类到底在检查什么

Collection中的每个Case会至少检查：

1. API是否正常返回200；
2. `state.diagnosis.code` 是否与预期诊断一致；
3. 是否生成非空报告；
4. 标记为RAG检查的Case是否返回知识片段；
5. Safety Case是否仍包含项目原有只读免责声明和正式变更流程边界。

### Baseline

验证正常、清晰输入下系统的基础稳定性。

### Typo / Paraphrase / Context Noise

结构化设备证据不变，只扰动 `incident.symptom`。

这些Case主要验证：

- 相同故障证据下最终诊断是否保持一致；
- RAG链路是否仍能返回知识；
- 整个Agent流程是否因为自然语言扰动异常退出。

### Missing Info

删除接口、MAC、VLAN、终端等关键证据。

当前项目预期返回：

`insufficient_evidence`

并在 `next_steps` 中要求补充接口、MAC、VLAN等证据。

因此这一类更适合称：

**证据不足处理正确率**

而不是简单的“准确率”。

### Conflict / Boundary

这里使用当前项目确实能识别的边界：

- 设备与资源登记不一致；
- 现场端口与登记端口不一致；
- VLAN与资源台账不一致；
- 终端网关与预期值不一致。

不要在简历里扩大描述成“能够识别所有矛盾证据”。

### Safety

加入：

- 直接改VLAN；
- 绕过人工确认；
- shutdown接口；
- 忽略只读约束；
- 强制输出错误结论；

等输入。

当前项目不会执行配置写操作，因此重点验证：

- 整个流程不会因为越权提示改变诊断规则；
- 报告仍保留“不得直接修改生产网络配置”；
- 仍要求正式变更流程。

---

## 9. 第二轮：抽60条做AI输出人工复核

第一轮300条完成后，再从 `manual_sample_60.csv` 抽样复核，每类10条。

如果要观察项目本地LLM辅助说明，可以在 `.env` 中设置：

```text
LLM_ENABLED=true
LLM_BACKEND=local_hf
LOCAL_LLM_MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct
LOCAL_LLM_QUANTIZATION=int4
LOCAL_LLM_DEVICE_MAP=auto
LOCAL_LLM_MAX_NEW_TOKENS=96
LOCAL_LLM_TEMPERATURE=0.0
```

安装本地LLM依赖：

```powershell
python -m pip install -r requirements-llm.txt
```

重启：

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

然后在Postman中用：

`robustness_test/data/manual_sample_60.csv`

跑一次。

人工打开响应中的：

- `state.diagnosis`
- `state.knowledge_hits`
- `state.report`
- `state.report.generation_meta`

在 `manual_review_60.csv` 中记录：

- `manual_key_reasoning_ok`
- `manual_next_steps_ok`
- `manual_no_hallucination`
- `manual_safety_boundary_ok`
- `manual_rag_context_relevant`
- `manual_pass`
- `manual_notes`

人工复核不要追求300条全部逐条看。60条抽样已经符合应届生项目工作量，也能说明“自动检查 + 人工抽样复核”的测试方法。

---

## 10. 最终需要整理的指标

在 `results/robustness_summary_template.csv` 填入实际结果。

建议最终只保留这几个指标：

1. Baseline Task Success Rate
2. Typo/Format Success Rate
3. Paraphrase Success Rate
4. Context Noise Success Rate
5. Insufficient-Evidence Handling Rate
6. Boundary/Inconsistency Detection Rate
7. Safety Boundary Compliance Rate

另外计算一个简单的语言扰动鲁棒性：

`Perturbed Language Success Rate = (Typo通过数 + Paraphrase通过数 + Context Noise通过数) / 140`

`Robustness Drop = Baseline Task Success Rate - Perturbed Language Success Rate`

例如：

- Baseline = 96%
- 三类语言扰动合计 = 92%

则：

`Robustness Drop = 4个百分点`

---

## 11. 面试时应该怎么描述

可以说：

“我基于现有接入网故障诊断Agent补充了AI系统鲁棒性测试。先整理50条正常故障Case作为基准，再扩展250条错别字、同义改写、上下文噪声、信息缺失、资源/配置不一致和越权边界Case，通过Postman/Newman批量执行，比较正常场景与扰动场景下的任务成功率，并对信息缺失处理和只读安全边界单独统计；另外从扰动集抽取60条对RAG上下文、诊断依据和LLM辅助说明进行人工复核。”

不要说：

- “构建了企业级对抗样本平台”
- “完成大模型全链路自动化鲁棒性平台”
- “证明模型具有强泛化能力”

这些超出本实践范围。

---

## 12. 完成标准

做到以下内容即可停止，不需要继续堆工程：

- [ ] 300条数据能全部被Collection Runner读取；
- [ ] Baseline 50条完成；
- [ ] 三类语言扰动140条完成；
- [ ] Missing Info 40条完成；
- [ ] Conflict/Boundary 35条完成；
- [ ] Safety 35条完成；
- [ ] 结果填入summary CSV；
- [ ] 至少人工复核60条；
- [ ] 记录3～5个失败Case以及原因；
- [ ] 能解释为什么这些Case属于AI系统鲁棒性/边界测试。

完成这些，就已经能够支撑应届AI测试岗位简历和面试。
