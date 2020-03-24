from .frameobject import Frame
from .generatorobject import (
    Generator, Coroutine, AsyncGenerator
)
from .methodobject import Method
from bytefall._internal.utils import get_vm


__all__ = ['Function']


class Function(object):
    __slots__ = [
        '__name__', '__code__', '__globals__', '__defaults__', '__closure__',
        '__dict__', '__doc__', '__annotations__', '__kwdefaults__',
    ]
    def __init__(self, code, globs, name, defaults, closure):
        # NOTE: order of arguments is modified to fit the implementation of builtin
        # `function` class:
        # https://github.com/python/cpython/blob/3.4/Objects/funcobject.c#L476-L477
        self.__dict__ = {}
        self.__name__ = code.co_name
        self.__code__ = code
        self.__globals__ = globs
        self.__defaults__ = None if defaults is None else tuple(defaults)
        self.__kwdefaults__ = {}
        self.__closure__ = closure
        self.__doc__ = code.co_consts[0] if code.co_consts else None
        self.__annotations__ = {}
        self.__qualname__ = name

    def __repr__(self):
        return '<Function %s at 0x%016X>' % (self.__qualname__, id(self))

    def __get__(self, instance, owner):
        return self if instance is None else Method(instance, owner, self)

    def __call__(self, *args, **kwargs):
        code = self.__code__
        argc = code.co_argcount
        kwargc = code.co_kwonlyargcount
        # posargc = code.co_posonlyargcount     # TODO: new in Py38

        # NOTE: For both argc, function signature should be either:
        #   ```def fn(x=1, y=2): ...```, where posargc is 2, kwargc is 0
        #   ```def fn(*, x=1, y=2): ...```, where posargc is 0, kwargc is 2
        #   It is impossible that both kwargc and posargc are not 0.
        # assert kwargc ^ posargc == (kwargc + posargc), \
        #     "at least one of `kwargc` or `posargc` should be 0"

        varargs = 0 != (code.co_flags & 0x04)   # CO_VARARGS: 0x0004
        varkws = 0 != (code.co_flags & 0x08)    # CO_VARKEYWORDS: 0x0008
        params = code.co_varnames[:argc+kwargc+varargs+varkws]

        defaults = self.__defaults__ if self.__defaults__ else ()
        kwdefaults = self.__kwdefaults__
        nrequired = -(len(defaults)+int(varkws)) if defaults else argc

        f_locals = dict(zip(params[nrequired:], defaults))
        f_locals.update(kwdefaults)
        f_locals.update(dict(zip(params, args)))
        if varargs:
            # for the case: ```def foo(*args): ...```
            f_locals[params[argc]] = args[argc:]
        elif argc < len(args):
            raise TypeError(
                    '%s() takes %d positional arguments but %d %s given'
                    % (self.__name__, argc,
                       len(args), 'was' if len(args) == 1 else 'were')
                )

        if varkws:
            # for the case: ```def foo(**kwargs): ... ```
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

        # handling generator
        CO_GENERATOR = 0x0020
        CO_COROUTINE = 0x0080
        CO_ITERABLE_COROUTINE = 0x0100
        CO_ASYNC_GENERATOR = 0x0200

        if self.__code__.co_flags & (CO_GENERATOR | CO_COROUTINE | CO_ASYNC_GENERATOR):
            gen = Generator(frame)
            if self.__code__.co_flags & CO_COROUTINE:
                gen = Coroutine(gen)
            elif self.__code__.co_flags & CO_ASYNC_GENERATOR:
                gen = AsyncGenerator(gen)
            frame.generator = gen
            retval = gen
        else:
            retval = vm.run(frame)
        return retval
