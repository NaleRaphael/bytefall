"""
Bytecode operations.
"""

from __future__ import print_function, division
import dis, operator
from inspect import isclass as inspect_isclass

from .pycell import Cell
from .pyframe import Frame
from .pyobj import Function, Generator, CoroWrapper, _gen_yf, _coro_get_awaitable_iter
from .exceptions import VirtualMachineError
from .cache import GlobalCache
from ._utils import get_vm


UNARY_OPERATORS = {
    'POSITIVE': operator.pos,   'NOT':    operator.not_,
    'NEGATIVE': operator.neg,   'INVERT': operator.invert,
}

BINARY_OPERATORS = {
    'POWER':    pow,             'ADD':      operator.add,
    'LSHIFT':   operator.lshift, 'SUBTRACT': operator.sub,
    'RSHIFT':   operator.rshift, 'MULTIPLY': operator.mul,
    'OR':       operator.or_,    'MODULO':   operator.mod,
    'AND':      operator.and_,   'TRUE_DIVIDE': operator.truediv,
    'XOR':      operator.xor,    'FLOOR_DIVIDE': operator.floordiv,
    'SUBSCR':   operator.getitem,
    # TODO: new operators in py35
    # 'MATRIX_MULTIPLY': operator.matmul
}
assert all([op.__qualname__ in dir(operator) for op in BINARY_OPERATORS.values()])

INPLACE_OPERATORS = {
    'POWER':    operator.ipow,    'ADD':      operator.iadd,
    'LSHIFT':   operator.ilshift, 'SUBTRACT': operator.isub,
    'RSHIFT':   operator.irshift, 'MULTIPLY': operator.imul,
    'OR':       operator.ior,     'MODULO':   operator.imod,
    'AND':      operator.iand,    'TRUE_DIVIDE': operator.itruediv,
    'XOR':      operator.ixor,    'FLOOR_DIVIDE': operator.ifloordiv,
    # 'SUBSCR':   operator.getitem,
    # TODO: new operators in py35
    # 'MATRIX_MULTIPLY': operator.imatmul
}
assert all([op.__qualname__ in dir(operator) for op in INPLACE_OPERATORS.values()])


def exception_match(x, y):
    """Check the relation between two given exception `x`, `y`:
    - `x` equals to `y`
    - `x` is a subclass/instance of `y`

    Note that `BaseException` should considered.

    e.g. `GeneratorExit` is a subclass of `BaseException` but which is not a
    subclass of `Exception`, and it is technically not an error.
    """
    return (
        (issubclass(x, Exception) or issubclass(x, BaseException))
        and issubclass(x, y)
    )

COMPARE_OPERATORS = [
    operator.lt,
    operator.le,
    operator.eq,
    operator.ne,
    operator.gt,
    operator.ge,
    lambda x, y: x in y,
    lambda x, y: x not in y,
    lambda x, y: x is y,
    lambda x, y: x is not y,
    exception_match,
]


class OperationClass(type):
    """A class providing a namespace for bytecode operations."""
    _unsupported_ops = []

    def __new__(cls, name, bases, local, **kwargs):
        for k, attr in local.items():
            if callable(attr) and not k.startswith('__'):
                local[k] = staticmethod(attr)
        new_cls = type.__new__(cls, name, bases, local)
        cls._set_removed_ops(new_cls, local.get('_unsupported_ops', None))
        return new_cls

    def _set_removed_ops(cls_instance, names):
        """Make operations listed in `_unsupported_ops` raise exception when
        they are called, and it will show the version in which it was removed.
        """
        if names is None:
            return
        if not all([n in dir(cls_instance) for n in names]):
            raise ValueError('Not all names exist in %s' % (cls_instance))

        def removed_op(func):
            def wrapper(*args, **kwargs):
                raise RuntimeError('Operation `%s` is removed in %s.'
                    % (func.__name__, cls_instance.__name__[-4:]))
            return wrapper

        for k in names:
            func = getattr(cls_instance, k)
            setattr(cls_instance, k, removed_op(func))


class Operation(metaclass=OperationClass):
    def __dir__(self):
        """Override this to remove operations listed in `_unsupported_ops`
        while `dir(OperationPyXX)` is called.
        """
        _set = set()
        isclass = inspect_isclass(self)
        bases = self.__bases__ if isclass else self.__class__.__bases__

        for base in bases:
            if issubclass(base, Operation):
                _set |= set(base.__dir__(base))
                _set -= set(getattr(self, '_unsupported_ops', []))
            else:
                _set |= set(dir(self))
        return list(_set)

    def POP_TOP(frame):
        frame.pop()

    def ROT_TWO(frame):
        a, b = frame.popn(2)
        frame.push(b, a)

    def ROT_THREE(frame):
        a, b, c = frame.popn(3)
        frame.push(b, c, a)

    def DUP_TOP(frame):
        frame.push(frame.top())

    def DUP_TOP_TWO(frame):
        a, b = frame.popn(2)
        frame.push(a, b, a, b)

    def NOP(frame):
        return

    def unary_operator(frame, op):
        x = frame.pop()
        frame.push(UNARY_OPERATORS[op](x))

    def binary_operator(frame, op):
        x, y = frame.popn(2)
        frame.push(BINARY_OPERATORS[op](x, y))

    def inplace_operator(frame, op):
        x, y = frame.popn(2)
        frame.push(INPLACE_OPERATORS[op](x, y))

    def COMPARE_OP(frame, opnum):
        x, y = frame.popn(2)
        frame.push(COMPARE_OPERATORS[opnum](x, y))

    def STORE_MAP(frame): # TODO: deprecated in py35 (exists only in py <= 34)
        the_map, val, key = frame.popn(3)
        the_map[key] = val
        frame.push(the_map)

    def STORE_SUBSCR(frame):
        val, obj, subscr = frame.popn(3)
        obj[subscr] = val

    def DELETE_SUBSCR(frame):
        obj, subscr = frame.popn(2)
        del obj[subscr]

    def GET_ITER(frame):
        frame.push(iter(frame.pop()))

    if 0:   # XXX: Only used in the interactive interpreter, not in modules.
        def PRINT_EXPR(frame):
            print(frame.pop())

    def LOAD_BUILD_CLASS(frame):
        frame.push(build_class)

    def YIELD_FROM(frame):
        u = frame.pop()
        x = frame.top()
        try:
            if isinstance(x, Generator) or isinstance(x, CoroWrapper):
                retval = x.send(u)
            else:
                retval = next(x)
            GlobalCache().set('return_value', retval)
        except StopIteration as e:
            frame.pop()
            frame.push(e.value)
        else:
            # YIELD_FROM decrements f_lasti, so that it will be called
            # repeatedly until a StopIteration is raised.
            frame.jump(frame.f_lasti - 1)
            # Returning 'yield' prevents the block stack cleanup code
            # from executing, suspending the frame in its current state.
            return 'yield'

    def BREAK_LOOP(frame):
        return 'break'

    def WITH_CLEANUP(frame):
        v = w = None
        u = frame.top()
        if u is None:
            exit_func = frame.pop(1)
        elif isinstance(u, str):
            if u in ('return', 'continue'):
                exit_func = frame.pop(2)
            else:
                exit_func = frame.pop(1)
            u = None
        elif issubclass(u, BaseException):
            w, v, u = frame.popn(3)
            tp, exc, tb = frame.popn(3)
            exit_func = frame.pop()
            frame.push(tp, exc, tb)
            frame.push(None)
            frame.push(w, v, u)
            block = frame.pop_block()
            assert block.type == 'except-handler'
            frame.push_block(block.type, block.handler, block.level-1)
        else:
            raise VirtualMachineError("Confused WITH_CLEANUP")

        exit_ret = exit_func(u, v, w)
        err = (u is not None) and bool(exit_ret)
        if err:
            # An error occurred, and was suppressed
            frame.push('silenced')

    def RETURN_VALUE(frame):
        GlobalCache().set('return_value', frame.pop())

        # NOTE: this should be compatiable with `CoroWrapper`
        if frame.generator:
            frame.generator._finished = True
        return 'return'

    def IMPORT_STAR(frame):
        mod = frame.pop()
        attrs = {k: getattr(mod, attr) for k in dir(mod) if k[0] != '_'}
        frame.f_locals.update(attrs)

    def YIELD_VALUE(frame):
        GlobalCache().set('return_value', frame.pop())
        return 'yield'

    def POP_BLOCK(frame):
        frame.block_stack.pop()

    def END_FINALLY(frame):
        v = frame.pop()
        if isinstance(v, str):
            why = v
            if why in ('return', 'continue'):
                GlobalCache().set('return_value', frame.pop())
            if why == 'silenced':
                block = frame.pop_block()
                assert block.type == 'except-handler'
                frame.unwind_block(block)
                why = None
        elif v is None:
            why = None
        elif issubclass(v, BaseException):
            exctype = v
            val = frame.pop()
            tb = frame.pop()
            GlobalCache().set('last_exception', (exctype, val, tb))
            why = 'reraise'
        else:
            raise VirtualMachineError("Confused END_FINALLY")
        return why


    def POP_EXCEPT(frame):
        block = frame.block_stack.pop()
        if block.type != 'except-handler':
            raise VirtualMachineError('popped block is not an except handler')
        frame.unwind_block(block)

    def STORE_NAME(frame, name):
        frame.f_locals[name] = frame.pop()

    def DELETE_NAME(frame, name):
        del frame.f_locals[name]

    def UNPACK_SEQUENCE(frame, count):
        seq = frame.pop()
        frame.push(*seq[::-1])

    def FOR_ITER(frame, jump):
        # NOTE: applied implementation from darius/tailbiter
        # create a local object `void` to make sure this instance is unique and
        # exist in here only, which can avoid collision of using other builtin
        # object like `None`, `False`...
        void = object()
        element = next(frame.top(), void)
        if element is void:
            frame.pop()
            frame.jump(jump)
        else:
            frame.push(element)

    def UNPACK_EX(frame, oparg):
        # NOTE: `before, vals, after = unpack(seq)`
        # where `argcnt == len(before)` and `argcntafter == len(after)`
        argcnt, argcntafter = (oparg & 0xFF), (oparg >> 8)
        totalargs = 1 + argcnt + argcntafter
        seq = list(frame.pop())

        if argcnt > len(seq):
            # https://github.com/python/cpython/blob/3.4/Python/ceval.c#L3794-L3796
            raise ValueError('need more than %d value%s to unpack' %
                (len(seq), '' if argcnt == 2 else 's'))
        if argcnt + argcntafter > len(seq):
            raise ValueError('need more than %d values to unpack' % len(seq))

        before = seq[:argcnt]
        vals = seq[argcnt:(-argcntafter if argcntafter else None)]
        after = seq[(-argcntafter if argcntafter else len(seq)):]

        frame.push(*after[::-1])
        frame.push(vals)
        frame.push(*before[::-1])

    def STORE_ATTR(frame, name):
        val, obj = frame.popn(2)
        setattr(obj, name, val)

    def DELETE_ATTR(frame, name):
        obj = frame.pop()
        delattr(obj, name)

    def STORE_GLOBAL(frame, name):
        frame.f_globals[name] = frame.pop()

    def DELETE_GLOBAL(frame, name):
        del frame.f_globals[name]

    def LOAD_CONST(frame, const):
        frame.push(const)

    def LOAD_NAME(frame, name):
        if name in frame.f_locals:   val = frame.f_locals[name]
        elif name in frame.f_globals:  val = frame.f_globals[name]
        elif name in frame.f_builtins: val = frame.f_builtins[name]
        else: raise NameError("name '%s' is not defined" % name)
        frame.push(val)

    def BUILD_TUPLE(frame, count):
        elts = frame.popn(count)
        frame.push(tuple(elts))

    def BUILD_LIST(frame, count):
        elts = frame.popn(count)
        frame.push(elts)

    def BUILD_SET(frame, count):
        elts = frame.popn(count)
        frame.push(set(elts))

    def BUILD_MAP(frame, size):
        frame.push({})

    def LOAD_ATTR(frame, attr):
        obj = frame.pop()
        val = getattr(obj, attr)
        frame.push(val)

    def COMPARE_OP(frame, opnum):
        x, y = frame.popn(2)
        frame.push(COMPARE_OPERATORS[opnum](x, y))

    def IMPORT_NAME(frame, name):
        level, fromlist = frame.popn(2)
        val = __import__(name, frame.f_globals, frame.f_locals, fromlist, level)

        # XXX: In order to make the decorator `asyncio.coroutine` works normally
        # in our virtual machine, replace it with our implementation.
        if name == 'asyncio':
            from .pyobj import coroutine
            val.coroutine = coroutine
            val.coroutines.coroutine = coroutine

        frame.push(val)

    def IMPORT_FROM(frame, name):
        frame.push(getattr(frame.top(), name))

    def JUMP_FORWARD(frame, jump):
        frame.jump(jump)

    def JUMP_IF_FALSE_OR_POP(frame, jump):
        if not frame.top():
            frame.jump(jump)
        else:
            frame.pop()

    def JUMP_IF_TRUE_OR_POP(frame, jump):
        if frame.top():
            frame.jump(jump)
        else:
            frame.pop()

    def JUMP_ABSOLUTE(frame, jump):
        frame.jump(jump)

    def POP_JUMP_IF_FALSE(frame, jump):
        val = frame.pop()
        if not val:
            frame.jump(jump)

    def POP_JUMP_IF_TRUE(frame, jump): # XXX: not emitted by the compiler
        val = frame.pop()
        if val:
            frame.jump(jump)

    def LOAD_GLOBAL(frame, name):
        if name in frame.f_globals:  val = frame.f_globals[name]
        elif name in frame.f_builtins: val = frame.f_builtins[name]
        else: raise NameError("name '%s' is not defined" % name)
        frame.push(val)

    def CONTINUE_LOOP(frame, dest):
        GlobalCache().set('return_value', dest)
        return 'continue'

    def SETUP_LOOP(frame, dest):
        frame.push_block('loop', dest)

    def SETUP_EXCEPT(frame, dest):
        frame.push_block('setup-except', dest)

    def SETUP_FINALLY(frame, dest):
        frame.push_block('finally', dest)

    def LOAD_FAST(frame, name):
        # https://github.com/python/cpython/blob/fee552669f21ca294f57fe0df826945edc779090/Python/ceval.c#L1335
        if name not in frame.f_locals:
            raise UnboundLocalError(
                "local variable '%s' referenced before assignment" % name)
        frame.push(frame.f_locals[name])

    def STORE_FAST(frame, name):
        frame.f_locals[name] = frame.pop()

    def DELETE_FAST(frame, name):
        del frame.f_locals[name]

    def RAISE_VARARGS(frame, argc):
        assert 2 >= argc >= 0
        # https://github.com/python/cpython/blob/3.4/Python/ceval.c#L1876
        ret = [None]*2
        ret[:argc] = frame.popn(argc)
        return do_raise(frame, *ret)

    def CALL_FUNCTION(frame, arg):
        return call_function(frame, arg, [], {})

    def MAKE_FUNCTION(frame, argc):
        code, name = frame.popn(2)
        func = Function(code, frame.f_globals, name, None, None)
        func = _setup_function(frame, argc, func)
        frame.push(func)

    def BUILD_SLICE(frame, count):
        if count != 2 or count != 3:
            raise VirtualMachineError('Strange BUILD_SLICE count: %r' % count)
        frame.push(slice(*frame.stack.popn(count)))

    def MAKE_CLOSURE(frame, argc):
        closure, code, name = frame.popn(3)
        func = Function(code, frame.f_globals, name, None, closure)
        func = _setup_function(frame, argc, func)
        frame.push(func)

    def LOAD_CLOSURE(frame, name):
        frame.push(frame.cells[name])

    def LOAD_DEREF(frame, name):
        frame.push(frame.cells[name].contents)

    def STORE_DEREF(frame, name):
        frame.cells[name].contents = frame.pop()

    def DELETE_DEREF(frame, name):
        del frame.cells[name].contents

    def CALL_FUNCTION_VAR(frame, arg):
        args = frame.pop()
        return call_function(frame, arg, args, {})

    def CALL_FUNCTION_KW(frame, arg):
        kwargs = frame.pop()
        return call_function(frame, arg, [], kwargs)

    def CALL_FUNCTION_VAR_KW(frame, arg):
        # https://docs.python.org/3.5/library/dis.html#opcode-CALL_FUNCTION_VAR_KW
        args, kwargs = frame.popn(2)
        return call_function(frame, arg, args, kwargs)

    def SETUP_WITH(frame, dest):
        ctxmgr = frame.pop()
        frame.push(ctxmgr.__exit__)
        ctxmgr_obj = ctxmgr.__enter__()
        # NOTE: the finally block should be setup before pushing the result.
        frame.push_block('finally', dest)
        frame.push(ctxmgr_obj)

    def LIST_APPEND(frame, count):
        """Append value to the list (at `frame.stack[-count]`)"""
        val = frame.pop()
        frame.stack[-count].append(val)

    def SET_ADD(frame, count):
        val = frame.pop()
        frame[-count].add(val)

    def MAP_ADD(frame, count):
        val, key = frame.popn(2)
        frame[-count][key] = val

    def LOAD_CLASSDEREF(frame, name):   # new in py34
        frame.push(frame.cells[name].contents)

    def EXTENDED_ARG(frame, count):
        GlobalCache().set('oparg', count << 16)
        return 'extended_arg'


class OperationPy34(Operation):
    ...


class OperationPy35(OperationPy34):
    _unsupported_ops = ['WITH_CLEANUP', 'STORE_MAP']

    def GET_AITER(frame):
        obj = frame.pop()
        _iter = None
        if hasattr(obj, '__aiter__'):
            _iter = obj.__aiter__()
            if _iter is None:
                frame.push(None)
                # TODO: chech whether this is a correct exception to be returned
                raise ValueError('No asynchronous iterator availale')
        else:
            frame.push(None)
            raise TypeError("'async for' requires an object with __aiter__ "
                "method, got %s" % obj.__class__.__name__)

        # NOTE: __aiter__ should return asynchronous iterators since CPython 3.5.2
        # see also bpo-27243
        # TODO: Drop support for asynchronous __aiter__ in Py37 (bpo-31709)
        if hasattr(_iter, '__anext__'):
            wrapper = CoroWrapper(obj).__aiter__()
            frame.push(wrapper)
            return

        awaitable = _coro_get_awaitable_iter(_iter)
        if awaitable is None:
            frame.push(None)
            raise TypeError("'async for' received an invalid object from "
                "__aiter__: %s" % _iter.__class__.__name__)
        else:
            # TODO: We didn't consider that when this warning should be converted
            # to an error.
            import warnings
            warnings.warn((
                '%s implements legacy __aiter__ protocol; __aiter__ should '
                'return an asynchronous iterator, not awaitable'
                ), PendingDeprecationWarning)
            frame.push(awaitable)

    def GET_ANEXT(frame):
        aiter = frame.top()
        if hasattr(aiter, '__anext__'):
            next_iter = aiter.__anext__()
            if next_iter is None:
                raise ValueError('Not a valid asynchronous iterator')
        else:
            raise TypeError("'async for' requires an iterator with __anext__ "
                "method, got %s" % aiter.__class__.__name__)

        awaitable = _coro_get_awaitable_iter(next_iter)
        if awaitable is None:
            raise TypeError("'async for' received an invalid object from "
                "__anext__: %s" % next_iter.__class__.__name__)

        frame.push(awaitable)

    def BEFORE_ASYNC_WITH(frame):
        ctxmgr = frame.pop()
        frame.push(ctxmgr.__aexit__)
        ctxmgr_obj = ctxmgr.__aenter__()
        frame.push(ctxmgr_obj)

    def GET_YIELD_FROM_ITER(frame):
        # NOTE: using `iter()` with catching `TypeError` is more reliable
        # see also: https://stackoverflow.com/a/1952481
        try:
            iterable = iter(frame.top())
        except TypeError:
            raise
        frame.push(iter(frame.pop()))

    def GET_AWAITABLE(frame):
        val = frame.pop()
        _iter = _coro_get_awaitable_iter(val)

        if isinstance(_iter, CoroWrapper):
            yf = _gen_yf(_iter)
            if yf is not None:
                raise RuntimeError('coroutine is being awaited already')
        frame.push(_iter)

    # NOTE: implementation of `WITH_CLEANUP` is separated into
    # `WITH_CLEANUP_START`, `WITH_CLEANUP_FINISH` since Py35
    def WITH_CLEANUP_START(frame):
        v = w = None
        u = frame.top()
        if u is None:
            exit_func = frame.pop(1)
        elif isinstance(u, str):
            if u in ('return', 'continue'):
                exit_func = frame.pop(2)
            else:
                exit_func = frame.pop(1)
            u = None
        elif issubclass(u, BaseException):
            w, v, u = frame.popn(3)
            tp, exc, tb = frame.popn(3)
            exit_func = frame.pop()
            frame.push(tp, exc, tb)
            frame.push(None)
            frame.push(w, v, u)
            block = frame.pop_block()
            assert block.type == 'except-handler'
            frame.push_block(block.type, block.handler, block.level-1)
        else:
            raise VirtualMachineError("Confused WITH_CLEANUP")

        exit_ret = exit_func(u, v, w)
        frame.push(*(u, exit_ret))

    def WITH_CLEANUP_FINISH(frame):
        u, exit_ret = frame.popn(2)
        err = (u is not None) and bool(exit_ret)
        if err:
            frame.push('silenced')

    def BUILD_MAP(frame, size):
        # changed in version 3.5
        items = [frame.popn(2) for i in range(size)]
        frame.push(dict(items))

    def CALL_FUNCTION_VAR(frame, arg):
        # NOTE: this operation is changed in py35, and will be removed in py36,
        # but it does not affect our implementation
        args = frame.pop()
        return call_function(frame, arg, args, {})

    def CALL_FUNCTION_KW(frame, arg):
        kwargs = frame.pop()
        return call_function(frame, arg, [], kwargs)

    def CALL_FUNCTION_VAR_KW(frame, arg):
        # NOTE: this operation is changed in py35, and will be removed in py36,
        # but it does not affect our implementation
        args, kwargs = frame.popn(2)
        return call_function(frame, arg, args, kwargs)

    def BUILD_LIST_UNPACK(frame, count):
        # NOTE: for case like ```a = [1, 2, 3]; b = [*a]```,
        # which is not allowed in Py34.
        elts = frame.popn(count)
        frame.push(*elts)

    def BUILD_MAP_UNPACK(frame, count):
        # NOTE: for case like ```a = {'a': 1, 'b': 2}; b = {**a}```,
        # which is not allowed in Py34.
        elts = frame.popn(count)
        frame.push(*elts)

    def BUILD_MAP_UNPACK_WITH_CALL(frame, oparg):
        num_map, func_location = oparg & 0xff, (oparg >> 8) & 0xff
        func = frame.peek(num_map + func_location - 1)
        elts = frame.popn(num_map)
        _map = {}
        for elt in elts:
            if not isinstance(elt, dict):
                raise TypeError('%s() argument after ** must be a mapping, not %s'
                    % (func.__name__, type(elt).__name__))
            _map.update(elt)
        frame.push(_map)

    def BUILD_TUPLE_UNPACK(frame, count):
        # NOTE: for case like ```a = (1, 2, 3); b = (*a,)```,
        # which is not allowed in Py34.
        elts = frame.popn(count)
        frame.push(*elts)

    def BUILD_SET_UNPACK(frame, count):
        # NOTE: for case like ```a = {1, 2, 3}; b = {*a}```,
        # which is not allowed in Py34.
        elts = frame.popn(count)
        frame.push(*elts)

    def SETUP_ASYNC_WITH(frame, dest):
        res = frame.pop()   # this affect the offset of block to be pushed
        frame.push_block('finally', dest)
        frame.push(res)

    def UNPACK_EX(frame, oparg):
        # NOTE: message of ValueError is modified
        # https://github.com/python/cpython/blob/3.5/Python/ceval.c#L4288-L4296
        argcnt, argcntafter = (oparg & 0xFF), (oparg >> 8)
        totalargs = 1 + argcnt + argcntafter
        seq = list(frame.pop())

        if argcnt + argcntafter > len(seq):
            raise ValueError('not enough values to unpack '
                '(expected at least %d, got %d)' % (argcnt + argcntafter, len(seq)))

        before = seq[:argcnt]
        vals = seq[argcnt:(-argcntafter if argcntafter else None)]
        after = seq[(-argcntafter if argcntafter else len(seq)):]

        frame.push(*after[::-1])
        frame.push(vals)
        frame.push(*before[::-1])


class OperationPy36(OperationPy35):
    _unsupported_ops = [
        'CALL_FUNCTION_VAR', 'CALL_FUNCTION_VAR_KW', 'MAKE_CLOSURE',
    ]

    def SETUP_ANNOTATIONS(frame):
        raise NotImplementedError

    def STORE_ANNOTATION(frame, namei):
        raise NotImplementedError

    def MAKE_FUNCTION(frame, oparg):
        # NOTE: Operation `MAKE_CLOSURE` is removed since Py36, and the
        # implementation of it is merged into this operation.
        code, name = frame.popn(2)
        func = Function(code, frame.f_globals, name, (), None)
        if oparg & 0x08: func.__closure__ = frame.pop()
        if oparg & 0x04: func.__annotations__ = frame.pop()
        if oparg & 0x02: func.__kwdefaults__ = frame.pop()
        if oparg & 0x01: func.__defaults__ = frame.pop()
        frame.push(func)

    def CALL_FUNCTION_EX(frame, arg):
        varargs, kwargs = frame.popn(2)
        return call_function(frame, arg, varargs, kwargs)

    def FORMAT_VALUE(frame, flags):
        raise NotImplementedError

    def BUILD_CONST_KEY_MAP(frame, count):
        raise NotImplementedError

    def BUILD_STRING(frame, count):
        raise NotImplementedError

    def BUILD_TUPLE_UNPACK_WITH_CALL(frame, count):
        raise NotImplementedError


class OperationPy37(OperationPy36):
    _unsupported_ops = ['STORE_ANNOTATION']

    def LOAD_METHOD(frame, namei):
        raise NotImplementedError

    def CALL_METHOD(frame, argc):
        raise NotImplementedError


def do_raise(frame, exc, cause):
    if exc is None:
        exc_type, val, tb = GlobalCache().get('last_exception')
        return 'exception' if exc_type is None else 'reraise'
    elif type(exc) == type:
        exc_type = exc
        val = exc()
    elif isinstance(exc, BaseException):
        exc_type = type(exc)
        val = exc
    else:
        return 'exception'

    if cause:
        if type(cause) == type:
            cause = cause()
        elif not isinstance(cause, BaseException):
            return 'exception'
        val.__cause__ = cause

    GlobalCache().set('last_exception', (exc_type, val, val.__traceback__))
    return 'exception'


def _setup_function(frame, argc, func):
    """A helper function to setup __annotations__, __defaults__,
    __kwdefaults__ of `Function` object for CPython < 3.5 only.

    (Because implementation of `MAKE_FUNCTION` is changed since CPython 3.6)
    """
    num_posdefs = argc & 0xff
    num_kwdefs = (argc>>8) & 0xff
    num_annos = (argc>>16) & 0x7fff

    annos = {}
    if num_annos > 0:
        anno_names = frame.pop()
        anno_vals = frame.popn(len(anno_names))
        annos = dict(zip(anno_names, anno_vals))
    func.__annotations__ = annos

    kwdefs = {}
    if num_kwdefs > 0:
        elts = frame.popn(num_kwdefs*2)
        keys = elts[::2]
        vals = elts[1::2]
        kwdefs = dict(zip(keys, vals))
    func.__kwdefaults__ = kwdefs

    posdefs = ()
    if num_posdefs > 0:
        func.__defaults__ = tuple(frame.popn(num_posdefs))
    return func


def call_function(frame, oparg, varargs, kwargs):
    len_kw, len_pos = divmod(oparg, 256)
    namedargs = dict([frame.popn(2) for i in range(len_kw)])
    namedargs.update(kwargs)
    posargs = frame.popn(len_pos)
    posargs.extend(varargs)
    func = frame.pop()

    # XXX: This is a temporary workaround to skip checking on some builtin
    # functions which may lack `__name__`, e.g. `functools.partial`.
    if hasattr(func, '__name__'):
        # XXX: Calling `locals()` and `globals()` in the script to be executed
        # by virtual machine will return the actual information of the frame
        # executed by host runtime. To simulate the execution in the virtual
        # machine, we have to return the information of the frame we got here.
        if func.__name__ == 'locals':
            frame.push(frame.f_locals)
            return
        elif func.__name__ == 'globals':
            frame.push(frame.f_globals)
            return
    frame.push(func(*posargs, **namedargs))


def build_class(func, name, *bases, **kwds):
    # Modified implementation of darius/tailbiter.
    if not isinstance(func, Function):
        raise TypeError('func must be a function')
    if not isinstance(name, str):
        raise TypeError('name is not a string')
    metaclass = kwds.pop('metaclass', None)
    if metaclass is None:
        metaclass = type(bases[0]) if bases else type
    if isinstance(metaclass, type):
        metaclass = calculate_metaclass(metaclass, bases)

    void = object()
    prepare = getattr(metaclass, '__prepare__', void)
    namespace = {} if prepare is void else prepare(name, bases, **kwds)

    vm = get_vm()
    frame = Frame(func.__code__, func.__globals__, namespace, func.__closure__, vm.frame)
    cell = vm.run(frame)

    cls = metaclass(name, bases, namespace)
    if isinstance(cell, Cell):
        cell.contents = cls
    return cls


def calculate_metaclass(metaclass, bases):
    winner = metaclass
    for base in bases:
        t = type(base)
        if issubclass(t, winner):
            winner = t
        elif not issubclass(winner, t):
            raise TypeError('metaclass conflict', winner, t)
    return winner
