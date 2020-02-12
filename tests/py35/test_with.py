"""
These tests should be run when version of Python >= 3.5
"""

import pytest
from .. import vmtest


class TestAsyncWith(vmtest.VmTestCase):
    def test_simple_async_context_manager(self):
        self.assert_ok("""\
            import asyncio

            l = []
            class AsyncNullContext:
                async def __aenter__(self):
                    l.append('i')
                    return 17

                async def __aexit__(self, exctype, val, tb):
                    l.append('o')
                    return False

            async def coro():
                for i in range(3):
                    async with AsyncNullContext() as val:
                        assert val == 17
                        l.append('w')
                    l.append('e')
                l.append('r')
                s = ''.join(l)
                print("Look: %r" % s)
                assert s == "iwoeiwoeiwoer"

            loop = asyncio.get_event_loop()
            loop.run_until_complete(coro())
            """)

    def test_raise_in_async_context_manager(self):
        self.assert_ok("""\
            import asyncio

            l = []
            class AsyncNullContext:
                async def __aenter__(self):
                    l.append('i')
                    return self

                async def __aexit__(self, exctype, val, tb):
                    assert exctype is ValueError, \\
                        'Expected ValueError: %r' % exctype
                    l.append('o')
                    return False

            async def coro():
                try:
                    async with AsyncNullContext():
                        l.append('w')
                        raise ValueError('Boo!')
                    l.append('e')
                except ValueError:
                    l.append('x')
                l.append('r')
                s = ''.join(l)
                print('Look: %r' % s)
                assert s == 'iwoxr'

            loop = asyncio.get_event_loop()
            loop.run_until_complete(coro())
            """)

    def test_suppressed_raise_in_async_context_manager(self):
        self.assert_ok("""\
            import asyncio

            l = []
            class AsyncNullContext:
                async def __aenter__(self):
                    l.append('i')
                    return self

                async def __aexit__(self, exctype, val, tb):
                    assert exctype is ValueError, \\
                        'Expected ValueError: %r' % exctype
                    l.append('o')
                    return True     # suppress exception

            async def coro():
                try:
                    async with AsyncNullContext():
                        l.append('w')
                        raise ValueError('Boo!')
                    l.append('e')
                except ValueError:
                    l.append('x')
                l.append('r')
                s = ''.join(l)
                print('Look: %r' % s)
                assert s == 'iwoer'

            loop = asyncio.get_event_loop()
            loop.run_until_complete(coro())
            """)

    def test_return_in_async_with(self):
        self.assert_ok("""\
            import asyncio

            l = []
            class AsyncNullContext:
                async def __aenter__(self):
                    l.append('i')
                    return self

                async def __aexit__(self, exctype, val, tb):
                    l.append('o')
                    return False

            async def use_with(val):
                print('in use_with: %s' % val)
                async with AsyncNullContext():
                    l.append('w')
                    return val
                l.append('e')

            async def coro():
                assert await use_with(23) == 23
                l.append('r')
                s = ''.join(l)
                print('Look: %r' % s)
                assert s == 'iwor'

            loop = asyncio.get_event_loop()
            loop.run_until_complete(coro())
            """)

    def test_continue_in_async_with(self):
        self.assert_ok("""\
            import asyncio

            l = []
            class AsyncNullContext:
                async def __aenter__(self):
                    l.append('i')
                    return self

                async def __aexit__(self, exctype, val, tb):
                    l.append('o')
                    return False

            async def coro():
                for i in range(3):
                    async with AsyncNullContext():
                        l.append('w')
                        if i % 2:
                            continue
                        l.append('z')
                    l.append('e')

                l.append('r')
                s = ''.join(l)
                print('Look: %r' % s)
                assert s == 'iwzoeiwoiwzoer'

            loop = asyncio.get_event_loop()
            loop.run_until_complete(coro())
            """)

    def test_break_in_async_with(self):
        self.assert_ok("""\
            import asyncio

            l = []
            class AsyncNullContext:
                async def __aenter__(self):
                    l.append('i')
                    return self

                async def __aexit__(self, exctype, val, tb):
                    l.append('o')
                    return False

            async def coro():
                for i in range(3):
                    async with AsyncNullContext():
                        l.append('w')
                        if i % 2:
                            break
                        l.append('z')
                    l.append('e')

                l.append('r')
                s = ''.join(l)
                print('Look: %r' % s)
                assert s == 'iwzoeiwor'

            loop = asyncio.get_event_loop()
            loop.run_until_complete(coro())
            """)

    def test_raise_in_async_with(self):
        self.assert_ok("""\
            import asyncio

            l = []
            class AsyncNullContext:
                async def __aenter__(self):
                    l.append('i')
                    return self

                async def __aexit__(self, exctype, val, tb):
                    l.append('o')
                    return False

            async def coro():
                try:
                    async with AsyncNullContext():
                        l.append('w')
                        raise ValueError('oops!')
                        l.append('z')
                    l.append('e')
                except ValueError as e:
                    assert str(e) == 'oops!', 'Not an expected error message'
                    l.append('x')
                l.append('r')
                s = ''.join(l)
                print('Look: %r' % s)
                assert s == 'iwoxr', 'What!?'

            loop = asyncio.get_event_loop()
            loop.run_until_complete(coro())
            """)

    def test_at_async_context_manager_simplified(self):
        self.assert_ok("""\
            import asyncio
            import sys

            class GeneratorAsyncContextManager(object):
                def __init__(self, gen):
                    self.gen = gen

                async def __aenter__(self):
                    try:
                        return next(self.gen)
                    except StopIteration:
                        raise RuntimeError("generator didn't yield")

                async def __aexit__(self, exctype, val, tb):
                    if exctype is None:
                        try:
                            next(self.gen)
                        except StopIteration:
                            return
                        else:
                            raise RuntimeError("generator didn't stop")
                    else:
                        if val is None:
                            val = exctype()
                        try:
                            self.gen.throw(exctype, val, tb)
                            raise RuntimeError(
                                "generator didn't stop after throw()"
                            )
                        except StopIteration as exc:
                            return exc is not val
                        except:
                            if sys.exc_info()[1] is not val:
                                raise

            def contextmanager(func):
                def helper(*args, **kwds):
                    return GeneratorAsyncContextManager(func(*args, **kwds))
                return helper

            @contextmanager
            def my_context_manager(val):
                yield val

            async def coro():
                try:
                    async with my_context_manager(17) as x:
                        assert x == 17
                        raise ValueError('Nooooo!')
                except ValueError as e:
                    assert str(e) == 'Nooooo!'

            loop = asyncio.get_event_loop()
            loop.run_until_complete(coro())
            """)
