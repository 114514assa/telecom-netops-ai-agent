# Knowledge Base

公开仓库**不包含**根据实习资料整理的源文件或脱敏知识库。

- `knowledge/demo/`：完全虚构、可公开的演示知识。
- `knowledge/sanitized/`：仅供本地私人使用，已被 `.gitignore` 屏蔽。
- `knowledge/source_private/`：原始资料目录，禁止提交。

如需本地使用自己的知识库，请在 `.env` 中修改：

```env
RAG_KNOWLEDGE_DIR=knowledge/your_private_folder
```
