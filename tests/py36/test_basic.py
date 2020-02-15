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
