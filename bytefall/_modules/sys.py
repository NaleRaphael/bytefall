""" Incomplete Python implemented "sysmodule.c".

Here we just implement functions related to the workflow of our vm.
"""
from ..vm import settrace as vm_settrace
from .._utils import get_vm


__all__ = ['settrace', '_getframe']


def _trace_trampoline(cb, frame, what, arg):
    callback = cb if what == 'call' else frame.f_trace
    if callback is None:
        return 0
    result = callback(frame, what, arg)
    if result is None:
        vm_settrace(None, None)
        del frame.f_trace
        return -1
    return 0


def settrace(callback):
    if callback is None:
        # Uninstall callback
        vm_settrace(None, None)
    else:
        vm_settrace(_trace_trampoline, callback)


def _getframe(level=0):
    frame = get_vm().frame
    while level > 0:
        frame = frame.f_back
        level -= 1
    return frame
