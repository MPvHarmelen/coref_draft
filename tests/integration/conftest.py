import os
import pytest

pytest.register_assert_rewrite('run_and_compare')


@pytest.fixture
def temp_file():
    import tempfile
    return tempfile.mktemp()


@pytest.fixture
def example_naf_output(resources_dir):
    return resources_dir / 'example-out.naf'


@pytest.fixture
def easy_in_dir(resources_dir):
    return resources_dir / 'easy-sentences/NAFin'


@pytest.fixture
def easy_correct_out_dir(resources_dir):
    return resources_dir / 'easy-sentences/NAFout'


EASY_EXPECTED_FAILURES = {
    '52-wie-zal-de-stilte-breken-die-als-ijs-rondom-je-staat.naf',
}


@pytest.fixture
def easy_expected_failures():
    """
    Names of files of which we expect the integration test to fail.
    """
    return EASY_EXPECTED_FAILURES


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


def pytest_generate_tests(metafunc):
    """
    Generate a separate test case for every expected failure,
    because otherwise we can't check that all of them fail.
    """
    arg = 'easy_expected_to_fail'
    if arg in metafunc.fixturenames:
        metafunc.parametrize(arg, EASY_EXPECTED_FAILURES)
