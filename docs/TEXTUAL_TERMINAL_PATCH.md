# textual-terminal patch for Textual 8.x compatibility

## Problem

`textual-terminal==0.3.0` imports `DEFAULT_COLORS` from `textual.app`, which was
removed in newer versions of Textual. This causes an `ImportError` on import.

## Fix

In `.venv/lib/python3.12/site-packages/textual_terminal/_terminal.py`, line 34:

```python
# Change this:
from textual.app import DEFAULT_COLORS

# To this:
# from textual.app import DEFAULT_COLORS  # removed: incompatible with textual 8.x
```

This only affects the `default_colors="textual"` option. The default
(`default_colors="system"`) works fine without it.

## Recommendation

Consider vendoring a patched copy of `textual_terminal/` into the project, since
`pip install --force-reinstall` or `uv sync` will overwrite the patch.
