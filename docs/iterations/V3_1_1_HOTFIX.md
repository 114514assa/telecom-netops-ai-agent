# V3.1.1 Windows pytest 兼容性修复说明

## 1. 版本范围与问题证据

- 父版本：V3.1.0（Guardrail 可观测性与安全否定句误报修复）。
- 本次用户 Windows 验收：`93 passed, 1 warning, 2 errors`；错误输出存在大量重复 `X` 和 `ValueError: the environment variable is longer than 32767 characters`。
- 源码核查发现：`tests/test_pdf_ingest.py` 将 `b"X" * (MAX_PDF_BYTES + 1)`（5MiB+1）作为 `pytest.mark.parametrize` 参数，但未指定 pytest 用例标识。Python Windows/pytest/插件或运行器组合可能把超长数据序列化进测试 ID/环境变量。仅凭截图不能断言两个错误都来自同一机制；需以重测或 `--tb=short` 日志确证。
- 这是 V3.1.0 打包引入/遗漏的测试兼容性回归，不是 PDF 接口真实处理失败，也不是用户 `.venv` 迁移错误。

## 2. 具体改动及设计原因

| 修改 | 技术方式 | 解决的问题 |
|---|---|---|
| `tests/test_pdf_ingest.py` | 为 invalid_pdf_header、empty_pdf、oversized_pdf 指定 `pytest.param(..., id=...)` | 保留超大文件检查，同时避免超长参数进入 pytest 测试 ID |
| `RUN_V3_1_ENV.ps1` | 改用独立 `runtime_v3_1_1` | 不覆盖 V2/V3.1.0 测试索引、Checkpoint 和报告 |
| `scripts/analyze_guardrail_v3_1.py` | 输出标识设为 `v3_1_1` | 使实验输出文件名可辨版本；分析算法不变 |
| `tests/test_guardrail_v3_1.py` | 更新期望输出文件名的断言 | 适配版本化输出 |
| `VERSION.json`、`CHANGELOG.md`、运行手册 | 注明 3.1.1/热修复原因 | 形成可追溯迭代链 |

没有改动生产 API、Guardrail 判断规则、RAG、定量评测语料、故障规则和量化脚本；因此此补丁不应被当作 V3.1 优化效果的证据。

## 3. Windows 运行步骤（与 V2/V3.1.0 同级解压）

```powershell
$Project = 'C:\Users\Lenovo\Desktop\秋招\agent教学\telecom-netops-ai-agent_B7E78B8AE5BAAEE6B4BAE781\telecom-netops-ai-agent-v3.1.1'
Set-Location -LiteralPath $Project
. .\RUN_V3_1_ENV.ps1
& $Py -m pip check
& $Py -m pytest -q tests/test_pdf_ingest.py --tb=short
& $Py -m pytest -q --tb=short
```

- 仅共享 V2 的 Python 虚拟环境，不需要复制 `.venv`；不得在共享 `.venv` 中擅自升级依赖。
- 版本数据位于 V3.1.1 根目录的 `runtime_v3_1_1/`，不覆盖 V3.1.0 的 `runtime_v3_1/`。
- 如果依旧出现 Error，请执行 `& $Py -m pytest -q --tb=short --maxfail=1 > .\pytest_v3_1_1_error.txt 2>&1`，提供日志最后 80 行，先定位而非再次改动全部代码。

## 4. 验收准则与后续步骤

1. `tests/test_pdf_ingest.py` 所有测试通过，无 5MiB `X` 字符串展开。
2. 全量 pytest 不再出现原先 32767 字符错误；如果剩余独立异常，分案处理。
3. V3.1.1 完整 E2E/模型对照测试仍未执行；待 Windows 用户验证通过后，使用 `runtime_v3_1_1` 与 V2 基线比较。
4. 面试叙述：通过 Windows 环境验证发现大型参数化测试 ID 造成进程/运行器兼容性问题，保留边界测试数据，只缩短测试用例名称，并通过独立补丁版本保证可追溯与旧基线不受影响。
