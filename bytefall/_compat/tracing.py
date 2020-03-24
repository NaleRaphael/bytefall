import sys
from pdb import Pdb, getsourcelines

from .utils import check_frame
from bytefall._modules import sys as py_sys
from bytefall._c_api import convert_to_builtin_frame


__all__ = ['PdbWrapper']


class PdbWrapper(object):
    @staticmethod
    @check_frame
    def set_trace(frame, *args, **kwargs):
        return pdb_wrapper(frame)(*args, **kwargs)


def pdb_wrapper(this_frame):
    _pdb = _Pdb()
    def wrapper(*args, **kwargs):
        # Frame to be stepped in is not retrieved by `sys._getframe()`,
        # so that we don't need to pass its `f_back` into `set_trace()`
        _pdb.set_trace(this_frame)

    return wrapper


class _Pdb(Pdb):
    def do_longlist(self, arg):
        filename = self.curframe.f_code.co_filename
        breaklist = self.get_file_breaks(filename)
        try:
            # Here we need to convert `self.curframe` to builtin frame
            # for `getsourcelines`, in which `inspect.findsource()`
            # requires a builtin frame to work.
            converted = convert_to_builtin_frame(self.curframe)
            lines, lineno = getsourcelines(converted)
        except OSError as err:
            self.error(err)
            return
        self._print_lines(lines, lineno, breaklist, self.curframe)
    do_ll = do_longlist

    def set_continue(self):
        self._set_stopinfo(self.botframe, None, -1)
        if not self.breaks:
            # Here we need to replace the implementation of `sys.settrace()`
            # and `sys._getframe()`.
            py_sys.settrace(None)

            # In the original implementation, here it calls
            # `sys._getframe().f_back` to get the caller of this method.
            # However, we cannot get caller `pyframe.Frame` that calling
            # `py_sys._getframe()`, but it does not affect the result.
            # Because the current running frame in vm is what we want here.
            frame = py_sys._getframe()
            while frame and frame is not self.botframe:
                del frame.f_trace
                frame = frame.f_back

    def set_trace(self, frame=None):
        self.reset()
        while frame:
            frame.f_trace = self.trace_dispatch
            self.botframe = frame
            frame = frame.f_back

        self.set_step()
        py_sys.settrace(self.trace_dispatch)
