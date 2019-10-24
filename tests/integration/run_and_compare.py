import os
import sys
import subprocess

from KafNafParserPy import KafNafParser

from multisieve_coreference import main


def run_with_subprocess(input_file, output_file):
    subprocess.check_call(
        [sys.executable, '-m', 'multisieve_coreference'],
        stdin=input_file,
        stdout=output_file
    )


def run_without_subprocess(input_file, output_file):
    main(input_file, output_file)


def run_and_compare(in_filename, out_filename, correct_out_filename,
                    use_subprocess=True):
    """
    Runs the system with `in_filename` as input and `out_filename` as output
    and then compares the result to `correct_out_filename`.

    Because some header data changes (as it should), the contents of
    `correct_out_filename` will be formatted using a call to `str.format` with
    the following keyword arguments:

        - version
        - timestamp
        - beginTimestamp
        - endTimestamp
        - hostname

    """
    with open(in_filename) as fd, open(out_filename, 'wb') as out:
        if use_subprocess:
            run_with_subprocess(fd, out)
        else:
            run_without_subprocess(fd, out)

    with open(out_filename) as out, open(correct_out_filename) as correct:
        # Check something happened and that the result can be parsed
        outnaf = KafNafParser(out_filename)

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


def run_integration(filename, in_dir, correct_out_dir, temp_file, **kwargs):
    in_filename = os.path.join(in_dir, filename)
    correct_outfile = os.path.join(correct_out_dir, filename)

    assert os.path.exists(in_filename)
    assert os.path.exists(correct_outfile)

    run_and_compare(in_filename, temp_file, correct_outfile, **kwargs)
