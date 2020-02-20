"""
These tests should be run when version of Python >= 3.5
"""

import pytest
from .. import vmtest


class TestClassAnnotations(vmtest.VmTestCase):
    def test_simple_annotations(self):
        self.assert_ok("""\
            class Foo(object):
                a: int = 1
                b: float = 0.1
                c: str = 'evil'
                d = {}
                d['a']: int = 0
                d['b']: float
                (x): int

            _dict = Foo.__dict__
            print(Foo.__annotations__)
            print(_dict['a'], _dict['b'], _dict['c'], _dict['d'])
            assert 'x' not in Foo.__annotations__
            """)

    def test_access_class_annotations_from_method(self):
        self.assert_ok("""\
            class Foo(object):
                a: int = 1
                b: float = 0.1
                c: str = 'evil'

                def fn(self):
                    return (self.a, self.b, self.c)

            print(Foo().fn())
            """)


class TestFString(vmtest.VmTestCase):
    def test_simple_f_string(self):
        self.assert_ok("""\
            who = 'world'
            print(f'hello {who}')
            """)

    def test_print_object(self):
        self.assert_ok("""\
            class ChaoticNeutralObject(object):
                def __str__(self):
                    return "I'm totally neutral"
                def __repr__(self):
                    return "s​a​s​a​g​e​y​o"

            obj = ChaoticNeutralObject()

            print(f'{obj}')
            print(f'{obj!s}')
            print(f'{obj!r}')
            print(f'{obj!a}')
            """)

    def test_digit_format(self):
        self.assert_ok("""\
            value = 1.23456
            print(f'{value:.4f}')
            """)

    def test_call_function_in_f_string(self):
        self.assert_ok("""\
            def fn():
                return 'wow'

            print(f'{fn()}')
            """)

    def test_invalid_format(self):
        self.assert_ok("""\
            class Foo(object):
                def __repr__(self):
                    return 'foo'

            foo = Foo()
            print(f'{foo:.4f}')
            """, raises=TypeError)


class TestExec(vmtest.VmTestCase):
    def test_class_annotations(self):
        self.assert_ok("""\
            class C:
                exec('x: int')
            print(C.__annotations__)
            print(__annotations__)
            """, globs=globals(), locs=locals())
