"""
These tests should be run when version of Python >= 3.5
"""

import pytest
from .. import vmtest


class TestIt(vmtest.VmTestCase):
    def test_building_item_with_unpacking(self):
        # case for `BUILD_LIST_UNPACK`
        self.assert_ok("""\
            a = [1, 2, 3]
            b = [*a]
            assert a == b
            """)
        # case for `BUILD_TUPLE_UNPACK`
        self.assert_ok("""\
            a = (1, 2, 3)
            b = (*a,)
            assert a == b
            """)
        # case for `BUILD_SET_UNPACK`
        self.assert_ok("""\
            a = {1, 2, 3}
            b = {*a}
            assert a == b
            """)
        # case for `BUILD_MAP_UNPACK`
        self.assert_ok("""\
            a = {'a': 1, 'b': 2, 'c': 3}
            b = {**a}
            assert a == b
            """)

    def test_calling_method_with_unpacking(self):
        # case for `BUILD_MAP_UNPACK_WITH_CALL`
        self.assert_ok("""\
            def foo(**kwargs):
                pass
            def bar(items):
                foo(**items, c=3)
            data = {'a': 1, 'b': 2}
            bar(data)
            """)
        self.assert_ok("""\
            def foo(**kwargs):
                pass
            def bar(items):
                foo(**items, **{3})
            data = {'a': 1, 'b': 2}
            bar(data)
            """, raises=TypeError)
