import os
import sys
import subprocess

from KafNafParserPy import KafNafParser


def run_and_compare(infile, outfile, correctoutfile):
    """
    Runs the system with `infile` as input and `outfile` as output and then
    compares the result to `correctoutfile`.

    Because some header data changes (as it should), the contents of
    `correctoutfile` will be formatted using a call to `str.format` with the
    following keyword arguments:

        - version
        - timestamp
        - beginTimestamp
        - endTimestamp
        - hostname

    """
    with open(infile) as fd, open(outfile, 'w') as out:
        subprocess.check_call(
            [sys.executable, '-m', 'multisieve_coreference'],
            stdin=fd,
            stdout=out
        )

    with open(outfile) as out, open(correctoutfile) as correct:
        # Check something happened and that the result can be parsed
        outnaf = KafNafParser(outfile)

        # Get the header information to be able to compare raw files
        our_header_layer = list(
            outnaf.get_linguisticProcessors()
        )[-1]
        assert our_header_layer.get_layer() == 'coreferences'

        processors = list(
            our_header_layer.get_linguistic_processors()
        )
        assert len(processors) == 1

        our_header_data = processors[0]

        correct = correct.read().format(
            version=our_header_data.get_version(),
            timestamp=our_header_data.get_timestamp(),
            beginTimestamp=our_header_data.get_beginTimestamp(),
            endTimestamp=our_header_data.get_endTimestamp(),
            hostname=our_header_data.get_hostname(),
        )
        assert out.read() == correct


def run_integration(filename, in_dir, correct_out_dir, temp_file):
    infile = os.path.join(in_dir, filename)
    correct_outfile = os.path.join(correct_out_dir, filename)

    assert os.path.exists(infile)
    assert os.path.exists(correct_outfile)

    run_and_compare(infile, temp_file, correct_outfile)
