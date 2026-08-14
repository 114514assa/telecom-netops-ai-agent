# GitHub 发布前检查

1. 复制 `.env.example` 为本地 `.env`，不要提交 `.env` 或 API Key。
2. 运行 `python scripts/seed_db.py` 和 `pytest -q`。
3. 安装开发依赖后运行 `ruff check app scripts tests`。
4. 基础功能建议至少演示一次 `python scripts/run_demo.py --case vlan_mismatch`。
5. 如需展示模型量化，使用自己的机器运行 `scripts/benchmark_quantization.py`，保留原始 JSON/CSV，但不要把未经验证的提升比例写进 README 或简历。
6. GitHub 仓库建议保留 README、LICENSE、SECURITY、PROJECT_BOUNDARY 与 CI 配置。
7. 截图或录屏只使用当前模拟数据，不展示公司内部系统、真实 IP、账号、客户信息或设备标识。
