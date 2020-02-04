import sys
import subprocess

from KafNafParserPy import KafNafParser


def run_and_compare(infile, outfile, correctoutfile, cmdl_args=[]):
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
    with open(infile) as fd, open(outfile, 'w+') as out:
        try:
            subprocess.run(
                [sys.executable, '-m', 'multisieve_coreference'] + cmdl_args,
                stdin=fd,
                stdout=out,
                stderr=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            out.seek(0)
            raise AssertionError(
                f"stderr output of the process:\n\n{e.stderr.decode()}\n\n"
                f"stdout output of the process:\n\n{out.read()}") from e

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
        assert correct == out.read()
