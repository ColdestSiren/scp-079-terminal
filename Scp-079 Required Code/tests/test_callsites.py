"""Every module attribute main.py reaches for must actually exist.

WHY THIS EXISTS: v1.0.1 shipped calling gaslight.proposed_name(), which was
not in gaslight.py - an edit adding it had been reverted and nobody looked
again. Nothing caught it, because the call sits inside handle_gaslight and
only runs when somebody tries to rename 079. So the game imported fine,
started fine, played fine, and crashed to a traceback the first time a
player did the one thing the whole feature exists for.

A test that imports main is not enough. This walks the source for
`module.attribute` and checks each one resolves, which is the cheapest way
to catch a call that no test happens to execute.
"""
import ast
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

PASS = FAIL = 0


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


# Local modules only. Standard library and pygame are not the risk here, and
# some of them resolve attributes at runtime in ways ast cannot see.
LOCAL = set()
for entry in os.listdir(APP):
    if entry.endswith(".py") and not entry.startswith("_"):
        LOCAL.add(entry[:-3])

SOURCES = [f for f in sorted(os.listdir(APP)) if f.endswith(".py")]

missing = []
for filename in SOURCES:
    path = os.path.join(APP, filename)
    with open(path, "r", encoding="utf-8") as fh:
        try:
            tree = ast.parse(fh.read(), filename)
        except SyntaxError as exc:
            check("%s parses" % filename, False)
            print("       %s" % exc)
            continue

    # Which local modules this file imports under which name.
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in LOCAL:
                    imported[alias.asname or alias.name] = alias.name

    if not imported:
        continue

    # Names the file assigns to itself shadow the module of the same name.
    # main.py has a local list called `feedback`, and without this every
    # list method called on it reads as a missing module attribute.
    shadowed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            shadowed.add(node.id)
        elif isinstance(node, ast.arg):
            shadowed.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)):
            shadowed.add(node.name)

    wanted = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in shadowed:
                continue
            mod = imported.get(node.value.id)
            if mod:
                wanted.setdefault(mod, set()).add(node.attr)

    for mod, attrs in sorted(wanted.items()):
        try:
            module = __import__(mod)
        except Exception as exc:                 # noqa: BLE001
            check("%s imports (needed by %s)" % (mod, filename), False)
            print("       %s" % exc)
            continue
        for attr in sorted(attrs):
            if not hasattr(module, attr):
                missing.append("%s -> %s.%s" % (filename, mod, attr))

check("no source references a name its module does not define", not missing)

# ---------------------------------------------------------------------------
# ARITY. Existence is not enough, and this is not hypothetical: the fix for
# the crash above shipped a SECOND crash three commits later, because
# gaslight.Tracker.note_attack existed but took one argument and main.py
# passed two. The attribute check above passed it happily.
import inspect

arity = []
for filename in SOURCES:
    path = os.path.join(APP, filename)
    with open(path, "r", encoding="utf-8") as fh:
        try:
            tree = ast.parse(fh.read(), filename)
        except SyntaxError:
            continue

    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in LOCAL:
                    imported[alias.asname or alias.name] = alias.name

    shadowed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            shadowed.add(node.id)
        elif isinstance(node, ast.arg):
            shadowed.add(node.arg)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)):
            continue
        if fn.value.id in shadowed:
            continue
        mod = imported.get(fn.value.id)
        if not mod:
            continue
        try:
            target = getattr(__import__(mod), fn.attr, None)
        except Exception:                        # noqa: BLE001
            continue
        if not inspect.isfunction(target):
            continue
        # *args means anything goes; starred call args make the count unknown.
        if any(isinstance(a, ast.Starred) for a in node.args):
            continue
        try:
            sig = inspect.signature(target)
        except (TypeError, ValueError):
            continue
        params = list(sig.parameters.values())
        if any(p.kind is p.VAR_POSITIONAL for p in params):
            continue
        allowed = [p for p in params
                   if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        required = len([p for p in allowed if p.default is p.empty])
        given = len(node.args)
        if given > len(allowed) or given < required:
            arity.append("%s:%d -> %s.%s takes %d-%d positional, given %d"
                         % (filename, node.lineno, mod, fn.attr,
                            required, len(allowed), given))

check("no call passes the wrong number of arguments", not arity)
for item in arity:
    print("       ARITY: %s" % item)


for item in missing:
    print("       MISSING: %s" % item)

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
