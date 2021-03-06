import dis, functools, inspect, six, sys, traceback, types, warnings
from asyncio import futures
from asyncio.coroutines import _DEBUG
from asyncio.coroutines import CoroWrapper as _CoroWrapper

# NOTE: in Py37, `collections.abc.Coroutine` and `collections.abc.Awaitable`
# are import directly. To keep the same implementation for Python > 3.4, we
# use the try-except block to handle this (which is same as the impl. in
# module `asyncio.coroutines` for Python 3.4 ~ 3.6)
try:
    from collections.abc import Awaitable as _AwaitableABC
except ImportError:
    _AwaitableABC = None

_is_coroutine = object()


from bytefall._internal.cache import GlobalCache
from bytefall._internal.utils import get_vm


__all__ = [
    'Generator', 'Coroutine', 'AsyncGenerator', 'AIterWrapper',
    'AsyncGenWrappedValue', '_gen_yf', '_coro_get_awaitable_iter',
    'coroutine',
]


class Generator(object):
    def __init__(self, g_frame):
        self.gi_frame = g_frame
        self.gi_code = g_frame.f_code  # https://bugs.python.org/issue1473257
        self.gi_running = False
        self.gi_yieldfrom = None       # added in py35
        self._finished = False         # for internal use only

    def __iter__(self):
        return self

    def __next__(self):
        return self.send(None)

    def send(self, value=None, exc=None):
        return gen_send_ex(self, value=value, exc=exc)

    def throw(self, exctype, val=None, tb=None):
        return gen_throw(self, exctype, val=val, tb=tb)

    def close(self):
        # just call `gen_close` without returning value to make this API
        # match builtin `generator.close()`
        gen_close(self)

    def __del__(self):
        if self.gi_frame is None or self._finished:
            return
        if self.gi_code and gen_is_coroutine(self) and self.gi_frame.f_lasti == 0:
            last_exception = GlobalCache().get('last_exception', None)
            if last_exception is None:
                warnings.warn(
                    "coroutine '%s' was never awaited" % self.gi_code.co_name,
                    RuntimeWarning
                )
        else:
            # TODO: unraisable error will be logged here in CPython impl.
            pass


def match_exception(x, y):
    if not inspect.isclass(inspect):
        _cls = type(x)
    else:
        _cls = x
    return isinstance(_cls, y) or issubclass(_cls, y)


def _gen_yf(gen):
    """Get another generator object.

    Corresponding impl.:
    https://github.com/python/cpython/blob/3.5/Objects/genobject.c#L272-L289
    """
    yf = None
    f = gen.gi_frame

    # XXX: `f_lasti` might exceed the length of `f_code.co_code` here, but it
    # seems not a possible case in CPython implementation. Maybe we have to
    # recheck it.
    if f and f.f_lasti < len(f.f_code.co_code):
        byte_code = f.f_code.co_code
        op = byte_code[f.f_lasti]
        if op != dis.opmap['YIELD_FROM']:
            return None
        yf = f.top()
    return yf


def gen_send_ex(gen, value=None, exc=None):
    if gen.gi_running:
        # TODO: error message for coroutine
        raise ValueError('generator already executing')
    if gen._finished:
        raise StopIteration
    if gen.gi_frame.f_lasti == 0 and value is not None:
        raise TypeError("Can't send non-None value to a just-started generator")
    gen.gi_frame.stack.append(value)

    # Run frame and get returned value instantly, and `gi_running` is True
    # only in this duration.
    # https://github.com/python/cpython/blob/3.5/Objects/genobject.c#L140-L142
    gen.gi_running = True
    val = None
    vm = get_vm()
    try:
        val = vm.resume_frame(gen.gi_frame, exc=exc)
    finally:
        gen.gi_running = False

    # NOTE: our implementation is different from CPython here.
    # In CPython, `gi_frame.f_stacktop` is used to check whether a generator
    # is exhausted or not.
    # https://github.com/python/cpython/blob/3.5/Python/ceval.c#L1191
    # https://github.com/python/cpython/blob/3.5/Objects/genobject.c#L152
    if gen._finished:
        raise StopIteration(val)

    return val


def gen_throw(gen, exctype, val=None, tb=None):
    if tb and not isinstance(tb, types.TracebackType):
        raise TypeError('throw() third argument must be a traceback object')

    if isinstance(val, str):    # XXX: wrap `val` to an Exception instance
        val = exctype(val)

    yf = _gen_yf(gen)
    ret = None

    if yf:
        # XXX: cannot make sure `exctype` is actually a type?
        if match_exception(exctype, GeneratorExit):
            gen.gi_running = True
            err = gen_close_iter(yf)
            gen.gi_running = False
            if err < 0:
                try:
                    val = gen.send(None, exc=GeneratorExit)
                except GeneratorExit:
                    pass
                # val = gen.send(None, exc=GeneratorExit)
                return val
            gen._finished = True
            six.reraise(exctype, val, tb)
        if isinstance(yf, Generator):
            gen.gi_running = True
            try:
                ret = yf.throw(exctype, val, tb)
            finally:
                gen._finished = True
                gen.gi_running = False
        else:
            meth = getattr(yf, 'throw', None)
            if meth is None:
                gen._finished = True
                six.reraise(exctype, val, tb)
            gen.gi_running = True
            ret = meth(exctype, val, tb)
            gen.gi_running = False
        if ret is None:
            val = None
            ret = gen.gi_frame.pop()
            assert ret == yf
            gen.gi_frame.f_lasti += 1
            ret = gen.send(val)
        return ret
    else:
        GlobalCache().set('last_exception', (exctype, val, tb))
        try:
            val = gen.send(None, exc=exctype)
        finally:
            gen._finished = True
        return val


def gen_close(gen):
    """Interal helper function to close a generator.

    Corresponding impl.:
    https://github.com/python/cpython/blob/3.5/Objects/genobject.c#L291-L322
    """
    yf = _gen_yf(gen)
    retval = None
    err = 0
    exc = None
    try:
        if yf:
            gen.gi_running = True
            err = gen_close_iter(yf)
            gen.gi_running = False
        if err == 0:
            GlobalCache().set('last_exception', (GeneratorExit, None, None))
            exc = GeneratorExit

        retval = gen.send(None, exc=exc)
        if retval is not None:
            raise RuntimeError('generator ignored GeneratorExit')
    except (StopIteration, GeneratorExit):
        # generator is closed normally
        gen._finished = True
        return None
    return -1


def gen_close_iter(gen):
    """Interal helper function to close a subiterator.

    Corresponding impl.:
    https://github.com/python/cpython/blob/3.5/Objects/genobject.c#L291-L322
    """
    if isinstance(gen, Generator):
        if gen_close(gen) == -1:
            return -1
    else:
        meth = getattr(gen, 'close', None)
        if (meth is not None) and (meth() is None):
            return -1
    return 0


def gen_is_coroutine(o):
    # CO_ITERABLE_COROUTINE = 0x0080
    return (
        isinstance(o, (Generator, types.GeneratorType)) and
        bool(o.gi_code.co_flags & 0x0080)
    )

def gen_is_iterable_coroutine(o):
    # CO_ITERABLE_COROUTINE = 0x0100
    return (
        isinstance(o, (Generator, types.GeneratorType)) and
        bool(o.gi_code.co_flags & 0x0100)
    )


class CoroWrapper(_CoroWrapper):
    # We borrow the implementation from `asyncio.coroutines.CoroWrapper`,
    # so that it will be easily to make it compatiable with the actual
    # `asyncio` system.
    def __init__(self, gen, func=None):
        assert isinstance(gen, Generator)
        self.gen = gen
        self.func = func
        self._source_traceback = traceback.extract_stack(sys._getframe(1))
        self.cw_coroutine = None
        self.__name__ = getattr(gen, '__name__', None)
        self.__qualname__ = getattr(gen, '__qualname__', None)

    @property
    def _finished(self):
        return self.gen._finished

    @_finished.setter
    def _finished(self, value):
        self.gen._finished = value


def _coro_get_awaitable_iter(o):
    """Interal helper function to get an awaitable iterator.

    Corresponding impl.:
    https://github.com/python/cpython/blob/3.5/Objects/genobject.c#L783-L823
    """
    if isinstance(o, (Coroutine, CoroWrapper)) or gen_is_iterable_coroutine(o):
        return o

    if hasattr(o, '__await__'):
        res = o.__await__()
        if res:
            if isinstance(o, (Coroutine, CoroWrapper)) or gen_is_coroutine(res):
                raise TypeError('__await__() returned a coroutine')
            else:
                try:
                    iterable = iter(res)
                except TypeError as e:
                    raise TypeError(
                        '__await__() returned non-iterator of type '
                        % res.__class__.__name__
                    ) from e
        return res
    else:
        raise TypeError(
            "object %s can't be used in 'await' expression" % o.__class__.__name__
        )


def isfuture(obj):
    return (hasattr(obj.__class__, '_asyncio_future_blocking') and
            obj._asyncio_future_blocking is not None)


def coroutine(func):
    """A decorator to mark coroutines, and this implementation is modified
    from `asyncio.coroutines.coroutine`.

    The reason why this should be done is that the implementation of
    `asyncio.coroutine` relies on native types and functions (e.g.
    types.GeneratorType, inspect.isgeneratorfunction, ...). However, some
    of those native types and functions are re-implemented by us to run in
    virtual machine. Therefore, this should be used to replace the original
    one to make `@asyncio.coroutine` work.
    """
    # Return directly if given function is a coroutine.
    if func.__code__.co_flags & 0x0080:
        return func

    if isinstance(func, Generator):
        coro = func
    else:
        @functools.wraps(func)
        def coro(*args, **kw):
            res = func(*args, **kw)
            if isfuture(res) or isinstance(res, (Generator, CoroWrapper)):
                res = yield from res
            elif _AwaitableABC is not None:
                try:
                    await_meth = res.__await__
                except AttributeError:
                    pass
                else:
                    if isinstance(res, _AwaitableABC):
                        res = yield from await_meth()
            return res

    if not _DEBUG:
        wrapper = coro
    else:
        @functools.wraps(func)
        def wrapper(*args, **kwds):
            w = CoroWrapper(coro(*args, **kwds), func=func)
            if w._source_traceback:
                del w._source_traceback[-1]
            w.__name__ = getattr(func, '__name__', None)
            w.__qualname__ = getattr(func, '__qualname__', None)
            return w

    wrapper._is_coroutine = _is_coroutine  # For iscoroutinefunction().
    return wrapper


class Coroutine(object):
    """Coroutine. (PyCoroObject)

    Corresponding impl.:
    https://github.com/python/cpython/blob/3.6/Objects/genobject.c#L933-L1047
    """
    def __init__(self, gen):
        self.gen = gen
        self.cr_frame = self.gen.gi_frame
        self.cr_running = self.gen.gi_running
        self.cr_code = self.gen.gi_code

    def __await__(self):
        cw = CoroWrapper(self.gen)
        cw.cw_coroutine = self
        return cw

    @property
    def cr_await(self):
        return _gen_yf(self)

    @property
    def _finished(self):
        return self.gen._finished

    @_finished.setter
    def _finished(self, value):
        self.gen._finished = value

    def send(self, value=None):
        return gen_send_ex(self.gen, value)

    def throw(self, exctype, val=None, tb=None):
        return gen_throw(self.gen, exctype, val=val, tb=tb)

    def close(self):
        gen_close(self.gen)


from enum import Enum
class AwaitableState(Enum):
    AWAITABLE_STATE_INIT = 0
    AWAITABLE_STATE_ITER = 1
    AWAITABLE_STATE_CLOSED = 3
del Enum


class AsyncGenerator(object):
    """Async generator. (PyAsyncGenObject)

    See also: https://www.python.org/dev/peps/pep-0525/#implementation-details

    Corresponding impl.:
    https://github.com/python/cpython/blob/3.6/Objects/genobject.c#L1355-L1502
    """
    def __init__(self, gen):
        self.gen = gen
        self.ag_code = self.gen.gi_code
        self.ag_frame = self.gen.gi_frame
        self.ag_running = self.gen.gi_running
        self.ag_closed = False

    def __aiter__(self):
        return self

    def __anext__(self):
        return AsyncGenASend(self, None)

    @property
    def ag_await(self):
        return _gen_yf(self)

    @property
    def _finished(self):
        return self.gen._finished

    @_finished.setter
    def _finished(self, value):
        self.gen._finished = value

    def asend(self, value=None):
        return AsyncGenASend(self, value)

    def aclose(self):
        return AsyncGenAThrow(self, None)

    def athrow(self, *args):
        # args: exctype[,value[,traceback]]
        return AsyncGenAThrow(self, args)


class AsyncGenASend(object):
    """Async generator Asend awaitable. (PyAsyncGenAsendObject)
    This is an awaitable object that implements `__anext__()` and `asend()` methods
    of `AsyncGenerator`.

    Corresponding impl.:
    https://github.com/python/cpython/blob/3.6/Objects/genobject.c#L1588-L1735
    """
    def __init__(self, gen, sendval):
        self.ags_gen = gen
        self.ags_state = AwaitableState.AWAITABLE_STATE_INIT
        self.ags_sendval = sendval

    def __next__(self):
        return self.send(None)

    def __await__(self):
        return self

    def __iter__(self):
        return self

    def send(self, value=None):
        gen = self.ags_gen.gen
        if self.ags_state == AwaitableState.AWAITABLE_STATE_CLOSED:
            raise StopIteration(None)
        if self.ags_state == AwaitableState.AWAITABLE_STATE_INIT:
            if value is None:
                value = self.ags_sendval
            self.ags_state = AwaitableState.AWAITABLE_STATE_ITER

        result, exc = None, None
        try:
            result = gen_send_ex(gen, value)
        except (Exception, BaseException) as e:
            exc = e

        try:
            result = async_gen_unwrap_value(gen, result, exc=exc)
        finally:
            if result is None:
                self.ags_state = AwaitableState.AWAITABLE_STATE_CLOSED
        return result

    def throw(self, *args, **kwargs):
        gen = self.ags_gen.gen
        if self.ags_state == AwaitableState.AWAITABLE_STATE_CLOSED:
            raise StopIteration(None)

        result, exc = None, None
        try:
            result = gen_throw(gen, *args, **kwargs)
        except (Exception, BaseException) as e:
            exc = e

        try:
            result = async_gen_unwrap_value(gen, result, exc=exc)
        finally:
            if result is None:
                self.ags_state = AwaitableState.AWAITABLE_STATE_CLOSED
        return None

    def close(self):
        self.ags_state = AwaitableState.AWAITABLE_STATE_CLOSED


class AsyncGenAThrow(object):
    """Async generator AThrow awaitable. (PyAsyncGenThrowObject)
    This is an awaitable object that implements `athrow()` and `aclose()` methods
    of `AsyncGenerator`.

    Corresponding impl.:
    https://github.com/python/cpython/blob/3.6/Objects/genobject.c#L1854-L2078
    """
    def __init__(self, gen, args):
        self.agt_gen = gen
        self.agt_args = args
        self.agt_state = AwaitableState.AWAITABLE_STATE_INIT

    def __next__(self):
        return self.send(None)

    def __await__(self):
        return self

    def __iter__(self):
        return self

    def send(self, value=None):
        gen = self.agt_gen.gen
        f = gen.gi_frame
        retval = None

        if f is None or self.agt_state == AwaitableState.AWAITABLE_STATE_CLOSED:
            raise StopIteration(None)

        if self.agt_state == AwaitableState.AWAITABLE_STATE_INIT:
            if self.agt_gen.ag_closed:
                raise StopIteration(None)
            if value is not None:
                raise RuntimeError("can't send non-None value to a just-started coroutine")

            self.agt_state = AwaitableState.AWAITABLE_STATE_ITER
            if self.agt_args is None:
                self.agt_gen.ag_closed = True
                retval = gen_throw(gen, GeneratorExit)
                if retval is not None and isinstance(retval, AsyncGenWrappedValue):
                    raise RuntimeError('async generator ignored GeneratorExit')
            else:
                retval = None
                try:
                    retval = gen_throw(gen, *self.agt_args)
                except (StopAsyncIteration, GeneratorExit):
                    self.agt_state = AwaitableState.AWAITABLE_STATE_CLOSED
                    if self.agt_args is None:
                        raise StopIteration
                try:
                    retval = async_gen_unwrap_value(self.agt_gen, retval)
                except (StopAsyncIteration, GeneratorExit):
                    self.agt_state = AwaitableState.AWAITABLE_STATE_CLOSED
                    if self.agt_args is None:
                        raise StopIteration(None)
            return retval

        assert self.agt_state == AwaitableState.AWAITABLE_STATE_ITER
        try:
            retval = gen_send_ex(gen, value)
        except (StopAsyncIteration, GeneratorExit):
            self.agt_state = AwaitableState.AWAITABLE_STATE_CLOSED
            if self.agt_args is None:
                raise StopIteration

        if self.agt_args:
            return async_gen_unwrap_value(self.agt_gen, retval)
        else:
            if retval is not None and isinstance(retval, AsyncGenWrappedValue):
                raise RuntimeError('async generator ignored GeneratorExit')
            return retval

    def throw(self, *args, **kwargs):
        retval = None
        if self.agt_state == AwaitableState.AWAITABLE_STATE_INIT:
            raise RuntimeError("can't send non-None value to a just-started coroutine")
        if self.agt_state == AwaitableState.AWAITABLE_STATE_CLOSED:
            raise StopIteration(None)
        retval = gen_throw(self.agt_gen, *args, **kwargs)
        if self.agt_args:
            return async_gen_unwrap_value(self.agt_gen, retval)
        else:
            if isinstance(retval, AsyncGenWrappedValue):
                raise RuntimeError('async generator ignored GeneratorExit')
            return retval

    def close(self):
        self.agt_state = AwaitableState.AWAITABLE_STATE_CLOSED


class AsyncGenWrappedValue(object):
    """Async generator value wrapper. (_PyAsyncGenWrappedValue)
    A wrapper used to wrap value which is directly yielded. (related to bytecode
    operation `YIELD_VALUE`)

    Corresponding impl.:
    https://github.com/python/cpython/blob/3.6/Objects/genobject.c#L1764-L1829
    """
    def __init__(self, value):
        self.agw_val = value


class AIterWrapper(object):
    """An __aiter__ wrapper.

    Check out bpo-27243 for details.
    """
    def __init__(self, aiter):
        self.ags_aiter = aiter

    def __next__(self):
        raise StopIteration(self.ags_aiter)


def async_gen_unwrap_value(gen, result, exc=None):
    if result is None:
        if isinstance(exc, (StopAsyncIteration, GeneratorExit)):
            gen.ag_closed = True
        raise StopAsyncIteration(None)
    if isinstance(result, AsyncGenWrappedValue):
        raise StopIteration(result.agw_val)
    return result
