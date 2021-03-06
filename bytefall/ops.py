"""
Bytecode operations.
"""

from __future__ import print_function, division
import dis, operator
from inspect import isclass as inspect_isclass

from .objects import CellType, make_cell, Frame, Function
from .objects.generatorobject import (
    Generator, Coroutine, AsyncGenerator, AIterWrapper, AsyncGenWrappedValue,
    _gen_yf, _coro_get_awaitable_iter, coroutine
)

from ._internal.exceptions import VirtualMachineError
from ._internal.cache import GlobalCache
from ._internal.utils import get_vm

# TODO: merge these two modules
from ._compat import BuiltinsWrapper, PdbWrapper


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

    Note that `BaseException` should be considered.

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

# Unit of bytecode is changed into 2 bytes since Py36
from sys import version_info
CODE_UNIT = 1 if version_info < (3, 6) else 2


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
            if isinstance(x, (Generator, Coroutine)):
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
            frame.jump(frame.f_lasti - CODE_UNIT)
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
                frame.unwind_except_handler(block)
                why = None
        elif v is None:
            why = None
        elif issubclass(v, BaseException):
            exctype = v
            val = frame.pop()
            tb = frame.pop()
            # PyErr_Restore
            GlobalCache().set('last_exception', (exctype, val, tb))
            why = 'exception'
        else:
            raise VirtualMachineError("Confused END_FINALLY")
        return why

    def POP_EXCEPT(frame):
        block = frame.pop_block()
        if block.type != 'except-handler':
            raise SystemError('popped block is not an except handler')
        frame.unwind_except_handler(block)

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
        frame.push(frame.cells[name].cell_contents)

    def STORE_DEREF(frame, name):
        frame.cells[name] = make_cell(frame.pop())

    def DELETE_DEREF(frame, name):
        del frame.cells[name].cell_contents

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
        frame.stack[-count].add(val)

    def MAP_ADD(frame, count):
        val, key = frame.popn(2)
        frame.stack[-count][key] = val

    def LOAD_CLASSDEREF(frame, name):   # new in py34
        frame.push(frame.cells[name].cell_contents)

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
        if hasattr(_iter, '__anext__'):
            wrapper = AIterWrapper(_iter)
            return frame.push(wrapper)

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
        if isinstance(aiter, AsyncGenerator):
            awaitable = aiter.__anext__()
            if awaitable is None:
                raise ValueError('Not a valid asynchronous iterator')
            return frame.push(awaitable)

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

        if isinstance(_iter, Coroutine):
            yf = _gen_yf(_iter.gen)
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
        # changed in Py35
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


# Mask and values used by FORMAT_VALUE conversion
# https://github.com/python/cpython/blob/3.6/Include/ceval.h#L226-L233
FVC_MAP = {
    0: None,  # FVC_NONE
    1: str,  # FVC_STR
    2: repr,  # FVC_REPR
    3: ascii,  # FVC_ASCII
}
FVC_MASK = 0x3
FVS_HAVE_SPEC = 0x4

class OperationPy36(OperationPy35):
    _unsupported_ops = [
        'CALL_FUNCTION_VAR', 'CALL_FUNCTION_VAR_KW', 'MAKE_CLOSURE',
    ]

    def YIELD_VALUE(frame):
        retval = frame.pop()
        if frame.f_code.co_flags & 0x0200:    # CO_ASYNC_GENERATOR = 0x0200
            retval = AsyncGenWrappedValue(retval)
        GlobalCache().set('return_value', retval)
        return 'yield'

    def SETUP_ANNOTATIONS(frame):
        if frame.f_locals is None:
            raise SystemError('no locals found when setting up annotations')
        if '__annotations__' not in frame.f_locals:
            frame.f_locals['__annotations__'] = {}

    def STORE_ANNOTATION(frame, namei):
        if frame.f_locals is None:
            raise SystemError('no locals found when setting up annotations')

        anno_dict = frame.f_locals.get('__annotations__', None)
        if anno_dict is None:
            raise NameError('__annotations__ not found')
        anno_dict[namei] = frame.pop()

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

    def CALL_FUNCTION_KW(frame, oparg):
        kwnames = frame.pop()
        return call_function_kw(frame, oparg, kwnames)

    def CALL_FUNCTION_EX(frame, oparg):
        kwargs = frame.pop() if oparg & 0x01 else {}
        posargs = frame.pop()
        func = frame.pop()
        retval = func(*posargs, **kwargs)
        frame.push(retval)

    def FORMAT_VALUE(frame, flags):
        # FVC_MASK: 0x3, for chosing conversion function
        # FVS_MASK: 0x4, check whether string should be formatted, e.g. f'{x:.4f}'
        which_conversion = flags & 0x3
        have_fmt_spec = (flags & 0x4) == FVS_HAVE_SPEC
        fmt_spec = frame.pop() if have_fmt_spec else None
        value = frame.pop()
        conv_fn = FVC_MAP.get(which_conversion, None)

        if conv_fn:
            result = conv_fn(value)
            value = result
        if fmt_spec is None:
            result = value
        else:
            result = format(value, fmt_spec)
        frame.push(result)

    def BUILD_CONST_KEY_MAP(frame, count):
        keys = frame.pop()
        if len(keys) != count:
            raise SystemError('bad BUILD_CONST_KEY_MAP keys argument')
        vals = frame.popn(count)
        key_map = dict(zip(keys, vals))
        frame.push(key_map)

    def BUILD_STRING(frame, count):
        frame.push(''.join(frame.popn(count)))

    def BUILD_TUPLE_UNPACK_WITH_CALL(frame, count):
        vals = []
        for v in frame.popn(count):
            vals.extend(v)
        frame.push(tuple(vals))

    def BUILD_MAP_UNPACK_WITH_CALL(frame, oparg):
        num_map = oparg
        func = frame.peek(1 + oparg)    # XXX: in CPython: PEEK(2 + oparg)
        elts = frame.popn(oparg)
        _map = {}
        for elt in elts:
            if not isinstance(elt, dict):
                raise TypeError('%s() argument after ** must be a mapping, not %s'
                    % (func.__name__, type(elt).__name__))
            _map.update(elt)
        frame.push(_map)

    def EXTENDED_ARG(frame, count):
        GlobalCache().set('oparg', count << 8)
        return 'extended_arg'


class OperationPy37(OperationPy36):
    _unsupported_ops = ['STORE_ANNOTATION']
    # Check out bpo-32550 for details of removal of 'STORE_ANNOTATION'.

    def GET_AITER(frame):
        # NOTE: Support for asynchronous __aiter__ is dropped in Py37. (bpo-31709)
        # We should return an `<asynchronous iterator>` directly instead of an
        # awaitable that could resolve to an `<asynchronous iterator>`.
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

        if not hasattr(_iter, '__anext__'):
            frame.push(None)
            raise TypeError("'async for' received an object from __aiter__ "
                "that does not implement __anext__: %s" % _iter.__class__.__name__)

        frame.push(_iter)

    def LOAD_METHOD(frame, name):
        obj = frame.pop()
        meth = getattr(obj, name, None)
        if meth is None:
            raise AttributeError("type object '%s' has no attribute '%s'"
                % (obj.__name__, name))

        # XXX: Instead of implementing something like `_PyObject_GetMethod()`,
        # we can determine whether a method has a bounding object or not by
        # checking the attribute `__self__`. See also:
        # - https://github.com/python/cpython/blob/3.7/Python/ceval.c#L3040
        # - https://github.com/python/cpython/blob/3.7/Objects/object.c#L1126-L1197
        if hasattr(meth.__call__, '__self__'):
            # `meth` is not an unbound method
            frame.push(*(None, meth))
        else:
            frame.push(*(meth, obj))

    def CALL_METHOD(frame, oparg):
        meth = frame.peek(oparg + 1)
        if meth is None:
            call_function_kw(frame, oparg, [])
            frame.pop(1)    # pop out NULL
        else:
            call_function_kw(frame, oparg+1, [])


class OperationPy38(OperationPy37):
    _unsupported_ops = [
        'BREAK_LOOP', 'CONTINUE_LOOP', 'SETUP_LOOP', 'SETUP_EXCEPT'
    ]

    def WITH_CLEANUP_FINISH(frame):
        # Changed in Py38, and `WHY_SILENCED` is removed.
        u, exit_ret = frame.popn(2)
        err = (u is not None) and bool(exit_ret)
        if err < 0:
            return 'exception'
        elif err > 0:
            block = frame.pop_block()
            assert block.type == 'except-handler'
            frame.unwind_except_handler(block)
            frame.push(None)

    def POP_EXCEPT(frame):
        block = frame.pop_block()
        if block.type != 'except-handler':
            raise SystemError('popped block is not an except handler')
        num_stack = len(frame.stack)
        assert block.level + 3 <= num_stack <= block.level + 4
        tb, value, exctype = frame.popn(3)
        GlobalCache().set('new_exception', (exctype, value, tb))

    def MAP_ADD(frame, count):
        # Changed in Py38. Order of key and val is reversed.
        key, val = frame.popn(2)
        frame.stack[-count][key] = val

    def ROT_FOUR(frame):
        # related test case: test_with::test_generator_with_context_manager
        a, b, c, d = frame.popn(4)
        frame.push(b, c, d, a)

    def BEGIN_FINALLY(frame):
        frame.push(None)

    def END_FINALLY(frame):
        exc = frame.pop()
        if exc is None:
            return
        elif isinstance(exc, int):
            # `exc` should be a line number to jump to
            last_exception = GlobalCache().get('last_exception', None)
            if exc == 0 and last_exception is not None:
                return 'exception'
            frame.jump(exc)
        else:
            assert issubclass(exc, BaseException)
            tb, val = frame.popn(2)
            # PyErr_Restore
            GlobalCache().set('last_exception', (exc, val, tb))
            return 'exception'

    def END_ASYNC_FOR(frame):
        exc = frame.pop()
        assert issubclass(exc, BaseException)
        if exception_match(exc, StopAsyncIteration):
            block = frame.pop_block()
            assert block.type == 'except-handler'
            frame.unwind_except_handler(block)
            frame.pop()
            # XXX: no oparg here, but there is an expression
            # `JUMPBY(opargs)` in CPython...
            return
        else:
            tb, val = frame.popn(2)
            GlobalCache().set('last_exception', (exc, val, tb))
            return 'exception'

    def CALL_FINALLY(frame, oparg):
        # value to be pushed: INSTR_OFFSET()
        frame.push(frame.f_lasti)
        # jump to 'finally' block
        frame.jump(oparg)

    def POP_FINALLY(frame, preserve_tos):
        res = frame.pop() if preserve_tos else None
        exc = frame.pop()
        if exc:
            frame.popn(2)
            block = frame.pop_block()
            if block.type != 'except-handler':
                raise SystemError('popped block is not an except handler')
            assert len(frame.stack) == block.level + 3
            tb, value, exctype = frame.popn(3)
            GlobalCache().set('new_exception', (exctype, value, tb))
        if preserve_tos:
            frame.push(res)


def do_raise(frame, exc, cause):
    if exc is None:
        exc_type, val, tb = GlobalCache().get('new_exception', (type(None), None, None))
        # PyErr_Restore
        GlobalCache().set('last_exception', (exc_type, val, tb))
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

    # PyErr_SetObject (PyErr_Restore)
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

    frame.push(_call_function(func, frame, *posargs, **namedargs))


def call_function_kw(frame, oparg, kwnames):
    """Call function with names of keyword arguments.
    This is a new implementation of `call_function` since **Py36**.

    See also:
    https://github.com/python/cpython/blob/3.6/Python/ceval.c#L4832-L4894
    """
    nkwargs = len(kwnames)
    nargs = oparg - nkwargs
    kwvals = frame.popn(nkwargs)
    namedargs = dict(zip(kwnames, kwvals))
    posargs = frame.popn(nargs)
    func = frame.pop()

    frame.push(_call_function(func, frame, *posargs, **namedargs))


def _call_function(func, frame, *posargs, **namedargs):
    # XXX: This is a temporary workaround to skip checking on some builtin
    # functions which may lack `__name__`, e.g. `functools.partial`.
    fn = getattr(func, '__name__', '')

    if hasattr(BuiltinsWrapper, fn):
        func = getattr(BuiltinsWrapper, fn)
        retval = func(frame, *posargs, **namedargs)
    elif hasattr(PdbWrapper, fn):
        func = getattr(PdbWrapper, fn)
        retval = func(frame, *posargs, **namedargs)
    else:
        retval = func(*posargs, **namedargs)
    return retval


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
    if isinstance(cell, CellType):
        cell.cell_contents = cls
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
