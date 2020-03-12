"""
A pure-Python Python bytecode interpreter.

Derived from the implementation of `byterun` by Ned Batchelder and
Darius Bacon.

ref: https://github.com/nedbat/byterun
ref: https://github.com/darius/tailbiter
"""

import dis, builtins, sys
import six

from ._base import Singleton
from ._utils import get_operations, check_line_number
from .cache import GlobalCache
from .pyframe import Frame
from .exceptions import VirtualMachineError


# build a map for opcodes that defined in `dis.hasconst`, `dis.hasfree`, ...
SPECIAL_COLLECTION = {v: getattr(dis, v) for v in dir(dis) if v[:3] == 'has'}
SPECIAL_OPCODE = {}
for name, values in SPECIAL_COLLECTION.items():
    SPECIAL_OPCODE.update({v: name for v in values})

COLLECTION_PROCESS = {
    'hasconst': lambda f, code, int_arg: code.co_consts[int_arg],
    'hasfree': lambda f, code, int_arg: (code.co_cellvars[int_arg]
        if int_arg < len(code.co_cellvars) else
        code.co_freevars[int_arg - len(code.co_cellvars)]),
    'hasname': lambda f, code, int_arg: code.co_names[int_arg],
    'haslocal': lambda f, code, int_arg: code.co_varnames[int_arg],
    'hasjrel': lambda f, code, int_arg: f.f_lasti + int_arg,
}


class VirtualMachine(metaclass=Singleton):
    def __init__(self, debug=False):
        self.frames = []
        self.frame = None
        self.cls_op = get_operations()  # local lazy-import to avoid circular reference
        self._debug = debug     # for development

    def run_code(self, code, f_globals=None, f_locals=None):
        if f_globals is None: f_globals = builtins.globals()
        if f_locals is None:  f_locals = f_globals
        if '__builtins__' not in f_globals:
            f_globals['__builtins__'] = builtins.__dict__
        frame = Frame(code, f_globals, f_locals, None, None)
        return self.run(frame)

    def run(self, frame, exc=None):
        self.push_frame(frame)
        why = None
        _call_trace_protected(self.frame, 'call', None)

        while True:
            if exc is not None:
                why = 'exception'
                exc = None
            elif why is None:
                byte_name, arguments = self.parse_byte_and_args()
                why = self.dispatch(byte_name, arguments)

            if why == 'extended_arg':
                # NOTE: index of argument is too big to be represented in 2 byte, so
                # it is extended by operation `EXTENDED_ARG`
                arg_offset = GlobalCache().pop('oparg')
                byte_name, arguments = self.parse_byte_and_args(arg_offset=arg_offset)
                why = self.dispatch(byte_name, arguments)
                continue
            if why == 'exception':
                _call_exc_trace(self.frame)
            if why == 'reraise':
                why = 'exception'
            if why != 'yield':
                while why and frame.block_stack:
                    why = frame.manage_block_stack(why)
            if why:
                break

        func = GlobalCache().get('tracefunc', None)
        obj = GlobalCache().get('traceobj', None)
        retval = GlobalCache().get('return_value', None)

        if why in ['return', 'yield']:
            if _call_trace(func, obj, self.frame, 'return', retval):
                why = 'exception'
        elif why == 'exception':
            _call_trace_protected(self.frame, 'return', None)

        self.pop_frame()
        if why == 'exception':
            six.reraise(*GlobalCache().get('last_exception'))

        return retval

    def push_frame(self, frame):
        self.frames.append(frame)
        self.frame = frame

    def pop_frame(self):
        self.frames.pop()
        self.frame = self.frames[-1] if self.frames else None

    def resume_frame(self, frame, exc=None):
        frame.f_back = self.frame
        val = self.run(frame, exc=exc)
        frame.f_back = None
        return val

    def parse_byte_and_args(self, **kwargs):
        raise NotImplementedError

    def dispatch(self, byte_name, arguments):
        """ Dispatch opcode.

        Equivalent to the block defined as `dispatch_opcode` in "ceval.c".
        """
        why = None

        # In CPython, `maybe_call_line_trace` is called in the block defined by
        # `fast_next_opcode` label, which is a former block of `dispatch_opcode`.
        _maybe_call_line_trace(self.frame)

        try:
            prefix, *rem = byte_name.split('_')
            if prefix in ['UNARY', 'BINARY', 'INPLACE']:
                op = byte_name[len(prefix)+1:]
                attr_name = '%s_operator' % prefix.lower()
                getattr(self.cls_op, attr_name)(self.frame, op)
            else:
                why = getattr(self.cls_op, byte_name)(self.frame, *arguments)
        except:
            # raise exception directly for debugging code while developing
            if self._debug: raise
            last_exception = sys.exc_info()[:2] + (None,)
            GlobalCache().set('last_exception', last_exception)
            why = 'exception'
        return why


class VirtualMachinePy34(VirtualMachine):
    def parse_byte_and_args(self, arg_offset=0):
        f = self.frame
        code = f.f_code
        opcode = code.co_code[f.f_lasti]
        f.f_lasti += 1
        if opcode >= dis.HAVE_ARGUMENT:
            int_arg = (code.co_code[f.f_lasti] + (code.co_code[f.f_lasti+1] << 8)) | arg_offset
            f.f_lasti += 2
            collection_type = SPECIAL_OPCODE.get(opcode, None)
            if collection_type and collection_type in COLLECTION_PROCESS:
                arg = COLLECTION_PROCESS[collection_type](f, code, int_arg)
            else:
                arg = int_arg
            return dis.opname[opcode], (arg,)
        return dis.opname[opcode], ()


class VirtualMachinePy35(VirtualMachinePy34):
    ...


class VirtualMachinePy36(VirtualMachine):
    def run_code(self, code, f_globals=None, f_locals=None):
        if f_globals is None: f_globals = builtins.globals()
        if f_locals is None:  f_locals = f_globals
        if '__builtins__' not in f_globals:
            f_globals['__builtins__'] = builtins.__dict__
        if '__annotations__' not in f_globals:
            f_globals['__annotations__'] = {}
        frame = Frame(code, f_globals, f_locals, None, None)
        return self.run(frame)

    def parse_byte_and_args(self, arg_offset=0):
        f = self.frame
        code = f.f_code
        opcode, int_arg = code.co_code[f.f_lasti:f.f_lasti+2]
        int_arg |= arg_offset
        f.f_lasti += 2

        if opcode >= dis.HAVE_ARGUMENT:
            collection_type = SPECIAL_OPCODE.get(opcode, None)
            if collection_type and collection_type in COLLECTION_PROCESS:
                arg = COLLECTION_PROCESS[collection_type](f, code, int_arg)
            else:
                arg = int_arg
            return dis.opname[opcode], (arg,)

        return dis.opname[opcode], ()


class VirtualMachinePy37(VirtualMachinePy36):
    ...


class VirtualMachinePy38(VirtualMachinePy36):
    ...


def settrace(func, arg):
    """ Setup trace function. (`ceval.c::PyEval_SetTrace`) """
    GlobalCache().set('tracefunc', func)  # _trace_trampoline
    GlobalCache().set('traceobj', arg)    # a Python callback function
    GlobalCache().set('use_tracing', func is not None)


def _call_trace(func, obj, frame, what, arg=None):
    """ Call trace function. (`ceval.c::calltrace`) """
    tracing = GlobalCache().get('tracing', False)
    if tracing or func is None:
        return

    GlobalCache().set('tracing', True)
    GlobalCache().set('use_tracing', False)
    result = func(obj, frame, what, arg)

    # Here we get the trace function directly in case it is uninstalled by
    # `sys.settrace(None)`.
    temp = GlobalCache().get('tracefunc', None)
    GlobalCache().set('use_tracing', temp is not None)
    GlobalCache().set('tracing', False)
    return result


def _call_trace_protected(frame, what, arg=None):
    """ Call trace function with exception handling.
    (`ceval.c::call_trace_protected`)
    """
    use_tracing = GlobalCache().get('use_tracing', False)
    func = GlobalCache().get('tracefunc', None)
    obj = GlobalCache().get('traceobj', None)

    if not use_tracing or func is None:
        return

    try:
        _call_trace(func, obj, frame, what, arg)
    except:
        raise

def _maybe_call_line_trace(frame):
    """ Used to trigger the callback function to trace per line in source
    code or bytecode instruction.
    """
    tracing = GlobalCache().get('tracing', False)
    func = GlobalCache().get('tracefunc', None)
    obj = GlobalCache().get('traceobj', None)

    # Check whether we are tracing now. If true, we should avoid calling
    # trace function again.
    if tracing or func is None:
        return

    # Get lower & upper bound of instructions corresponding to line number
    line, lb, ub = check_line_number(frame.f_code, frame.f_lasti)

    result = 0
    if frame.f_lasti == lb and frame.f_trace_lines:
        result = _call_trace(func, obj, frame, 'line', None)
    if frame.f_trace_opcodes:
        result = _call_trace(func, obj, frame, 'opcode', None)

    # Reload possibly changed frame fields
    frame.jump(frame.f_lasti)

    return result

def _call_exc_trace(frame):
    """ Used to trigger the callback function for tracing while there is
    an error occuring.
    """
    func = GlobalCache().get('tracefunc', None)
    obj = GlobalCache().get('traceobj', None)

    if func is None:
        return

    # PyErr_Fetch
    arg = GlobalCache().pop('last_exception', (type(None), None, None))

    _call_trace(func, obj, frame, 'exception', arg)

    # PyErr_Restore
    GlobalCache().set('last_exception', arg)
