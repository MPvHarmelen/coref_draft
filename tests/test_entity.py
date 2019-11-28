from copy import copy

import pytest

from multisieve_coreference.entity import Entity
from multisieve_coreference.mentions import Mention


HASHABLE_AND_ITERABLE_MENTION_ATTRIBUTES = [
    'span',
    'relaxed_span',
    'full_head',
    'non_stopwords',
]

ITERABLE__BUT_NOT_HASHABLE_MENTION_ATTRIBUTES = [
    'modifiers',
    'appositives',
    'predicatives',
    'main_modifiers',
    # 'coreference_prohibited',
]

SINGLETON_MENTION_ATTRIBUTES = [
        'head_offset',
        'begin_offset',
        'end_offset',
        'head_pos',
        'number',
        'gender',
        'person',
        'entity_type',
        'is_relative_pronoun',
        'is_reflexive_pronoun',
        'sentence_number',
    ]


ITERABLE_MENTION_ATTRIBUTES = HASHABLE_AND_ITERABLE_MENTION_ATTRIBUTES + \
    ITERABLE__BUT_NOT_HASHABLE_MENTION_ATTRIBUTES


HASHABLE_MENTION_ATTRIBUTES = HASHABLE_AND_ITERABLE_MENTION_ATTRIBUTES + \
    SINGLETON_MENTION_ATTRIBUTES


ALL_MENTION_ATTRIBUTES = ITERABLE_MENTION_ATTRIBUTES + \
    SINGLETON_MENTION_ATTRIBUTES


@pytest.fixture
def some_mentions():
    return [
        Mention(id=1, span=(1, 2, 5), person='random'),
        Mention(id=3, span=(17, 23, 50), person='random'),
        Mention(id=2, span=(15, 16, 18), person='different'),
    ]


@pytest.fixture
def some_other_mentions():
    return [
        Mention(id=6, span=(7, 14, 16), person='another random'),
        Mention(id=8, span=(5, 8, 9), person='different'),
        Mention(id=7, span=(10, 12, 17), person='random'),
    ]


@pytest.fixture
def an_entity(some_mentions):
    return Entity(some_mentions)


@pytest.fixture
def another_entity(some_other_mentions):
    return Entity(some_other_mentions)


@pytest.mark.parametrize('attr', ALL_MENTION_ATTRIBUTES)
def test_non_unique_mention_attr(entity, attr):
    assert len(entity.non_unique_mention_attr(attr)) == \
        len(entity.mentions)


@pytest.mark.parametrize('attr', ALL_MENTION_ATTRIBUTES)
def test_non_unique_non_none_mention_attr(entity, attr):
    assert len(entity.non_unique_non_none_mention_attr(attr)) <= \
        len(entity.mentions)


@pytest.mark.parametrize('attr', HASHABLE_MENTION_ATTRIBUTES)
def test_mention_attr(entity, attr):
    unique = entity.mention_attr(attr)
    full = entity.non_unique_non_none_mention_attr(attr)
    assert 0 <= len(unique) <= len(full)
    assert set(full) == set(unique)


@pytest.mark.parametrize('attr', ITERABLE_MENTION_ATTRIBUTES)
def test_flat_mention_attr(entity, attr):
    flat = entity.flat_mention_attr(attr)
    assert {
        elem
        for iterable in entity.non_unique_non_none_mention_attr(attr)
        for elem in iterable
    } == flat


@pytest.mark.parametrize('method', [
    Entity.non_unique_mention_attr,
    Entity.non_unique_non_none_mention_attr,
    Entity.mention_attr,
    Entity.flat_mention_attr,
])
def test_non_unique_mention_attr_fails(entity, method):
    with pytest.raises(AttributeError):
        method(entity, 'blablablfoodoesnotexist')


@pytest.mark.xfail(reason="Equality of Entity is defined by equality of"
                   " Mention, which is badly defined.", error=AssertionError)
def test_repr(entity):
    assert entity == eval(repr(entity))


def test_merge(an_entity, another_entity):
    merged = copy(an_entity)
    merged._merge(another_entity)
    assert all(entity in merged for entity in an_entity)
    assert all(entity in merged for entity in another_entity)


@pytest.fixture(params=[
    pytest.lazy_fixture('an_entity'), pytest.lazy_fixture('another_entity')])
def entity(request):
    return request.param
