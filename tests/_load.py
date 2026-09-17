"""Load the skill's dependency-free scripts by path, without packaging."""
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / ".claude" / "skills" / "typed-decision" / "scripts"


def load(name):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
