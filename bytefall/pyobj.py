import collections, types, dis, inspect
import six

from .cache import GlobalCache
from .pyframe import Frame
from ._utils import get_vm


class Method(object):
    def __init__(self, obj, _class, func):
        self.__self__ = obj
        self._class = _class
        self.__func__ = func

    def __repr__(self):
        name = '%s.%s' % (self._class.__name__, self.__func__.__name__)
        return '<bound method %s of %s>' % (name, self.__self__)

    def __call__(self, *args, **kwargs):
        return self.__func__(self.__self__, *args, **kwargs)


class Function(object):
    __slots__ = [
        '__name__', '__code__', '__globals__', '__defaults__', '__closure__',
        '__dict__', '__doc__',
    ]
    def __init__(self, code, globs, name, defaults, closure):
        # NOTE: order of arguments is modified to fit the implementation of builtin
        # `function` class:
        # https://github.com/python/cpython/blob/3.4/Objects/funcobject.c#L476-L477
        self.__dict__ = {}
        self.__name__ = name or code.co_name
        self.__code__ = code
        self.__globals__ = globs
        self.__defaults__ = tuple(defaults)
        self.__closure__ = closure
        self.__doc__ = code.co_consts[0] if code.co_consts else None
        # self.__qualname__ = None  # TODO: impl this

    def __repr__(self):
        return '<Function %s at 0x%08x>' % (self.__name__, id(self))

    def __get__(self, instance, owner):
        return self if instance is None else Method(instance, owner, self)

    def __call__(self, *args, **kwargs):
        code = self.__code__
        argc = code.co_argcount
        # NOTE: co_flags:
        # https://github.com/python/cpython/blob/3.4/Include/code.h#L53-L59
        varargs = 0 != (code.co_flags & 0x04)   # CO_VARARGS: 0x0004
        varkws = 0 != (code.co_flags & 0x08)    # CO_VARKEYWORDS: 0x0008
        params = code.co_varnames[:argc+varargs+varkws]

        defaults = self.__defaults__
        nrequired = -(len(defaults)+int(varkws)) if defaults else argc

        f_locals = dict(zip(params[nrequired:], defaults))
        f_locals.update(dict(zip(params, args)))
        if varargs:
            # for the case: ```def foo(a, b, *args): ...```
            f_locals[params[argc]] = args[argc:]
        elif argc < len(args):
            raise TypeError('%s() takes up to %d positional argument(s) but got %d'
                            % (self.__name__, argc, len(args)))

        if varkws:
            f_locals[params[-1]] = varkw_dict = {}
        for kw, value in kwargs.items():
            if kw in params:
                f_locals[kw] = value
            elif varkws:
                varkw_dict[kw] = value
            else:
                raise TypeError('%s() got an unexpected keyword argument %r'
                                % (self.__name__, kw))

        missing = [v for v in params[slice(0, nrequired)] if v not in f_locals]
        if missing:
            raise TypeError("%s() missing %d required positional argument%s: %s"
                            % (code.co_name,
                               len(missing), 's' if 1 < len(missing) else '',
                               ', '.join(map(repr, missing))))

        vm = get_vm()
        frame = Frame(code, self.__globals__, f_locals, self.__closure__, vm.frame)

        # handling generator, CO_GENERATOR: 0x0020
        CO_GENERATOR = 0x0020
        if self.__code__.co_flags & CO_GENERATOR:
            gen = Generator(frame)
            frame.generator = gen
            retval = gen
        else:
            retval = vm.run(frame)
        return retval


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
        if self.gi_running:
            raise ValueError('generator already executing')
        if self._finished:
            raise StopIteration
        if self.gi_frame.f_lasti == 0 and value is not None:
            raise TypeError("Can't send non-None value to a just-started generator")
        self.gi_frame.stack.append(value)

        # Run frame and get returned value instantly, and `gi_running` is True
        # only in this duration.
        # https://github.com/python/cpython/blob/3.5/Objects/genobject.c#L140-L142
        self.gi_running = True
        val = None
        vm = get_vm()
        try:
            val = vm.resume_frame(self.gi_frame, exc=exc)
        finally:
            self.gi_running = False

        # NOTE: our implementation is different from CPython here.
        # In CPython, `gi_frame.f_stacktop` is used to check whether a generator
        # is exhausted or not.
        # https://github.com/python/cpython/blob/3.5/Python/ceval.c#L1191
        # https://github.com/python/cpython/blob/3.5/Objects/genobject.c#L152
        if self._finished:
            raise StopIteration(val)

        return val

    def throw(self, exctype, val=None, tb=None):
        if tb and not isinstance(tb, types.TracebackType):
            raise TypeError('throw() third argument must be a traceback object')

        yf = _gen_yf(self)
        ret = None

        if yf:
            # XXX: cannot make sure `exctype` is actually a type?
            if match_exception(exctype, GeneratorExit):
                self.gi_running = True
                err = gen_close_iter(yf)
                self.gi_running = False
                if err < 0:
                    try:
                        val = self.send(None, exc=GeneratorExit)
                    except GeneratorExit:
                        pass
                    return val
                self._finished = True
                six.reraise(exctype, val, tb)
            if isinstance(yf, Generator):
                self.gi_running = True
                try:
                    ret = yf.throw(exctype, val, tb)
                finally:
                    self._finished = True
                    self.gi_running = False
            else:
                meth = getattr(yf, 'throw', None)
                if meth is None:
                    self._finished = True
                    six.reraise(exctype, val, tb)
                self.gi_running = True
                ret = meth(exctype, val, tb)
                self.gi_running = False
            if ret is None:
                val = None
                ret = self.gi_frame.pop()
                assert ret == yf
                self.gi_frame.f_lasti += 1
                ret = self.send(val)
            return ret
        else:
            GlobalCache().set('last_exception', (exctype, val, tb))
            try:
                val = self.send(None, exc=exctype)
            finally:
                self._finished = True
            return val

    def close(self):
        # just call `gen_close` without returning value to make this API
        # match builtin `generator.close()`
        gen_close(self)


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
