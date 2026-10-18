from contextlib import AbstractContextManager

from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.config import get_settings
from app.data.repository import InventoryRepository
from app.graph.builder import build_graph
from app.services.audit import AuditLogger
from app.services.knowledge import RoutedKnowledgeBase


class ApplicationRuntime:
    def __init__(self):
        self.settings = get_settings()
        self.repository = InventoryRepository(self.settings.inventory_db)
        self.knowledge_base = RoutedKnowledgeBase(self.settings)
        self.audit = AuditLogger(self.settings.audit_log)
        self._checkpoint_context: AbstractContextManager | None = None
        self.checkpointer = None
        self.graph = None

    def start(self) -> None:
        if self.graph is not None:
            return
        if self.settings.app_env != "development":
            if not self.settings.demo_auth_enabled or not self.settings.demo_reader_token or not self.settings.demo_approver_token:
                raise RuntimeError("Non-development mode requires explicit read/approver tokens; demo token auth is not enterprise IAM")
            if not self.settings.require_approval:
                raise RuntimeError("Non-development mode requires human approval")
        self.settings.ensure_directories()
        self.repository.initialize(self.settings.data_dir / "inventory.csv")
        self.knowledge_base.load()
        self._checkpoint_context = SqliteSaver.from_conn_string(str(self.settings.checkpoint_db))
        self.checkpointer = self._checkpoint_context.__enter__()
        self.graph = build_graph(
            repository=self.repository,
            knowledge_base=self.knowledge_base,
            settings=self.settings,
            audit=self.audit,
            checkpointer=self.checkpointer,
        )

    def stop(self) -> None:
        if self._checkpoint_context is not None:
            self._checkpoint_context.__exit__(None, None, None)
        self._checkpoint_context = None
        self.checkpointer = None
        self.graph = None


runtime = ApplicationRuntime()
