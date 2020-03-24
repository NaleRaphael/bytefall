from ._internal.base import Singleton


DEFAULT_ENV_VARS = {
    'DEBUG_INTERNAL': (int, 0)
}


class Config(metaclass=Singleton):
    def __init__(self):
        self.content = {}
        self._update_from_env()

    def get(self, key, default=None):
        return self.content.get(key, default)

    def _update_from_env(self):
        import os

        for name, default in DEFAULT_ENV_VARS.items():
            _type, val = default
            self.content.update({name: _type(os.getenv(name, val))})
