import os
import pytest
from run_and_compare import run_and_compare


@pytest.fixture
def easy_in_dir(resources_dir):
    return os.path.join(resources_dir, 'easy-sentences/NAFin')


@pytest.fixture
def easy_correct_out_dir(resources_dir):
    return os.path.join(resources_dir, 'easy-sentences/NAFout')


EXPECTED_FAILURES = {
    '52-wie-zal-de-stilte-breken-die-als-ijs-rondom-je-staat.naf'
}


@pytest.fixture
def easy_expected_failures():
    """
    Names of files of which we expect the integration test to fail.
    """
    return EXPECTED_FAILURES


@pytest.fixture
def easy_expected_to_succeed(easy_in_dir, easy_expected_failures):
    """
    Names of files of which we expect the integration test to pass.
    """
    return (
        fn
        for fn in os.listdir(easy_in_dir)
        if fn not in easy_expected_failures
    )


def run_integration(filename, easy_in_dir, easy_correct_out_dir, temp_file):
    infile = os.path.join(easy_in_dir, filename)
    correct_outfile = os.path.join(easy_correct_out_dir, filename)

    assert os.path.exists(infile)
    assert os.path.exists(correct_outfile)

    run_and_compare(infile, temp_file, correct_outfile)


@pytest.mark.slow
def test_integration(easy_expected_to_succeed, easy_in_dir,
                     easy_correct_out_dir, temp_file):
    for filename in easy_expected_to_succeed:
        run_integration(filename, easy_in_dir, easy_correct_out_dir, temp_file)


def pytest_generate_tests(metafunc):
    """
    Generate a separate test case for every expected failure,
    because otherwise we can't check that all of them fail.
    """
    arg = 'failure'
    if arg in metafunc.fixturenames:
        metafunc.parametrize(arg, EXPECTED_FAILURES)


@pytest.mark.xfail(strict=True, error=AssertionError)
def test_failing_integration(failure, easy_in_dir, easy_correct_out_dir,
                             temp_file):
    run_integration(failure, easy_in_dir, easy_correct_out_dir, temp_file)
