"""Helper functions for internal use only."""

def get_python_version_string():
    from sys import version_info

    py_version = (version_info.major, version_info.minor)
    return ''.join(map(str, py_version))


def get_operations():
    from . import ops  # locally lazy-import to avoid circular reference

    name = 'OperationPy%s' % get_python_version_string()
    cls_inst = getattr(ops, name, None)
    if cls_inst is None:
        raise RuntimeError('No available version of `Operation` class')
    return cls_inst()


def get_vm_class():
    from . import vm  # locally lazy-import to avoid circular reference

    name = 'VirtualMachinePy%s' % get_python_version_string()
    return getattr(vm, name, None)


def get_vm(debug=False):
    cls_vm = get_vm_class()
    if cls_vm is None:
        raise RuntimeError('No available version of virtual machine')
    return cls_vm(debug=debug)


def check_line_number(co, lasti):
    """ Get line number and lower/upper bounds of bytecode instructions
    according to given code object and index of last instruction (f_lasti).

    See also: cython/Objects/codeobject.c::_PyCode_CheckLineNumber
    """
    lnotab = co.co_lnotab
    addr_offsets, line_offsets = lnotab[::2], lnotab[1::2]
    size = len(lnotab)//2
    addr, lb, ub, i = 0, 0, 0, 0
    line = co.co_firstlineno

    while size > 0:
        if addr + addr_offsets[i] > lasti: break
        addr += addr_offsets[i]
        line += line_offsets[i]
        lb = addr
        i += 1
        size -= 1

    ub = addr + addr_offsets[i] if size > 0 else 32767
    return line, lb, ub
