"""
These tests should be run when version of Python >= 3.4
"""

import pytest
from . import vmtest


@pytest.mark.skip(reason='run these tests until issues of importing '
    '`asyncio.coroutine` is resolved')
class TestCoroutine(vmtest.VmTestCase):
    def test_run_awaitable_object(self):
        # py34, generator-based coroutine
        # which will be removed in CPython 3.10
        self.assert_ok("""\
            import asyncio

            @asyncio.coroutine
            def foo():
                return 1

            @asyncio.coroutine
            def coro():
                ret = yield from foo()
                return ret

            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(coro())
            print(result)
            """)

    def test_not_awaited_coroutine(self):
        self.assert_ok("""\
            import asyncio
            @asyncio.coroutine
            def foo():
                await 1
            foo()
            """)
