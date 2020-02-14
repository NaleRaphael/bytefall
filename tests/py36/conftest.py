import pytest
from sys import version_info

CAN_BE_SKIPPED = version_info < (3, 6)


def pytest_runtest_setup(item):
    if CAN_BE_SKIPPED:
        pytest.skip('run in Python >= 3.6')
