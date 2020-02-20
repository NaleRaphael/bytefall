from ..exceptions import VirtualMachineError
from ..pyframe import Frame

__all__ = ['BuiltinsWrapper']


def check_frame(func):
    def wrapper(frame, *args, **kwargs):
        if not isinstance(frame, Frame):
            raise VirtualMachineError(
                'Given argument `frame`: "%s" is not a instance of %s'
                % (frame, Frame)
            )
        return func(frame, *args, **kwargs)
    return wrapper


class BuiltinsWrapper(object):
    """Wrappers to simulate the execution of built-in functions in virtual
    machine.

    e.g. Calling `locals()` and `globals()` in the script to be executed
    by virtual machine will return the actual information of the frame
    executed by host runtime. To simulate the execution in the virtual
    machine, we have to return the information of the frame we got here.
    """
    @staticmethod
    @check_frame
    def locals(frame, *args, **kwargs):
        return frame.f_locals

    @staticmethod
    @check_frame
    def globals(frame, *args, **kwargs):
        return frame.f_globals

    @staticmethod
    @check_frame
    def exec(frame, *args, **kwargs):
        # In Py34, `exec(*['STATEMENT'], f_globals, f_locals)` leads to an
        # error: "SyntaxError: only named arguments may follow *expression"
        posargs = [None, frame.f_globals, frame.f_locals]
        for i, val in enumerate(args):
            posargs[i] = val
        exec(*posargs)
