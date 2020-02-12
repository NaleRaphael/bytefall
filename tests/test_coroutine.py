"""
These tests should be run when version of Python >= 3.4
"""

import pytest
from . import vmtest


class TestCoroutine(vmtest.VmTestCase):
    @pytest.mark.skip(reason='this case works while running it as a script, '
    'but it will fail in test runner currently. Cause of failure is that '
    '`asyncio.coroutine` was patched while running this case in vm, but it '
    'was not restored after that.')
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
                return 1
            foo()
            """)
