from argparse import ArgumentParser, REMAINDER
import logging
from . import execfile as _execfile
from .config import CLIConfig


def main():
    parser = ArgumentParser(prog='bytefall')
    parser.add_argument('-m', '--module', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('--debug', action='store_true',
                        help=('Show detailed traceback of internal execution '
                        'if there is an unexpected error.'))
    parser.add_argument('--show_oparg', action='store_true',
                        help='Show parsed arguments per bytecode instruction.')
    parser.add_argument('prog')
    parser.add_argument('args', nargs=REMAINDER)

    args = parser.parse_args()

    run_fn = _execfile.run_python_module if args.module else _execfile.run_python_file
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    argv = [args.prog] + args.args
    run_fn(args.prog, argv, config=CLIConfig(args))


if __name__ == '__main__':
    main()
