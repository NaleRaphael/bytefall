from bytefall._internal.base import Singleton


class BaseConfig(object):
    def __init__(self):
        self.content = {}

    def get(self, key, default=None):
        return self.content.get(key, default)


class EnvConfig(BaseConfig):
    DEFAULTS = {
        'DEBUG_INTERNAL': (int, 0)
    }
    def __init__(self):
        super(EnvConfig, self).__init__()
        self._update_from_env()

    def _update_from_env(self):
        import os

        for name, default in self.DEFAULTS.items():
            _type, val = default
            self.content.update({name: _type(os.getenv(name, val))})


class CLIConfig(BaseConfig):
    DEFAULTS = {
        'debug': False,
        'show_oparg': False,
    }
    def __init__(self, cli_args=None):
        """
        Parameters
        ----------
        cli_args : `argparse.Namespace`, optional
            Arguments specified from CLI.
        """
        super(CLIConfig, self).__init__()
        if cli_args is not None:
            kws = vars(cli_args)
            required_kws = {k: kws.get(k, v) for k, v in self.DEFAULTS.items()}
            self.content.update(kws)
