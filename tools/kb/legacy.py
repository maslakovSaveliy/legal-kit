"""Access to the source base's table module (build_refs.py): the directory map and the short triggers."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


def _calls_main(node: ast.AST) -> bool:
    return any(
        isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "main"
        for call in ast.walk(node)
    )


def _runs_main(node: ast.stmt) -> bool:
    """True for a top-level statement that would call ``main()`` when the module is run.

    Function and class definitions only mention ``main`` and are kept; every other statement
    (call, ``raise SystemExit(main())``, ``x = main()``, ``x: int = main()``, ``x += main()``,
    ``if …: main()``, ``try: main()``) is dropped when its code calls ``main``.
    """
    return not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and _calls_main(node)


def load_build_refs(path):
    """Load the table module ``build_refs.py`` of the knowledge base (the file ``path``) and return the module.

    The module is only read, never copied. Its source is compiled and run in a fresh module
    object whose name is not ``__main__``. Top-level statements that call ``main()`` (bare, in an
    assignment, under an ``if`` or ``try``, including the ``__main__`` guard) are dropped before
    the code runs, so loading only defines ``DIRS``, ``TRIGGER`` and the rest. Nothing goes
    through the import system, so no bytecode is written next to the file: the knowledge base
    stays untouched.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"build_refs.py not found: {path}")
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    tree.body = [node for node in tree.body if not _runs_main(node)]
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader("kb_build_refs", loader=None))
    module.__file__ = str(path)
    exec(compile(tree, str(path), "exec"), module.__dict__)  # noqa: S102 - trusted file of the owner
    for name in ("DIRS", "TRIGGER"):
        if not hasattr(module, name):
            raise AttributeError(f"{path} defines no {name}")
    return module
