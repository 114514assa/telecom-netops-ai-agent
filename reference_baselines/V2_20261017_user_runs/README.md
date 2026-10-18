# V2 用户本地基线记录（2026-10-17）

本目录仅保存用户此前上传的 V2 两张实验汇总 CSV，作为后续对照资料；不是 V3.1 的测试结果。

- `V2_local_int4_agent_perf_summary.csv`：本地 INT4 E2E（用户上传 `perf_e2e.zip`）。
- `V2_quant_benchmark_v2_summary.csv`：量化组件性能（用户上传 `runtime.zip`）。
- RAG 150 Query 的 Hit@3 93.33% / MRR 0.8571，34 Query Hit@3 64.71%，见此前用户终端日志；没有将缺失的逐条原始 CSV 假造进新包。
- 本目录没有改变旧版的 `historical_results/`。
- V3.1 优化后性能需要在同一环境、同一案例与参数下重新验证；生成质量及安全不可由本目录外推。
