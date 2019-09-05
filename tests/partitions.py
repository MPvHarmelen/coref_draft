import itertools as it

from hypothesis.strategies import (
    integers,
    composite,
)


def all_partitions(n):
    """
    All partitions of the number `n`.

    From https://stackoverflow.com/a/44209393, which takes it from
    http://jeromekelleher.net/generating-integer-partitions.html
    """
    a = [0 for i in range(n + 1)]
    k = 1
    y = n - 1
    while k != 0:
        x = a[k - 1] + 1
        k -= 1
        while 2 * x <= y:
            a[k] = x
            y -= x
            k += 1
        m = k + 1
        while x <= y:
            a[k] = x
            a[m] = y
            yield a[:k + 2]
            x += 1
            y -= 1
        a[k] = x + y
        y = x + y - 1
        yield a[:k + 1]


def partition(iterable, partitioning):
    """
    Partition an iterable according to a partitioning.
    """
    iterator = iter(iterable)
    return (list(it.islice(iterator, size)) for size in partitioning)


"""
index -> the number of partitions of index
From https://oeis.org/A000041
(and the last one calculated using `all_partitions`)
"""
NUMBER_OF_PARTITIONS = [
    1, 1, 2, 3, 5, 7, 11, 15, 22, 30, 42, 56, 77, 101, 135, 176, 231,  297,
    385, 490, 627, 792, 1002, 1255, 1575, 1958, 2436, 3010,  3718, 4565, 5604,
    6842, 8349, 10143, 12310, 14883, 17977,  21637, 26015, 31185, 37338, 44583,
    53174, 63261, 75175,  89134, 105558, 124754, 147273, 173525, 204226
]
MAX_PARTITIONABLE_NUMBER = len(NUMBER_OF_PARTITIONS) - 1


@composite
def partitions(draw, iterables, min_size=None, max_size=None):
    li = list(draw(iterables))
    bare_size = len(li)
    if bare_size >= len(NUMBER_OF_PARTITIONS):
        raise ValueError(
            "Can only partition lists with length smaller than"
            f" {len(NUMBER_OF_PARTITIONS)}. Please make sure that `iterables`"
            " always generates iterables of at most that size."
            f" Got: {bare_size}.")
    if min_size is None:
        min_size = 0
    if max_size is None:
        max_size = bare_size
    if min_size > bare_size:
        raise ValueError(
            "The passed `min_size` is larger than the drawn iterable."
            " Please make sure that `iterables` always generates iterables of"
            f" at least `min_size`. Got: min_size={min_size!r}")
    if max_size < min_size:
        raise ValueError(
            "`max_size` should be at least `min_size`."
            f" Got: min_size={min_size!r}, max_size={max_size!r}")
    if max_size < 0:
        raise ValueError(f"`max_size` should be at least 0. Got: {max_size!r}")

    # Speed up, because this will take very long if we wait for chance.
    if min_size == bare_size:
        return partition(li, (1 for _ in li))
    if max_size == 0:
        return partition(li, ())
    if max_size == 1:
        return partition(li, (bare_size,))

    # Place to start looking for a partition with the correct size
    partition_index = draw(integers(
        min_value=0,
        max_value=NUMBER_OF_PARTITIONS[bare_size] - 1
    ))
    partitioning = next(filter(                     # find first partition that
        lambda p: min_size <= len(p) <= max_size,   # matches size constraints,
        it.islice(     # starting the search at `partition_index`
            it.cycle(  # but continuing from the start if nothing was found yet
                all_partitions(bare_size)),
            partition_index,
            None))
    )
    return partition(li, partitioning)
