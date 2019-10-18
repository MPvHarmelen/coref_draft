import pytest
from .run_and_compare import run_and_compare

from multisieve_coreference.resolve_coreference import process_coreference


def test_main_example(example_naf_file, temp_file, example_naf_output):
    run_and_compare(example_naf_file, temp_file, example_naf_output)


def test_example_without_fill(example_naf_object, caplog):
    caplog.set_level('DEBUG', 'multisieve_coreference.dump')
    process_coreference(example_naf_object, fill_gaps=False)
    assert example_naf_object.coreference_layer is not None


def test_example_debug(example_naf_object, caplog):
    caplog.set_level('DEBUG')
    process_coreference(example_naf_object)
    assert example_naf_object.coreference_layer is not None


@pytest.mark.slow
def test_main_sonar1_without_fill(sonar_naf_object1, caplog):
    caplog.set_level('DEBUG', 'multisieve_coreference.dump')
    process_coreference(sonar_naf_object1, fill_gaps=False)
    assert sonar_naf_object1.coreference_layer is not None


def test_main_sonar2_without_fill(sonar_naf_object2, caplog):
    caplog.set_level('DEBUG', 'multisieve_coreference.dump')
    process_coreference(sonar_naf_object2, fill_gaps=False)
    assert sonar_naf_object2.coreference_layer is not None


@pytest.mark.slow
def test_main_sonar3_without_fill(sonar_naf_object3, caplog):
    caplog.set_level('DEBUG', 'multisieve_coreference.dump')
    process_coreference(sonar_naf_object3, fill_gaps=False)
    assert sonar_naf_object3.coreference_layer is not None


def test_example_with_fill(example_naf_object, caplog):
    caplog.set_level('DEBUG', 'multisieve_coreference.dump')
    process_coreference(example_naf_object, fill_gaps=True)
    assert example_naf_object.coreference_layer is not None


@pytest.mark.slow
def test_main_sonar1_with_fill(sonar_naf_object1, caplog):
    caplog.set_level('DEBUG', 'multisieve_coreference.dump')
    process_coreference(sonar_naf_object1, fill_gaps=True)
    assert sonar_naf_object1.coreference_layer is not None


def test_main_sonar2_with_fill(sonar_naf_object2, caplog):
    caplog.set_level('DEBUG', 'multisieve_coreference.dump')
    process_coreference(sonar_naf_object2, fill_gaps=True)
    assert sonar_naf_object2.coreference_layer is not None


@pytest.mark.slow
def test_main_sonar3_with_fill(sonar_naf_object3, caplog):
    caplog.set_level('DEBUG', 'multisieve_coreference.dump')
    process_coreference(sonar_naf_object3, fill_gaps=True)
    assert sonar_naf_object3.coreference_layer is not None
