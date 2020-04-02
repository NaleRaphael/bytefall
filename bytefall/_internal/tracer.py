from pdb import Pdb

__all__ = ['OPTracer']


class OPTracer(Pdb):
    """ opcode (bytecode instruction) tracer.

    This is not a tracer for general purpose, and this should be used in the
    internal of this VM only. This tracer replis on the execution mechanism
    of built-in module `pdb` to make end users able to determine the entry
    of opcode tracing. Therefore, it's easy to use like the following example:

    ```python
    def main():
        foo()
        import pdb; pdb.set_trace()
        bar()   # <- entry
        buzz()

    # --- In terminal ---
    # -> def bar():
    # (Pdb) ...
    ```

    Important note for developer: Target function to be stepped in should be
    placed right after the calling of `set_trace()`, that is:

    ```python
    tracer = OPTracer()

    # ... omitted code

    tracer.set_trace(sys._getframe())
    your_function()   # <- this
    ```
    """
    def __init__(self, *args, **kwargs):
        super(OPTracer, self).__init__(*args, **kwargs)
        self.prompt = '(OPTracer) '
        self.first_frame = None

    def set_trace(self, frame=None):
        # In order to make this tracer stop at the beginning of the function
        # call of a bytecode instruction, we have to memorize the entry.
        self.first_frame = frame
        return super(OPTracer, self).set_trace(frame)

    def stop_here(self, frame):
        if frame is self.first_frame:
            return False
        else:
            self.first_frame = None
        return super(OPTracer, self).stop_here(frame)
