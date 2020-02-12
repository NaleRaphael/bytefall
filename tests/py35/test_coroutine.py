"""
These tests should be run when version of Python >= 3.5
"""

import pytest
from .. import vmtest


class TestCoroutine(vmtest.VmTestCase):
    def test_run_awaitable_object(self):
        self.assert_ok("""\
            import asyncio

            async def foo():
                return 1

            async def coro():
                await foo()

            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(coro())
            print(result)
            """)

    def test_run_awaitable_iterator(self):
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
            """)

        # # py36
        # # GET_AITER
        # self.assert_ok("""\
        #     import asyncio

        #     class Foo:
        #         async def __aiter__(self):
        #             yield 1
        #             yield 2

        #     async def coro():
        #         async for v in Foo():
        #             print(v)

        #     loop = asyncio.get_event_loop()
        #     result = loop.run_until_complete(coro())
        #     print(result)
        #     """)

    def test_not_awaited_coroutine(self):
        # TODO: catch warning
        self.assert_ok("""\
            import asyncio
            async def foo():
                await 1
            foo()
            """)

    def test_async_for_loop_with_invalid_object(self):
        self.assert_ok("""\
            import asyncio

            class foo:
                async def __aiter__(self):
                    return (v for v in range(3))

            async def coro():
                # 'async for' requires an iterator with __anext__ method
                async for v in foo():
                    print(v)

            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(coro())
            print(result)
            """, raises=TypeError)
