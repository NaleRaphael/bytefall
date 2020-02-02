"""
A pure-Python Python bytecode interpreter.

Derived from the implementation of `byterun` by Ned Batchelder and
Darius Bacon.

ref: https://github.com/nedbat/byterun
ref: https://github.com/darius/tailbiter
"""

from __future__ import print_function, division
import dis, operator

from .pycell import Cell
from .pyframe import Frame
from .pyobj import Function, Generator
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
}
assert all([op.__qualname__ in dir(operator) for op in BINARY_OPERATORS.values()])

INPLACE_OPERATORS = {
    'POWER':    operator.ipow,    'ADD':      operator.iadd,
    'LSHIFT':   operator.ilshift, 'SUBTRACT': operator.isub,
    'RSHIFT':   operator.irshift, 'MULTIPLY': operator.imul,
    'OR':       operator.ior,     'MODULO':   operator.imod,
    'AND':      operator.iand,    'TRUE_DIVIDE': operator.itruediv,
    'XOR':      operator.ixor,    'FLOOR_DIVIDE': operator.ifloordiv,
}
assert all([op.__qualname__ in dir(operator) for op in INPLACE_OPERATORS.values()])

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
    lambda x, y: issubclass(x, Exception) and issubclass(x, y),
]


class StaticMethodClass(type):
    def __new__(cls, name, bases, local, **kwargs):
        cls._remove_unsupported(bases, local.get('_unsupported_ops', None))
        for k, attr in local.items():
            if callable(attr) and not k.startswith('__'):
                local[k] = staticmethod(attr)
        instance = type.__new__(cls, name, bases, local)
        return instance

    def _remove_unsupported(bases, deps):
        if deps is None:
            return
        for base in bases:
            for k in deps:
                delattr(base, k)


class Operation(metaclass=StaticMethodClass):
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
            if not isinstance(x, Generator) or u is None:
                # Call next on iterators.
                retval = next(x)
            else:
                retval = x.send(u)
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
        if frame.generator:
            frame.generator.gi_running = False
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
        *defaults, code, name = frame.popn(2+argc)
        frame.push(Function(code, frame.f_globals, name, defaults, None))

    def BUILD_SLICE(frame, count):
        if count != 2 or count != 3:
            raise VirtualMachineError('Strange BUILD_SLICE count: %r' % count)
        frame.push(slice(*frame.stack.popn(count)))

    def MAKE_CLOSURE(frame, argc):
        *defaults, closure, code, name = frame.popn(3+argc)
        frame.push(Function(code, frame.f_globals, name, defaults, closure))

    def LOAD_CLOSURE(frame, name):
        frame.push(frame.cells[name])

    def LOAD_DEREF(frame, name):
        frame.push(frame.cells[name].contents)

    def STORE_DEREF(frame, name):
        frame.cells[name].contents = frame.pop()

    def DELETE_DEREF(frame, name):
        del frame.cells[name].contents

    def CALL_FUNCTION_VAR(frame, arg): # TODO: changed in py35, removed in py36
        args = frame.pop()
        return call_function(frame, arg, args, {})

    def CALL_FUNCTION_KW(frame, arg):
        kwargs = frame.pop()
        return call_function(frame, arg, [], kwargs)

    def CALL_FUNCTION_VAR_KW(frame, arg): # TODO: changed in py35, removed in py36
        # https://docs.python.org/3.5/library/dis.html#opcode-CALL_FUNCTION_VAR_KW
        args, kwargs = frame.popn(2)
        return call_function(frame, arg, args, kwargs)

    def SETUP_WITH(frame, dest):
        ctxmgr = frame.pop()
        frame.push(ctxmgr.__exit__)
        ctxmgr_obj = ctxmgr.__enter__()
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
        GlobalCache().set('oparg', 1 << 16)
        return 'extended_arg'


class OperationPy34(Operation):
    ...


def do_raise(frame, exc, cause): # TODO: rewrite this
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


def call_function(frame, oparg, varargs, kwargs):
    len_kw, len_pos = divmod(oparg, 256)
    namedargs = dict([frame.popn(2) for i in range(len_kw)])
    namedargs.update(kwargs)
    posargs = frame.popn(len_pos)
    posargs.extend(varargs)
    func = frame.pop()
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
