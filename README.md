# bytefall
(This project is still WIP, but it currently works totally fine on Py34)

This is a Python virtual machine implemented in pure Python for version >= Py34. It mainly derives from the following great works: [nedbat/byterun][nedbat_byterun] and [darius/tailbiter][darius_tailbiter].

In this project, more complete bytecode operations is implemented. And the structure of implementation is modified to make it more easily to support multiple version of Python.

More features for debugging bytecode is going to be implemented, because I'm trying to use this tool to fix some bugs in my own project [bytejection][bytejection].

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
