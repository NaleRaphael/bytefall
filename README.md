# bytefall

[![Build Status](https://travis-ci.com/NaleRaphael/bytefall.svg?branch=master)](https://travis-ci.com/NaleRaphael/bytefall)

(This project is still WIP, but it currently works totally fine on Py34)

This is a Python virtual machine implemented in pure Python for version >= Py34. It mainly derives from the following great works: [nedbat/byterun][nedbat_byterun] and [darius/tailbiter][darius_tailbiter].

In this project, more complete bytecode operations are implemented. And the structure of implementation is modified to make it more easily be extended for multiple version of Python.

More features for debugging bytecode are going to be implemented, because I'm trying to use this tool to fix some bugs in my own project [bytejection][bytejection].

## Installation
```bash
$ pip install git+https://github.com/NaleRaphael/bytefall.git
```

## Usage
```bash
$ python -m bytefall [YOUR_SCRIPT.py]
```

## Run tests
```bash
$ python -m pytest ./tests/

# run tests including cases that usually take long time
$ python -m pytest ./tests/ --runslow
```

[nedbat_byterun]: https://github.com/nedbat/byterun
[darius_tailbiter]: https://github.com/darius/tailbiter
[bytejection]: https://github.com/naleraphael/bytejection

## Development
- You can run `bytefall` with an argument `--debug` to get more details about the failure
    ```bash
    $ python -m bytefall --debug [YOUR_SCRIPT.py]
    ```
