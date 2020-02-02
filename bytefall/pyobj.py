import collections, types
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

    def __iter__(self):
        return self

    def next(self):
        return self.send(None)

    def send(self, value=None):
        if not self.gi_running and value is not None:
            raise TypeError("Can't send non-None value to a just-started generator")
        self.gi_frame.stack.append(value)
        self.gi_running = True
        vm = get_vm()
        val = vm.resume_frame(self.gi_frame)
        if not self.gi_running:
            raise StopIteration(val)
        return val

    __next__ = next
