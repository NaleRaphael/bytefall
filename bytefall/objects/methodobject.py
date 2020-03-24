__all__ = ['Method']


class Method(object):
    def __init__(self, obj, _class, func):
        self.__self__ = obj
        self._class = _class
        self.__func__ = func

    def __repr__(self):
        name = '%s.%s' % (self._class.__name__, self.__func__.__name__)
        return '<bound method %s of %s>' % (name, self.__self__)

    def __call__(self, *args, **kwargs):
        return self.__func__(self.__self__, *args, **kwargs)
