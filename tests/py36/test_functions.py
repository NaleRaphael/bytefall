"""
These tests should be run when version of Python >= 3.5
"""

import pytest
from .. import vmtest


class TestFunctionAnnotations(vmtest.VmTestCase):
    def test_simple_annotation(self):
        self.assert_ok("""\
            def adder(x: int, y: int, z) -> int:
                return x+y+z

            assert adder(1, 2, 3) == 6
            """)

    def test_annotations_for_args_and_kwargs(self):
        self.assert_ok("""\
            def fn(*args: str):
                print(args)
                return ''.join(args)

            assert fn('h', 'e', 'l', 'l', 'o') == 'hello'
            """)

        # NOTE: Order keys of dict is preserved since Py36, so that the
        # result should be deterministic.
        self.assert_ok("""\
            def fn(**kwargs: str):
                return ', '.join(['(%s, %s)' % (k, v) for k, v in kwargs.items()])
            assert fn(a=1, b=2, c=3) == '(a, 1), (b, 2), (c, 3)'
            """)

    def test_lambda_in_annotation(self):
        self.assert_ok("""\
            class Foo:
                ...

            def adder(x: int, foo: (lambda x:isinstance(x, Foo))=None):
                foo_val = -1 if foo is None else 3
                return x+foo_val

            assert adder(1) == 0
            assert adder(1, Foo()) == 4
            """)

    def test_function_in_annotation(self):
        self.assert_ok("""\
            class Foo:
                def __init__(self):
                    self.val = 3

            def is_foo(x):
                return isinstance(x, Foo)

            def adder(x: int, foo: is_foo=None):
                foo_val = -1 if foo is None else foo.val
                return x+foo_val

            assert adder(1) == 0
            assert adder(1, Foo()) == 4
            """)
