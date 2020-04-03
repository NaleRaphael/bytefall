__all__ = ['CellType', 'make_cell']


def make_cell(value):
    fn = (lambda x: lambda: x)(value)
    return fn.__closure__[0]


# Define `CellType`
import sys
if sys.version_info < (3, 8):
    CellType = type(make_cell(None))
else:
    from types import CellType
del sys
