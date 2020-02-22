import collections
from .pycell import Cell
from .cache import GlobalCache
from .exceptions import VirtualMachineError


_Namedtuple_Block = collections.namedtuple('Block', 'type, handler, level')

class Block(_Namedtuple_Block):
    __slots__ = ()


class Frame(object):
    def __init__(self, f_code, f_globals, f_locals, f_closure, f_back):
        self.f_code = f_code
        self.f_globals = f_globals
        self.f_locals = f_locals
        self.f_back = f_back
        self.stack = []

        if f_back and f_back.f_globals is f_globals:
            # If we share the globals, we share the builtins.
            self.f_builtins = f_back.f_builtins
        else:
            self.f_builtins = f_globals.get('__builtins__', {'None': None})
            if hasattr(self.f_builtins, '__dict__'):
                self.f_builtins = self.f_builtins.__dict__

        self.f_lineno = f_code.co_firstlineno
        self.f_lasti = 0

        self.cells = {} if f_code.co_cellvars or f_code.co_freevars else None
        for var in f_code.co_cellvars:
            # Make a cell for the variable in our locals, or None.
            self.cells[var] = Cell(self.f_locals.get(var))

        # https://github.com/python/cpython/blob/3.4/Python/ceval.c#L3570-L3574
        if f_code.co_freevars:
            assert len(f_code.co_freevars) == len(f_closure)
            self.cells.update(zip(f_code.co_freevars, f_closure))

        self.block_stack = []
        self.generator = None

    def __repr__(self):
        return ('<Frame at 0x%08x: %r @ %d>'
                % (id(self), self.f_code.co_filename, self.f_lineno))

    def top(self):
        return self.stack[-1]

    def push(self, *vals):
        self.stack.extend(vals)

    def peek(self, i=0):
        return self.stack[-1-i]

    def pop(self, i=0):
        return self.stack.pop(-1-i)

    def popn(self, n):
        """Pop a number of values from the value stack.

        A list of `n` values is returned, the deepest value first.
        """
        if n:
            ret = self.stack[-n:]
            self.stack[-n:] = []
            return ret
        else:
            return []

    def jump(self, jump):
        self.f_lasti = jump

    def push_block(self, type, handler=None, level=None):
        level = len(self.stack) if level is None else level
        self.block_stack.append(Block(type, handler, level))

    def pop_block(self):
        return self.block_stack.pop()

    def unwind_block(self, block):
        while len(self.stack) > block.level:
            self.pop()

    def unwind_except_handler(self, block):
        while len(self.stack) > block.level + 3:
            self.pop()
        tb, value, exctype = self.popn(3)
        # NOTE: 'new_exception' denotes the current exception hold by vm.
        # (like `tstate->exc_type` ... in CPython)
        # 'last_exception' denotes the exception should be raised.
        GlobalCache().set('new_exception', (exctype, value, tb))

    def manage_block_stack(self, why):
        """ Manage a frame's block stack.
        Manipulate the block stack and data stack for looping,
        exception handling, or returning.
        """
        assert why != 'yield'

        block = self.block_stack[-1]
        if block.type == 'loop' and why == 'continue':
            self.jump(GlobalCache().get('return_value'))
            why = None
            return why

        self.pop_block()
        if block.type == 'except-handler':
            self.unwind_except_handler(block)
            return why
        self.unwind_block(block)

        if block.type == 'loop' and why == 'break':
            why = None
            self.jump(block.handler)
            return why

        if (
            why == 'exception' and
            block.type in ['setup-except', 'finally']
        ):
            self.push_block('except-handler')

            # in CPython, we retrieve exception from tstate and push to stack here
            exctype, value, tb = GlobalCache().get('new_exception', (type(None), None, None))
            self.push(tb, value, exctype)

            # PyErr_NormalizeException goes here

            # like `PyErr_Fetch`: get last_exception and clear it from GlobalCache
            exctype, value, tb = GlobalCache().pop('last_exception', (type(None), None, None))
            self.push(tb, value, exctype)

            # in CPython, we update the exception in tstate with fetched one
            GlobalCache().set('new_exception', (exctype, value, tb))
            why = None
            self.jump(block.handler)
            return why

        elif block.type == 'finally':
            if why in ('return', 'continue'):
                self.push(GlobalCache().get('return_value'))
            self.push(why)

            why = None
            self.jump(block.handler)
            return why

        return why
