import os
import pytest
from run_and_compare import run_and_compare


@pytest.fixture
def in_dir(resources_dir):
    return os.path.join(resources_dir, 'easy-sentences/NAFin')


@pytest.fixture
def correct_out_dir(resources_dir):
    return os.path.join(resources_dir, 'easy-sentences/NAFout')


EXPECTED_FAILURES = {
    '52-wie-zal-de-stilte-breken-die-als-ijs-rondom-je-staat.naf'
}


@pytest.fixture
def expected_failures():
    """
    Names of files of which we expect the integration test to fail.
    """
    return EXPECTED_FAILURES


def pytest_generate_tests(metafunc):
    arg = 'failure'
    if arg in metafunc.fixturenames:
        metafunc.parametrize(arg, EXPECTED_FAILURES)


def run_integration(filename, in_dir, correct_out_dir, temp_file):
    infile = os.path.join(in_dir, filename)
    correct_outfile = os.path.join(correct_out_dir, filename)

    assert os.path.exists(infile)
    assert os.path.exists(correct_outfile)

    run_and_compare(infile, temp_file, correct_outfile)


@pytest.mark.slow
def test_integration(in_dir, correct_out_dir, temp_file, expected_failures):
    expected_to_succeed = filter(
        lambda fn: fn not in expected_failures,
        os.listdir(in_dir)
    )
    for filename in expected_to_succeed:
        run_integration(filename, in_dir, correct_out_dir, temp_file)


@pytest.mark.xfail(strict=True)
def test_failing_integration(failure, in_dir, correct_out_dir, temp_file):
    run_integration(failure, in_dir, correct_out_dir, temp_file)
