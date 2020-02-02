import pytest


class CustomCommandLineOption(object):
    """An object for storing command line option parsed by pytest.

    `pytest.config` global object is deprecated and removed since version 5.0.
    In order to access command line options in methods of custom `VmTestCase`,
    this class is made to plug in pytest module instance.
    """
    def __init__(self):
        self._content = {}

    def __str__(self):
        return str(self._content)

    def add(self, key, value):
        self._content.update({key: value})

    def delete(self, key):
        del self._content[key]

    def __getattr__(self, key):
        if key in self._content:
            return self._content[key]
        else:
            return super(CustomCommandLineOption, self).__getattr__(key)


def pytest_addoption(parser):
    parser.addoption(
        '--show_bytecode', action='store_true',
        help='Show compiled bytecode when a test fails.'
    )
    parser.addoption(
        '--show_stdout', action='store_true',
        help='Show STDOUT of tests.'
    )
    parser.addoption(
        '--show_traceback', action='store_true',
        help='Show traceback of failed tests inside interpreter.'
    )
    parser.addoption(
        '--runslow', action='store_true',
        help='Run slow tests.'
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption('--runslow'):
        return
    skip_slow = pytest.mark.skip(reason='need --runslow option to run')
    for item in items:
        if 'slow' in item.keywords:
            item.add_marker(skip_slow)


def pytest_configure(config):
    config.addinivalue_line('markers', 'slow: mark test as slow to run')

    pytest.custom_cmdopt = CustomCommandLineOption()
    pytest.custom_cmdopt.add(
        'show_bytecode', config.getoption('--show_bytecode')
    )
    pytest.custom_cmdopt.add(
        'show_stdout', config.getoption('--show_stdout')
    )
    pytest.custom_cmdopt.add(
        'show_traceback', config.getoption('--show_traceback')
    )
