---
name: compact-python
description: >-
  Refactors Python so syntax that is usually wrapped for readability stays on
  one line, ignoring formatting rules in order to preserve tokens. Covers
  class constructor parameters, method parameters, method calls, and the rest
  of that multi-line syntax. Use when the user runs /compact-python or asks to
  compact Python, collapse Python formatting, or save tokens by putting Python
  on one line.
---

# Compact Python

Put readability wrapping onto one line. There is no line-length limit. Do not restore wraps to satisfy Black, Ruff, PEP 8, or the project's formatter.

Compact the Python the user names. When they name the project, compact every `*.py` file except virtual environments, `site-packages`, and `__pycache__`.

## Collapse

Join these when the only reason they span lines is readability. Drop a trailing comma that existed to keep a closer on its own line. Keep the comma in a one-element tuple.

```python
    def remember_player(
        self,
        name: str,
        *,
        agentic: bool = False,
        room_name: str = "",
        auras: list[str] | None = None,
    ) -> SessionBeing:
        being = self._upsert(name, "player", room_name, auras)
        being.agentic = agentic
        return being
```

```python
    def remember_player(self, name: str, *, agentic: bool = False, room_name: str = "", auras: list[str] | None = None) -> SessionBeing:
        being = self._upsert(name, "player", room_name, auras)
        being.agentic = agentic
        return being
```

Do the same for:

- Class bases and constructor parameter lists
- `def` and `async def` parameter lists, including defaults and annotations
- Calls, keyword arguments, and nested calls
- Lists, dicts, sets, tuples, and comprehensions
- Parenthesized imports (`from pkg import a, b, c`)
- Chains broken after a dot (`obj.one().two()`)
- Explicit backslash continuations

Move a comment that sat between wrapped parts onto the end of the collapsed line, or onto the line above it. Do not delete it.

## Leave in place

- Blank lines that separate blocks of related code
- Newlines inside string literals and docstrings
- A body with more than one statement
- Class suites. The header stays on its own line, including a subclass whose body is only a docstring or `pass`
- Function suites. The header stays on its own line. A wrapper that immediately returns an updated value is two lines:

  ```python
  def note_aggressive(self, name: str, *, room_name: str = "") -> SessionBeing:
      return self.remember_mobile(name, room_name=room_name, aggressive=True)
  ```

- `try`, `with`, `for`, `while`, `if`, and `match` headers that introduce a real suite
- Names, literals, control flow, and behavior

## Check

Parse each changed file with `python -m py_compile <file>`. Fix syntax the collapse introduced. Do not run a formatter afterward.
