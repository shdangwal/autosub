import importlib.util
import importlib.machinery
import os
import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")


def _load_script(name):
    """Import an extensionless script from scripts/ as a Python module."""
    path = os.path.abspath(os.path.join(SCRIPTS_DIR, name))
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def mod():
    """Import autosub_single (extensionless script) as a Python module."""
    return _load_script("autosub_single")


@pytest.fixture(scope="session")
def retranslate_mod():
    """Import autosub_retranslate (extensionless script) as a Python module."""
    return _load_script("autosub_retranslate")
