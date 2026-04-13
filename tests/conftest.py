import importlib.util
import importlib.machinery
import os
import pytest

SCRIPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "autosub_single"
)


@pytest.fixture(scope="session")
def mod():
    """Import autosub_single (extensionless script) as a Python module."""
    path = os.path.abspath(SCRIPT_PATH)
    loader = importlib.machinery.SourceFileLoader("autosub_single", path)
    spec = importlib.util.spec_from_file_location("autosub_single", path, loader=loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
