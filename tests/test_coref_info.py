from math import factorial
import itertools as it

import pytest
from hypothesis import given, assume, note, event, settings, HealthCheck
from hypothesis.strategies import (
    dictionaries,
    text,
    lists,
    sets,
    frozensets,
    integers,
    sampled_from,
    composite,
    randoms
)

from multisieve_coreference.coref_info import (
    merge_keys,
    CoreferenceInformation
)

MAX_TEXT_SIZE = 30


def ncr(n, r):
    if n < r:
        return 0
    r = min(r, n-r)
    return factorial(n) // factorial(r) // factorial(n-r)


@composite
def dicts_and_key_sets(draw, *args, **kwargs):
    dic = draw(dictionaries(*args, **kwargs))
    if dic:
        key_sets = draw(sets(frozensets(sampled_from(sorted(dic)))))
    else:
        key_sets = set()
    return dic, key_sets


@given(
    dictionaries(
        text(max_size=MAX_TEXT_SIZE),
        sets(text(max_size=MAX_TEXT_SIZE))
    ),
    integers())
def test_repr(dic, start_id):
    info = CoreferenceInformation(dic, start_id)
    assert info == eval(repr(info))


@given(
    dictionaries(
        text(max_size=MAX_TEXT_SIZE),
        sets(text(max_size=MAX_TEXT_SIZE))
    ))
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_merge_keys_fully_random_dicts(indic):
    orig_keys = list(indic)
    orig_values = set(it.chain.from_iterable(indic.values()))
    keymap = merge_keys(indic, (orig_keys,))
    assert len(orig_keys) == 0 or len(indic) == 1
    assert len(orig_keys) == 0 or orig_values == indic[next(iter(indic))]
    for key in orig_keys:
        assert key in indic or (key in keymap and keymap[key] in orig_keys)


@pytest.mark.slow
@given(
    dictionaries(
        text(max_size=MAX_TEXT_SIZE),
        sets(text(max_size=MAX_TEXT_SIZE)),
        max_size=100
    ),
    integers())
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_merge_keys_pointwise_random_dicts(indic, combinations):
    if indic:
        combinations %= len(indic)
    else:
        combinations = 1
    orig_keys = list(indic)
    orig_values = set(it.chain.from_iterable(indic.values()))
    orig_dic = {k: set(v) for k, v in indic.items()}    # deep copy
    keymap = merge_keys(
        indic,
        it.combinations(orig_keys, combinations)
    )
    if combinations == 0 or combinations == 1 or len(orig_keys) == 0:
        # Nothing should have happened
        assert indic == orig_dic
    else:
        # Everything should have been merged
        assert len(indic) == 1
        assert orig_values == indic[next(iter(indic))]

    for key in orig_keys:
        assert key in indic or (key in keymap and keymap[key] in orig_keys)
        assert orig_dic[key] <= indic[keymap.get(key, key)]


@given(
    dicts_and_key_sets(
        text(max_size=MAX_TEXT_SIZE),
        sets(text(max_size=MAX_TEXT_SIZE))
    ))
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_merge_keys_pointwise_selectively_random_dicts(dic_and_sets):
    indic, key_sets = dic_and_sets
    orig_dic = {k: set(v) for k, v in indic.items()}    # deep copy
    keymap = merge_keys(indic, key_sets)

    # Check whether the orig_dic, key_sets pair makes sense, i.e.
    # Check whether anything being in a key_set indeed means orig_dic is not
    # empty
    assert not any(key_sets) or orig_dic
    for key in orig_dic:
        assert key in indic or (key in keymap and keymap[key] in orig_dic)
        assert orig_dic[key] <= indic[keymap.get(key, key)]
    event("Final length dictionary: {}".format(len(indic)))


@given(
    dictionaries(
        text(max_size=MAX_TEXT_SIZE),
        sets(text(max_size=MAX_TEXT_SIZE)),
    ),
    sets(frozensets(integers())))
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_merge_keys_bad_keys(indic, bad_keys):
    assume(any(bad_keys))
    with pytest.raises(KeyError):
        merge_keys(indic, bad_keys)


@given(
    dictionaries(
        text(max_size=MAX_TEXT_SIZE),
        sets(text(max_size=MAX_TEXT_SIZE))
    ),
    lists(lists(text(max_size=MAX_TEXT_SIZE))),
    randoms())
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_add_coref_class(indic, content, random):
    info = CoreferenceInformation(indic)
    for mentions in content:
        new_id = info.add_coref_class(mentions, True)
        assert new_id in info.coref_classes
    prev_len = len(info.coref_classes)
    infloopstop = len(info.coref_classes)
    while len(info.coref_classes) > 1:
        if not infloopstop:
            raise RuntimeError("This would have been an infinite loop!")
        ca, cb = random.sample(info.coref_classes.keys(), 2)
        if len(info.coref_classes[ca]) == 0:
            del info.coref_classes[ca]
            prev_len -= 1
            continue
        ma = random.choice(tuple(info.coref_classes[ca]))

        if len(info.coref_classes[cb]) == 0:
            del info.coref_classes[cb]
            prev_len -= 1
            continue
        mb = random.choice(tuple(info.coref_classes[cb]))
        two_things = [ma, mb]
        note("two_things: {}\nold info: {}".format(two_things, info))
        new_id = info.add_coref_class(two_things, True)
        note("new info: {}".format(info))
        new_len = len(info.coref_classes)
        assert prev_len > new_len
        prev_len = new_len
        assert new_id in info.coref_classes
        infloopstop -= 1
