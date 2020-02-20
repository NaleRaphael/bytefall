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
from ._utils import get_operations
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
                # TODO: ceval calls PyTraceBack_Here, not sure what that does.
                pass
            if why == 'reraise':
                why = 'exception'
            if why != 'yield':
                while why and frame.block_stack:
                    why = frame.manage_block_stack(why)
            if why:
                break

        self.pop_frame()
        if why == 'exception':
            six.reraise(*GlobalCache().get('last_exception'))

        return GlobalCache().get('return_value')

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
        why = None
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
