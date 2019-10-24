import os
import pytest
import resource


def set_memory_limit(limit=2 * 1024**3):
    """
    To make sure tests that cause memory overflow do not crash the system,
    the soft limit of memory is set quite low.

    Luckily, this also seems to set the limit for child processes.

    The default is 2 GiB.

    :param limit:    new memory limit in bytes
    """
    memory_resource = resource.RLIMIT_VMEM \
        if hasattr(resource, 'RLIMIT_VMEM') \
        else resource.RLIMIT_AS

    original_soft, original_hard = resource.getrlimit(memory_resource)

    if original_hard == resource.RLIM_INFINITY or limit <= original_hard:
        print(
            f"Set memory limit to {limit/1024**2:3g} MiB")
        resource.setrlimit(memory_resource, (limit, original_hard))
    else:
        print(
            "Could not change original soft limit of"
            f" {original_soft/1024**3:g} GiB"
            f" to {limit/1024**3:g} GiB."
            f" Original hard limit: {original_hard/1024**3:g} GiB"
        )


set_memory_limit()


@pytest.fixture
def resources_dir():
    return 'resources'


# Example file
@pytest.fixture
def example_naf_file(resources_dir):
    return os.path.join(resources_dir, 'example-in.naf')


@pytest.fixture
def example_naf_object(example_naf_file):
    from KafNafParserPy import KafNafParser
    return KafNafParser(example_naf_file)


# SoNaR files that caused problems before
@pytest.fixture
def sonar_naf_file1(resources_dir):
    """This file contains a circular reference of size 2"""
    return os.path.join(resources_dir, 'SoNaR-dpc-bal-001236-nl-sen-in.naf')


@pytest.fixture
def sonar_naf_object1(sonar_naf_file1):
    from KafNafParserPy import KafNafParser
    return KafNafParser(sonar_naf_file1)


@pytest.fixture
def sonar_naf_file2(resources_dir):
    return os.path.join(resources_dir, 'SoNaR-dpc-cam-001280-nl-sen-in.naf')


@pytest.fixture
def sonar_naf_object2(sonar_naf_file2):
    from KafNafParserPy import KafNafParser
    return KafNafParser(sonar_naf_file2)


@pytest.fixture
def sonar_naf_file3(resources_dir):
    """
    This file contains a fully-connected sub-graph of size 4.
    (ELI5: very complicated circular reference.)
    """
    return os.path.join(resources_dir, 'SoNaR-WR-P-E-C-0000000021-in.naf')


@pytest.fixture
def sonar_naf_object3(sonar_naf_file3):
    from KafNafParserPy import KafNafParser
    return KafNafParser(sonar_naf_file3)
