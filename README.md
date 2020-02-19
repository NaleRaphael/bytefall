# bytefall

[![Build Status](https://travis-ci.com/NaleRaphael/bytefall.svg?branch=master)](https://travis-ci.com/NaleRaphael/bytefall)
[![Python Version](https://img.shields.io/badge/python-3.5%20|%203.6%20|%203.7-orange)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

This is a Python virtual machine implemented in pure Python and targeting Python version >= 3.4. It mainly derives from the following great works: [nedbat/byterun][nedbat_byterun] and [darius/tailbiter][darius_tailbiter].

In this project, complete bytecode operations are implemented. And the structure of implementation is modified to make it more easily be extended for multiple versions of Python.

Besides, operations related to `asyncio` is also supported.

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

## Development
- You can run `bytefall` with an argument `--debug` to get more details about the failure
    ```bash
    $ python -m bytefall --debug [YOUR_SCRIPT.py]
    ```

[nedbat_byterun]: https://github.com/nedbat/byterun
[darius_tailbiter]: https://github.com/darius/tailbiter
[bytejection]: https://github.com/naleraphael/bytejection
