from sys import byteorder as BYTE_ORDER
import ctypes

# Pointer size
P_SIZE = ctypes.sizeof(ctypes.c_void_p)

# Unit of memory representation (in byte)
M_UNIT = P_SIZE // 4    # 4: 32-bit (4*8 bit)

# Detect whether we are on a x32/x64 mode or not
IS_X64 = P_SIZE == 8

# Type of a pointer unit for memory (x64: 2 bytes; x32: 1 byte)
P_MEM_TYPE = ctypes.POINTER(ctypes.c_ulong if IS_X64 else ctypes.c_uint)

if IS_X64:
    MASK_H_HALF = 0xffffffff00000000
    MASK_L_HALF = 0x00000000ffffffff
else:
    MASK_H_HALF = 0xffff0000
    MASK_L_HALF = 0x0000ffff

# --- Py_DecRef
ctypes.pythonapi.Py_DecRef.argtypes = (P_MEM_TYPE, )
ctypes.pythonapi.Py_DecRef.restypes = None

# --- Py_IncRef
ctypes.pythonapi.Py_IncRef.argtypes = (P_MEM_TYPE, )
ctypes.pythonapi.Py_IncRef.restypes = None


def id2addr(_id):
    """ Convert result of `id()` to memory address (decimal).

    Note that the order of output will be adjusted according to the endianness
    for x64 system.
    """
    if IS_X64:
        addr_high = (_id & MASK_H_HALF) >> 32
        addr_low = _id & MASK_L_HALF
        if BYTE_ORDER == 'little':
            return addr_low, addr_high
        else:
            return addr_high, addr_low
    else:
        return _id


def addr2id(addr_tuple):
    """ Convert address to id (result of `id()`).

    For x64 system, given `addr_tuple` should be a tuple containing 2 elements.
    Besides, elements should be ordered according to the endianness of system.

    For little endian system, `addr_tuple` should be `(addr_high, addr_low)`.
    For big endian system, `addr_tuple` should be `(addr_low, addr_high)`.

    `addr_high` denotes the higher 4 bytes of address, and `addr_low` denotes
    the lower 4 bytes of address.
    """
    length = 2 if IS_X64 else 1
    if not isinstance(addr_tuple, tuple):
        raise ValueError('Given `addr_tuple` should be a tuple.')
    if len(addr_tuple) != length:
        raise ValueError('Length of given address tuple should be %s' % length)

    if IS_X64:
        if BYTE_ORDER == 'little':
            return (addr_tuple[1] << 32) | addr_tuple[0]
        else:
            return (addr_tuple[0] << 32) | addr_tuple[1]
    else:
        return addr_tuple[0]


def p_assign_address(p, _id, idx):
    """ Assign an address `_id` to specific index of memory array that given
    pointer `p` pointing.
    """
    if IS_X64:
        # Cache the original address of target for decreasing reference count
        id_ori = addr2id((p[idx], p[idx+1]))
        # Assign the new address to target 
        p[idx], p[idx+1] = id2addr(_id)

        ctypes.pythonapi.Py_DecRef(ctypes.cast(id_ori, P_MEM_TYPE))
        ctypes.pythonapi.Py_IncRef(ctypes.cast(_id, P_MEM_TYPE))
    else:
        p[idx] = _id
