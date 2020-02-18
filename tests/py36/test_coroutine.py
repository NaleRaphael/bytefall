"""
These tests should be run when version of Python >= 3.6
"""

import pytest
from .. import vmtest


# @pytest.mark.skip
class TestCoroutine(vmtest.VmTestCase):
    def test_run_awaitable_iterator(self):
        # # py36
        # # https://stackoverflow.com/questions/37549846/how-to-use-yield-inside-async-function
        # # GET_AITER

        # NOTE: 'yield' inside async function is valid since Py36
        self.assert_ok("""\
            import asyncio

            class Foo:
                async def __aiter__(self):
                    yield 1
                    yield 2
                    yield 3

            async def coro():
                async for v in Foo():
                    print(v)

            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(coro())
            print(result)
            """)

    def test_run_async_generator_function(self):
        self.assert_ok("""\
            import asyncio

            async def foo():
                for i in range(3):
                    await asyncio.sleep(0.001)
                    yield i

            async def coro():
                async for v in foo():
                    print(v)

            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(coro())
            print(result)
            """)

    @pytest.mark.skipif_py_ge((3, 7))
    def test_run_async_iterator(self):
        # Sinece Py37, support for wrapping an awaitable to async iterator
        # is dropped. It raise an TypeError instead.
        self.assert_ok("""\
            import asyncio

            class SimpleAsyncIterartor:
                def __init__(self, stop):
                    self.i = 0
                    self.stop = stop

                async def __aiter__(self):
                    return self

                async def __anext__(self):
                    if self.i < self.stop:
                        self.i += 1
                        await asyncio.sleep(0.001)
                        return self.i
                    else:
                        raise StopAsyncIteration

            async def coro():
                async for v in SimpleAsyncIterartor(3):
                    print(v)

            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(coro())
            print(result)
            """)
