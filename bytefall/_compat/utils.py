from bytefall.objects.frameobject import Frame

def check_frame(func):
    def wrapper(frame, *args, **kwargs):
        if not isinstance(frame, Frame):
            raise VirtualMachineError(
                'Given argument `frame`: "%s" is not a instance of %s'
                % (frame, Frame)
            )
        return func(frame, *args, **kwargs)
    return wrapper
