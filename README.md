# bytefall

[![Build Status](https://travis-ci.com/NaleRaphael/bytefall.svg?branch=master)](https://travis-ci.com/NaleRaphael/bytefall)
[![codecov](https://codecov.io/gh/NaleRaphael/bytefall/branch/master/graph/badge.svg)](https://codecov.io/gh/NaleRaphael/bytefall)
[![Python Version](https://img.shields.io/badge/python-3.4%20|%203.5%20|%203.6%20|%203.7%20|%203.8-orange)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

This is a Python virtual machine implemented in pure Python and targeting Python version >= 3.4. It mainly derives from the following great works: [nedbat/byterun][nedbat_byterun] and [darius/tailbiter][darius_tailbiter].

In this project, complete bytecode operations are implemented. And the structure of implementation is modified to make it more easily be extended for multiple versions of Python.

Besides, operations related to `asyncio` are also supported.

More features for debugging bytecode are going to be implemented, because I'm also trying to use this tool to fix some bugs in my own project [bytejection][bytejection].

## Installation
```bash
$ pip install git+https://github.com/NaleRaphael/bytefall.git
```

## Usage
Currently, version of virtual machine is automatically chosen according to your base Python runtime. Because it requires a base runtime to compile Python code to bytecode.

Therefore, you may need to create different virtual environment with the version of Python runtime you want to run this virtual machine.

```bash
$ python -m bytefall [YOUR_SCRIPT.py]
```

## Run tests
```bash
$ python -m pytest ./tests/

# run tests including cases that usually take long time
$ python -m pytest ./tests/ --runslow
```

## Features
- You can run `bytefall` with an argument `--debug` to get detailed traceback of an unexpected error
    ```bash
    $ python -m bytefall --debug [YOUR_SCRIPT.py]
    ```

- To show detailed information of each bytecode instruction which is going to be executed, you can run `bytefall` with `--show_oparg`.
    ```bash
    $ python -m bytefall --show_oparg [YOUR_SCRIPT.py]
    ```

    Then you can get something like this:
    ```raw
    # Format:
    # Instruction name | Arguments of instruction | Stack content on current frame

    LOAD_CONST (<code object main at 0x0000021583CAC150, file "foo.py", line 2>,) []
    LOAD_CONST ('main',) [<code object main at 0x0000021583CAC150, file "foo.py", line 2>]
    MAKE_FUNCTION (0,) [<code object main at 0x0000021583CAC150, file "foo.py", line 2>, 'main']
    STORE_NAME ('main',) [<Function main at 0x0000021583DDAA58>]
    # ...
    ```

- To trace execution of each bytecode instruction, you can run `bytefall` with `--trace_opcode`, and use `pdb.set_trace()` to determine the entry.
    ```bash
    $ python -m bytefall --trace_opcode [YOUR_SCRIPT.py]
    ```

    ```python
    # YOUR_SCRIPT.py
    def main():
        foo()
        import pdb; pdb.set_trace()
        bar()   # <- entry
        buzz()
    ```

- To explore the internal execution of virtual machine with `pdb`, you can run it with an environment variable `DEBUG_INTERNAL`
    ```bash
    $ DEBUG_INTERNAL=1 python -m bytefall [YOUR_SCRIPT.py]
    ```

[nedbat_byterun]: https://github.com/nedbat/byterun
[darius_tailbiter]: https://github.com/darius/tailbiter
[bytejection]: https://github.com/naleraphael/bytejection
