import logging
from operator import attrgetter, itemgetter

import pytest

from multisieve_coreference.entities import Entities
from multisieve_coreference.entity import Entity

from hypothesis import given, settings, Verbosity, HealthCheck
from hypothesis.strategies import (
    text,
    lists,
    integers,
    composite,
    randoms,
    data,
)

from partitions import partitions, MAX_PARTITIONABLE_NUMBER

logger = logging.getLogger() if __name__ == '__main__' \
    else logging.getLogger(__name__)


def ilen(iterable):
    return sum(1 for _ in iterable)


class EmptyMention:
    """
    A stand-in Mention object that (only) has an 'id' attribute.
    """
    def __init__(self, id):
        self.id = id

    def __repr__(self):
        return f'EmptyMention({self.id!r})'

    def __eq__(self, other):
        return isinstance(other, EmptyMention) and self.id == other.id

    @staticmethod
    def unique(mentions):
        """
        A list of all mentions with unique ids.
        """
        ids_had = set()
        unique = []
        for mention in mentions:
            if mention.id not in ids_had:
                unique.append(mention)
                ids_had.add(mention.id)
        return unique


def mentions(ids=text()):
    """
    A stand-in Mention object that (only) has an 'id' attribute.
    """
    return ids.map(EmptyMention)


@composite
def lists_of_unique_mentions(draw, min_size=None, max_size=None):
    """
    Sets of stand-in Mention objects.
    """
    if (min_size is not None and min_size < 0) or \
       (max_size is not None and max_size < 0):
        raise ValueError(
            "Both min and max size should be larger than or equal to zero."
            f" Got: min_size={min_size!r}, max_size={max_size!r}")
    if min_size is None:
        min_size = 0
    length = draw(integers(min_value=min_size, max_value=max_size))
    return [EmptyMention(i) for i in range(length)]


@composite
def entitieses(draw, min_size=None, max_size=None, min_to_discard=None,
               max_to_discard=None):
    """

    An Entities object consisting only of EmptyMention objects with different
    ids.

    To generate more interesting scenarios, a number of Entity objects are
    discarded immediately after creation.

    There is no guarantee that Entities objects with the required size can be
    generated.

    :param min_size:        minimum length of Entities object
    :param max_size:        maximum length of Entities object
    :param min_to_discard:  minimum number of Entity objects to discard
    :param max_to_discard:  maximum number of Entity objects to discard
    """
    if min_size is None:
        min_size = 0
    if min_to_discard is None:
        min_to_discard = 0
    if min_to_discard < 0:
        raise ValueError(
            f"`min_to_discard` must be non-negative. Got: {min_to_discard}")
    if max_to_discard is not None and max_to_discard < min_to_discard:
        raise ValueError(
            "`max_to_discard` should be at least `min_to_discard`."
            f" Got: min_to_discard={min_to_discard!r},"
            f" max_to_discard={max_to_discard!r}")
    min_mentions = min_size + min_to_discard
    if min_mentions > MAX_PARTITIONABLE_NUMBER:
        raise ValueError(
            "The number of mentions needed to adhere to the requested"
            " `min_size` and `min_to_discard` exceeds the highest number of"
            " which I can calculate the possible partitions. Please choose"
            " `min_size` and `min_to_discard` s.t. their sum is at most"
            f" {MAX_PARTITIONABLE_NUMBER!r}. Got: min_size={min_size!r},"
            f" min_to_discard={min_to_discard!r}"
        )
    mentions = lists_of_unique_mentions(
        min_size=min_mentions,
        max_size=MAX_PARTITIONABLE_NUMBER
    )

    # If there is no `max_to_discard`, there is no maximal partition size,
    # because we can discard as much as we like to adhere to `max_size`.
    # If there is no `max_size`, there isn't a maximal partition size either,
    # because we simply don't care.
    max_partition_size = None if (max_to_discard is None or max_size is None) \
        else max_size + max_to_discard
    # logger.debug(f"min_size={min_size}")
    # logger.debug(f"max_size={max_size}")
    # logger.debug(f"min_to_discard={min_to_discard}")
    # logger.debug(f"max_to_discard={max_to_discard}")
    # logger.debug(f"max_partition_size={max_partition_size}")
    partition = draw(partitions(
        mentions,
        min_size=min_mentions,
        max_size=max_partition_size,
    ))
    entities = Entities(map(Entity, partition))
    # logger.debug(f"Entities before discarding: {entities!r}")

    # Make it a more interesting case by randomly discarding some entities.
    if max_size is not None:
        # Make sure to remove enough to adhere to `max_size`
        min_to_discard = max((min_to_discard, len(entities) - max_size))
    if max_to_discard is None:
        max_to_discard = len(entities)
    # Make sure not to remove too much, to adhere to `min_size`
    max_to_discard = min((max_to_discard, len(entities) - min_size))
    assert min_to_discard <= max_to_discard  # Just to be safe

    n_to_discard = draw(integers(
        min_value=min_to_discard, max_value=max_to_discard))
    # logger.debug(f"n_to_discard: {n_to_discard}")

    to_discard = draw(randoms()).sample(list(entities), k=n_to_discard)
    for e in to_discard:
        entities.remove(e)

    # logger.debug(f"Entities after discarding: {entities!r}")

    return entities


@given(data())
def test_empty_entitieses(data):
    entities = data.draw(entitieses(max_size=0, max_to_discard=0))
    assert len(entities) == 0


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(data(), integers(min_value=1, max_value=MAX_PARTITIONABLE_NUMBER),
       integers(min_value=0))
def test_entitieses(caplog, data, length, n_to_discard):
    if MAX_PARTITIONABLE_NUMBER == length:
        n_to_discard = 0
    else:
        n_to_discard %= MAX_PARTITIONABLE_NUMBER - length
    caplog.set_level('DEBUG')
    # logger.debug("\n\nNew Test\n\n\n\n\n")

    def draw_entitieses(label, *args, **kwargs):
        return data.draw(entitieses(*args, **kwargs), label=label)

    assert len(draw_entitieses('length', min_size=length, max_size=length)) \
        == length

    assert len(draw_entitieses(
            'length',
            min_size=length,
            max_size=length,
            min_to_discard=n_to_discard,
            max_to_discard=n_to_discard
        )) == length


@given(text())
def test_empty_mention(mid):
    assert len(EmptyMention.unique((EmptyMention(mid), EmptyMention(mid)))) \
        == 1


@given(lists(mentions()))
def test_from_mentions(mentions):
    if len(mentions) == len(EmptyMention.unique(mentions)):
        entities = Entities.from_mentions(mentions)

        # Stuff is put into a list because "x in list" also holds for copies of
        # x, while that's not the case for Entities
        entity_list = list(entities)
        for mention in mentions:
            assert Entity([mention]) in entity_list

        assert mentions == list(
            map(itemgetter(0), map(attrgetter('mentions'), entities)))
    else:
        with pytest.raises(ValueError):
            Entities.from_mentions(mentions)


@pytest.mark.xfail(error=SyntaxError, reason="One of the arguments of"
                   " Entities is a filter function. As of now they do not have"
                   " a `repr` that can be `eval`ed.")
@settings(verbosity=Verbosity.quiet)  # Tell hypothesis to shut up
@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses())
def test_repr(entities):
    assert entities == eval(repr(entities))


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses())
def test_containment(entities):
    for entity in entities:
        assert entity in entities


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses())
def test_length(entities):
    assert ilen(entities) == len(entities)


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses())
def test_reversed(entities):
    assert list(reversed(entities)) == list(reversed(list(entities)))


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses())
def test_clear_disjointness_constraints(entities):
    entities.clear_disjointness_constraints()
    assert 0 == len(entities.disjoint_mentions)


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses())
def test_clear_entities(entities):
    entities.clear_entities()
    assert 0 == len(entities)


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses())
def test_clear_all(entities):
    entities.clear_all()
    assert 0 == len(entities.disjoint_mentions)
    assert 0 == len(entities)


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses())
def test_add(entities):
    new_entities = Entities(())
    for entity in reversed(entities):
        new_entities.add(entity)
    assert list(entities) == list(reversed(new_entities))


@given(entitieses(), randoms())
def test_remove(entities, random):
    # For some random order, try removing all entities one by one
    entities_in_random_order = random.sample(list(entities), k=len(entities))
    total_min_1 = len(entities) - 1
    for i, entity in enumerate(entities_in_random_order):
        entities.remove(entity)
        assert len(entities) == total_min_1 - i
    assert len(entities) == 0
    assert len(list(entities)) == 0


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses())
def test_discard_ignores(entities):
    not_there = 'Not in there'
    assert not_there not in entities
    entities.discard(not_there)


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses(min_size=1), randoms())
def test_void_disjointness_constraints(entities, random):
    # Randomly choose an entity
    entity_sequence = list(entities)
    entity = random.choice(entity_sequence)

    # Randomly choose two mentions
    # choices allows the same mention to be chosen twice
    m1, m2 = random.choices(list(entity), k=2)

    # Some under the hood hacking
    entities.disjoint_mentions.add(frozenset((m1.id, m2.id)))

    assert not entities.disjointness_constraints_satisfied()


@pytest.mark.slow
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(entitieses(), randoms())
def test_adhered_disjointness_constraints(entities, random):
    # Mark everything that is already disjoint as disjoint, and check that it
    # doesn't break anything.
    # Some things will be marked disjoint twice. That should be okay.
    for an_entity in entities:
        for another_entity in entities:
            if an_entity is not another_entity:
                entities.mark_disjoint(an_entity, another_entity)
                assert entities.disjointness_constraints_satisfied()


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses(), randoms())
def test_mark_disjoint_same(entities, random):
    for entity in entities:
        with pytest.raises(ValueError):
            entities.mark_disjoint(entity, entity)


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses(min_size=1), randoms())
def test_merge(entities, random):
    # This should be more than enough to shrink entities
    iterations_left = (len(entities) + 2) ** 2
    while iterations_left and len(entities) > 1:
        iterations_left -= 1

        # Choose two random entities
        e1, e2 = random.choices(list(entities), k=2)

        # Merge them
        entities.merge(e1, e2)

        # Verify the result
        assert e1 in entities
        if e1 is not e2:
            assert e2 not in entities
        for m2 in e2:
            assert m2 in e1

    if not iterations_left:
        raise RuntimeError("This code seems to be in an infinite loop.")

    assert len(entities) == 1
    all_mentions = list(entities)[0].mentions
    assert len(all_mentions) == len(EmptyMention.unique(all_mentions))


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses(min_size=3), randoms())
def test_merge_foreign(entities, random):
    e1, e2, e3 = random.sample(list(entities), k=3)  # None should overlap

    entities.merge(e1, e2)

    # Merging again should be allowed
    entities.merge(e1, e2)

    # But not into e2
    with pytest.raises(ValueError):
        entities.merge(e2, e1)

    entities.remove(e1)

    # Now merging again isn't allowed at all!
    with pytest.raises(ValueError):
        entities.merge(e1, e2)

    # This should all still be fine
    entities.merge(e3, e1)
    entities.merge(e3, e2)


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses())
def test_all_merge_allowed(entities):
    for an_entity in entities:
        for another_entity in entities:
            assert entities.merge_allowed(an_entity, another_entity)


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses(min_size=2), randoms())
def test_merge_allowed(entities, random):
    # Randomly choose three entities, s.t. one is definitely different from
    # the other two.
    entity_sequence = list(entities)
    e1 = random.choice(entity_sequence)
    entity_sequence.remove(e1)
    e2, e3 = random.choices(entity_sequence, k=2)

    # Without constraints, anything should be allowed to merge
    assert entities.merge_allowed(e1, e2)

    # Only strictly different entities can be marked as disjoint
    entities.mark_disjoint(e1, e2)

    # With the constraints, they shouldn't be allowed to merge
    assert not entities.merge_allowed(e1, e2)

    entities.merge(e3, e2)
    assert not entities.merge_allowed(e1, e3)


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses(min_to_discard=10))
def test_entities_before(entities):
    for i, entity in enumerate(entities):
        before = list(entities.entities_before(entity))
        assert len(before) == i
        assert entity not in before


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses(min_to_discard=10))
def test_entity_sort_key(entities):
    assert sorted(entities, key=entities.entity_sort_key) == list(entities)


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses())
def test_self_not_candidate(entities):
    for entity in entities:
        assert entity not in entities.get_candidates(entity)


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses())
def test_maximum_candidates(entities):
    for entity in entities:
        assert list(entities.get_candidates(entity)) == \
            list(entities.entities_before(entity))


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses(min_size=2), randoms())
def test_no_unmergable_candidates(entities, random):
    # Randomly choose three entities, s.t. one is definitely different from
    # the other two.
    entity_sequence = list(entities)
    e1 = random.choice(entity_sequence)
    entity_sequence.remove(e1)
    e2, e3 = random.choices(entity_sequence, k=2)

    # Without constraints, anything should be allowed to merge
    assert entities.merge_allowed(e1, e2)
    assert e1 in entities.get_candidates(e2) or \
        e2 in entities.get_candidates(e1)

    # Only strictly different entities can be marked as disjoint
    entities.mark_disjoint(e1, e2)

    # With the constraints, they shouldn't be allowed to merge
    assert not entities.merge_allowed(e1, e2)

    # And the candidates for `e1` should not contain `e2`
    assert e1 not in entities.get_candidates(e2)
    assert e2 not in entities.get_candidates(e1)

    entities.merge(e3, e2)
    assert not entities.merge_allowed(e1, e3)
    assert e1 not in entities.get_candidates(e3)
    assert e3 not in entities.get_candidates(e1)


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses(min_size=1), integers())
def test_candidates_of_discarded(entities, index):
    index %= len(entities)
    entity = list(entities)[index]
    entities.remove(entity)
    with pytest.raises(ValueError):
        entities.get_candidates(entity)


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(entitieses())
def test_candidate_filter(entities):
    for entity in entities:
        assert ilen(entities.get_candidates(
            entity,
            entity_filter=lambda x: False)
        ) == 0
