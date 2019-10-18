import pytest
from .run_and_compare import run_integration


@pytest.mark.slow
def test_integration(easy_expected_to_succeed, easy_in_dir,
                     easy_correct_out_dir, temp_file):
    for filename in easy_expected_to_succeed:
        run_integration(filename, easy_in_dir, easy_correct_out_dir, temp_file)


@pytest.mark.xfail(strict=True, error=AssertionError)
def test_failing_integration(easy_expected_to_fail, easy_in_dir,
                             easy_correct_out_dir, temp_file):
    run_integration(easy_expected_to_fail, easy_in_dir, easy_correct_out_dir,
                    temp_file)
