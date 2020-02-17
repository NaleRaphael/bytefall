"""
These tests should be run when version of Python >= 3.7
"""

import pytest
from .. import vmtest


class TestCoroutine(vmtest.VmTestCase):
    def test_run_awaitable_iterator(self):
        # This case is same as the one in `py35/test_coroutine`, but it
        # should raise a TypeError (__aiter__ should return an asynchronous
        # iterator directly)
        # TODO: Currently, name of the object in error message run in vm 
        # is not equal to the one run in real Python runtime.
        self.assert_ok("""\
            import asyncio

            class foo:
                def __init__(self, stop):
                    self.i = 0
                    self.stop = stop

                async def __aiter__(self):
                    return self

                async def __anext__(self):
                    if self.i < self.stop:
                        self.i += 1
                        return self.i
                    else:
                        raise StopAsyncIteration

            async def coro():
                async for v in foo(3):
                    print(v)

            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(coro())
            print(result)
            """, raises=TypeError)
