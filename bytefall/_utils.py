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


def get_vm():
    cls_vm = get_vm_class()
    if cls_vm is None:
        raise RuntimeError('No available version of virtual machine')
    return cls_vm()
