from .base import Singleton


class GlobalCache(metaclass=Singleton):
    _instance = None
    def __init__(self):
        self._content = {}

    def __str__(self):
        return str(self._content)

    def get(self, *args):
        return self._content.get(*args)

    def pop(self, *args):
        return self._content.pop(*args)

    def set(self, key, value):
        self._content.update({key: value})

    def delete(self, key):
        del self._content[key]
