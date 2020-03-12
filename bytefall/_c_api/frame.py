import ctypes
from ._pointer import P_MEM_TYPE, M_UNIT, p_assign_address

# --- PyThreadState_Get
ctypes.pythonapi.PyThreadState_Get.argtypes = None
ctypes.pythonapi.PyThreadState_Get.restype = P_MEM_TYPE

# --- PyFrame_New
ctypes.pythonapi.PyFrame_New.argtypes = (
    P_MEM_TYPE,
    P_MEM_TYPE,
    ctypes.py_object,
    ctypes.py_object
)
ctypes.pythonapi.PyFrame_New.restype = ctypes.py_object


__all__ = ['convert_to_builtin_frame']


class MemberIndexFinder(object):
    def __init__(self):
        self._cache = {}

    def find(self, obj, name, p_val=None, p_idx=None, search_rng=10):
        """ Get index of a member of a internal object.

        If `p_idx` and `p_val` is given, they will be used to check whether
        `obj_memory_array[p_idx] == p_val` is true or not in the first try.

        If it failed to find the index of corresponding value by presumption,
        then we search that value by given `search_rng`.
        """
        if name in self._cache:
            return self._cache[name]

        po = ctypes.cast(id(obj), P_MEM_TYPE)
        if p_idx is not None and p_val is not None:
            if p_val == po[p_idx]:
                self._cache.update({name: p_idx})
                return p_idx
        elif p_val is None:
            raise ValueError('No presumed value for searching.')

        try:
            idx = po[:search_rng].index(p_val)
        except ValueError as e:
            raise RuntimeError('Failed to locate member in object') from e

        self._cache.update({name: idx})
        return idx


mem_idx_finder = MemberIndexFinder()


def make_frame(source):
    """ Make a builtin frame object (PyFrameObject).

    Calling `PyFrame_New` to create a frame object is not enough to control
    the created content. Therefore, we have to modify content by assigning
    values through pointer. However, indices of member in frame object may
    be changed between different versions of CPython.

    In order to make the implementation robust, we tend to not hard code
    index of desired member in frame object. Instead, we make a presumption
    of index and value of a member, then verify it by checking the value
    at address.

    Parameters
    ----------
    source : bytefall.pyframe.Frame

    Returns
    -------
    frame : frame (builtin frame object)
    """
    frame = ctypes.pythonapi.PyFrame_New(
        ctypes.pythonapi.PyThreadState_Get(),
        ctypes.cast(id(source.f_code), P_MEM_TYPE),
        source.f_globals,
        source.f_locals
    )

    # Presumed index of `f_lasti` in the memory array of a `frame` object:
    # - PyObject_VAR_HEAD: 3*M_UNIT (while `Py_REF_DEBUG` is not defined)
    # - f_back, f_code, ..., f_trace: 8*M_UNIT
    # - f_trace_lines, f_trace_opcodes: 2*sizeof(char)
    # - f_gen: 1*M_UNIT
    # (for Python 3.7, see also: cpython/Include/frameobject.h)
    p_idx = (3+8+1)*M_UNIT + 2
    idx_f_lasti = mem_idx_finder.find(
        frame, 'f_lasti',
        p_val=ctypes.c_ulong(frame.f_lasti).value,
        p_idx=p_idx,
        search_rng=p_idx*2
    )

    # Presumed index of `f_lineno` in the memory array of a `frame` object:
    # which is defined right after `f_lasti`
    p_idx = idx_f_lasti + 1
    idx_f_lineno = mem_idx_finder.find(
        frame, 'f_lineno',
        p_idx=p_idx,
        p_val=ctypes.c_ulong(frame.f_lineno).value,
        search_rng=p_idx*2
    )

    # Modify `f_lasti` and `f_lineno`
    pf = ctypes.cast(id(frame), P_MEM_TYPE)
    pf[idx_f_lasti] = source.f_lasti
    pf[idx_f_lineno] = source.f_lineno
    return frame


def remove_f_back(frame):
    """ Remove content of `frame.f_back`. """
    # Presumed index of `f_back` in the memory array of a `frame` object:
    # - PyObject_VAR_HEAD: 3*M_UNIT (while `Py_REF_DEBUG` is not defined)
    p_idx = 3*M_UNIT

    # For x32 system, this mask takes all bits of memory address. Meanwhile,
    # unit of memory address is also 4 bytes.
    # For x64 system, this mask takes the lower 32 bits of memory address,
    # but unit of memory address is 8 bytes. In this case, we have to check
    # the endianness of system.
    mask = 0xffffffff
    p_val = id(frame.f_back) & mask

    idx_f_back = mem_idx_finder.find(
        frame, 'f_back',
        p_idx=p_idx,
        p_val=p_val,
        search_rng=p_idx*2
    )

    # Remove f_back by assigning the address of `None`
    pf = ctypes.cast(id(frame), P_MEM_TYPE)
    p_assign_address(pf, id(None), idx_f_back)


def replace_f_back(f1, f2):
    """ Replace `f1.f_back` (a frame object) by another frame.

    Attributes of builtin frame object are read-only. In order to modify
    them, we have to manipulate them through pointer.

    Inside the definition of `PyFrameObject`, `f_back` is the second member.
    Before it, there is a macro `PyObject_VAR_HEAD`, which can be expanded to:

    ```c
    typedef struct _frame {
        // PyObject_VAR_HEAD (while `Py_REF_DEBUG` is not defined)
        Py_ssize_t ob_refcnt;
        PyTypeObject *ob_type;
        Py_ssize_t ob_size;

        struct _frame *f_back
        // ... more members below
    } PyFrameObject;
    ```

    Size of `ob_refcnt`, `*ob_type`, `ob_size` are 1 unit of memory address
    representation (x32: 4 bytes, x64: 8 bytes). So that we can presume
    `f_back` is the 4th member. Then we can modify the content through pointer.
    """
    # Find the member index of `f_back` in `PyFrameObject`. See also the
    # implementation of `remove_f_back` for relative details.
    p_idx = 3*M_UNIT
    mask = 0xffffffff
    p_val = id(f1.f_back) & mask

    idx_f_back = mem_idx_finder.find(
        f1, 'f_back',
        p_idx=p_idx,
        p_val=p_val,
        search_rng=p_idx*2
    )

    # make `f1.f_back` point to the location of f2
    pf1 = ctypes.cast(id(f1), P_MEM_TYPE)
    p_assign_address(pf1, id(f2), idx_f_back)


def convert_to_builtin_frame(source):
    """ Convert a `bytefall.pyframe.Frame` object to a builtin frame object
    that holds the same content.

    Note that builtin frame object cannot be created in Python side directly,
    nor be instantiated by a class inheriting `types.FrameType`. It can only
    be created through calling c-api `PyFrame_New`.

    Parameters
    ----------
    source : bytefall.pyframe.Frame

    Returns
    -------
    retval : frame (builtin frame object)
    """
    retval = make_frame(source)
    src, dst = source, retval

    while src.f_back:
        cframe = make_frame(src.f_back)
        replace_f_back(dst, cframe)
        src, dst = src.f_back, dst.f_back

    # Eliminate remaining `f_back`, which contains information of vm
    remove_f_back(dst)

    return retval
