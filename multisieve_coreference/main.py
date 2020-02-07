"""
Definition of main entry-points of `multisieve-coreference`
"""
import sys
import time
import logging
from pkg_resources import get_distribution

import yaml
from KafNafParserPy import KafNafParser, Clp

from . import constants as c
from .resolve_coreference import resolve_coreference
from .dump import add_coreference_to_naf


logger = logging.getLogger(None if __name__ == '__main__' else __name__)


def process_coreference(
        nafin,
        fill_gaps=c.FILL_GAPS_IN_OUTPUT,
        include_singletons=c.INCLUDE_SINGLETONS_IN_OUTPUT,
        language=c.LANGUAGE):
    """
    Process coreferences and add to the given NAF.

    Main entry point of multisieve-coreference if you have a NAF-object.

    Note that header and coreference information is added in-place.
    """
    # timestamp begin time
    begintime = time.strftime('%Y-%m-%dT%H:%M:%S%Z')

    entities = resolve_coreference(
        nafin,
        fill_gaps=fill_gaps,
        include_singletons=include_singletons,
        language=language
    )

    logger.info("Adding coreference information to NAF...")
    add_coreference_to_naf(nafin, entities)

    # timestamp end time
    endtime = time.strftime('%Y-%m-%dT%H:%M:%S%Z')

    # add naf header information
    add_naf_header(nafin, begintime, endtime)


def add_naf_header(nafobj, begintime, endtime):
    """
    Add header information to NAF in-place.

    :param nafobj:      NAF-object to add header to
    :param begintime:   string representation of begin time to add to header
    :param endtime:     string representation of end time to add to header
    """
    lp = Clp(
        name="vua-multisieve-coreference",
        version=get_distribution(__name__.split('.')[0]).version,
        btimestamp=begintime,
        etimestamp=endtime)
    nafobj.add_linguistic_processor('coreferences', lp)


def parse_args(argv=None):
    """
    Parse command-line arguments.

    Also calls `logging.basicConfig` to configure the logging level passed on
    the command-line.

    :param argv:    list of strings to use for parsing, or None for sys.argv
    :param return:  {argument: value} dictionary of parsed arguments
    """
    from argparse import ArgumentParser, FileType

    parser = ArgumentParser()
    parser.add_argument('-l', '--log-level', help="Logging level",
                        type=str.upper, default='WARNING')
    parser.add_argument(
        '--log-config',
        help="YAML-file to read logging configuration from."
        " Overrides the `log-level`, if passed.",
        type=FileType('r')
    )
    if c.INCLUDE_SINGLETONS_IN_OUTPUT:
        parser.add_argument(
            '-s',
            '--remove-singletons',
            help="Remove singleton mentions from the output",
            action='store_false',
            dest='include_singletons',
        )
    else:
        parser.add_argument(
            '-s',
            '--include-singletons',
            help="Include singleton mentions in the output",
            action='store_true',
        )
    if c.FILL_GAPS_IN_OUTPUT:
        parser.add_argument(
            '-g',
            '--keep-gaps',
            help="Keep gaps in mention spans, i.e. don't fill them.",
            action='store_false',
            dest='fill_gaps'
        )
    else:
        parser.add_argument(
            '-f',
            '--fill-gaps',
            help="Whether to fill gaps in mention spans",
            action='store_true',
        )
    parser.add_argument(
        '--language',
        help="RFC5646 language tag of language data to use. Currently only"
        " reads a different set of stopwords. Defaults to {}".format(
            c.LANGUAGE),
        default=c.LANGUAGE
    )
    cmdl_args = vars(parser.parse_args(argv))

    # Logging configuration
    basic_level = cmdl_args.pop('log_level')
    config_file = cmdl_args.pop('log_config', None)

    if config_file is not None:
        logging.config.dictConfig(
            yaml.safe_load(config_file)
        )
    else:
        logging.basicConfig(level=basic_level)

    return cmdl_args


def main(input_file=None, output_file=None, **kwargs):
    """
    Main entry point for multisieve-coreference if all you have is an
    (input, output)-pair of (open) files.

    Does not parse command-line arguments. Instead, use:

        main(**parse_args())

    :param input_file:      (open) file-object to read input NAF data from
                            defaults to `sys.stdin`
    :param output_file:     (open) file-object to write output NAF data to
                            !! NB !! must be in binary mode!
                            defaults to `sys.stdout`
    :param **kwargs:        keyword arguments for `process_coreference`
    """
    if input_file is None:
        input_file = sys.stdin

    logger.info("Reading...")
    nafobj = KafNafParser(input_file)

    logger.info("Processing...")
    process_coreference(nafobj, **kwargs)

    # When `output_file` is None, this should default to `sys.stdout` in
    # binary mode.
    logger.info("Writing...")
    nafobj.dump(output_file)


if __name__ == '__main__':
    main(**parse_args())
