"""Contrato com o gflow-cli fixado: tudo o que o MCP importa ou usa por dentro precisa existir.

O MCP usa funções e métodos internos (com `_`) do gflow-cli. Os demais testes usam
mocks, então uma atualização do gflow-cli que os remova passaria despercebida; este
teste falha antes do deploy.
"""

import ast
import importlib
from pathlib import Path
import unittest

ROOT = Path(__file__).parent
# Métodos internos chamados ou sobrescritos (BudgetedComposer, worker, upload).
PRIVATE_MEMBERS = {
    ("gflow_cli.api.transports.migrated_composer", "MigratedComposer"):
        ("_open_pane", "_select", "_close_pane", "_pre_submit_gate", "_upload_via_toolbar", "ensure_editor"),
    ("gflow_cli.errors", "FlowAgentUiError"): (),
    ("gflow_cli.api.client", "FlowApiClient"): ("_request_headers", "_is_aisandbox_url"),
}


def gflow_imports():
    sources = [*ROOT.glob("flow_*.py"), ROOT / "keepalive.py", *ROOT.glob("deploy/*.py")]
    for path in sources:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("gflow_cli"):
                for alias in node.names:
                    yield path.name, node.module, alias.name


class GflowContractTest(unittest.TestCase):
    def test_every_imported_name_exists(self):
        missing = []
        for source, module, name in gflow_imports():
            loaded = importlib.import_module(module)
            if not hasattr(loaded, name):
                try:
                    importlib.import_module(f"{module}.{name}")  # submódulo (ex.: auth)
                except ImportError:
                    missing.append(f"{source}: {module}.{name}")
        self.assertEqual(missing, [])

    def test_private_members_used_by_the_mcp_exist(self):
        missing = [f"{module}.{cls}.{member}"
                   for (module, cls), members in PRIVATE_MEMBERS.items()
                   for member in members
                   if not hasattr(getattr(importlib.import_module(module), cls), member)]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
