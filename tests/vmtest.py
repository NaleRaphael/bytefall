"""Testing tools for byterun."""

import ast, dis, io, sys, textwrap, types, unittest
import pytest
from bytefall import get_vm, VirtualMachineError

# Make this false if you need to run the debugger inside a test.
CAPTURE_STDOUT = (not pytest.custom_cmdopt.show_stdout)
# # Make this false to see the traceback from a failure inside interpreter.
CAPTURE_EXCEPTION = (not pytest.custom_cmdopt.show_traceback)


def dis_code(code):
    """Disassemble `code` and all the code it refers to."""
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            dis_code(const)

    print("")
    print(code)
    dis.dis(code)


class VmTestCase(unittest.TestCase):

    def assert_ok(self, source_code, raises=None, globs=None, locs=None):
        """Run `code` in our VM and in real Python: they behave the same."""

        source_code = textwrap.dedent(source_code)
        filename = "<%s>" % self.id()

        ref_code = compile(source_code, filename, "exec", 0, 1)

        # Print the disassembly so we'll see it if the test fails.
        if pytest.custom_cmdopt.show_bytecode:
            dis_code(ref_code)

        # Run the code through our VM and the real Python interpreter, for comparison.
        vm_value, vm_exc, vm_stdout = self.run_in_vm(
            ref_code, globs=globs, locs=locs
        )
        py_value, py_exc, py_stdout = self.run_in_real_python(
            ref_code, globs=globs, locs=locs
        )

        self.assert_same_exception(vm_exc, py_exc)
        self.assertEqual(vm_stdout.getvalue(), py_stdout.getvalue())
        self.assertEqual(vm_value, py_value)
        if raises:
            self.assertIsInstance(vm_exc, raises)
        else:
            self.assertIsNone(vm_exc)

    def run_in_vm(self, code, globs=None, locs=None):
        real_stdout = sys.stdout

        # Run the code through our VM.

        vm_stdout = io.StringIO()
        if CAPTURE_STDOUT:              # pragma: no branch
            sys.stdout = vm_stdout

        vm_value = vm_exc = None
        try:
            vm = get_vm()
            vm_value = vm.run_code(code, f_globals=globs, f_locals=locs)
        except VirtualMachineError:         # pragma: no cover
            # If the VM code raises an error, show it.
            raise
        except AssertionError:              # pragma: no cover
            # If test code fails an assert, show it.
            raise
        except Exception as e:
            # Otherwise, keep the exception for comparison later.
            if not CAPTURE_EXCEPTION:       # pragma: no cover
                raise
            vm_exc = e
        finally:
            sys.stdout = real_stdout
            real_stdout.write("-- stdout ----------\n")
            real_stdout.write(vm_stdout.getvalue())

        return vm_value, vm_exc, vm_stdout

    def run_in_real_python(self, code, globs=None, locs=None):
        real_stdout = sys.stdout

        py_stdout = io.StringIO()
        sys.stdout = py_stdout

        py_value = py_exc = None
        default_globs = {
            '__builtins__': __builtins__,
            '__name__': '__main__',
            '__doc__': None,
            '__package__': None,
        }
        if globs:
            globs.update(default_globs)
        else:
            globs = default_globs
        locs = globs if locs is None else locs

        try:
            py_value = eval(code, globs, locs)
        except AssertionError:              # pragma: no cover
            raise
        except Exception as e:
            py_exc = e
        finally:
            sys.stdout = real_stdout

        return py_value, py_exc, py_stdout

    def assert_same_exception(self, e1, e2):
        """Exceptions don't implement __eq__, check it ourselves."""
        try:
            self.assertEqual(str(e1), str(e2))
            self.assertIs(type(e1), type(e2))
        except:
            import traceback as tb
            if e1:
                print('--- e1 ---')
                print(e1.__repr__())
                tb.print_tb(e1.__traceback__)
            if e2:
                print('--- e2 ---')
                print(e2.__repr__())
                tb.print_tb(e2.__traceback__)
