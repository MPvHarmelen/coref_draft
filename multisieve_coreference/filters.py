"""
Single Mention or single Entity filters.

All filters are defined on the Mention level, and lifted to the Entity level
by having `some_filter(entity) := any(some_filter(m) for m in entity)`.
"""
from functools import singledispatch
from .entity import Entity

# FIXME: tool specific output
NOMINAL_POSES = {'name', 'noun'}
CORRECT_TYPES = {
    'PER',  # person
    'ORG',  # organisation
    'LOC',  # location
    'MISC'  # miscellaneous
}


@singledispatch
def is_nominal(mention):
    return mention.head_pos in NOMINAL_POSES


@singledispatch
def is_named_entity(mention):
    """
    If `entity_type` is not None, this was a named mention.
    """
    return mention.entity_type is not None


@singledispatch
def is_proper_noun(mention):
    return mention.entity_type in CORRECT_TYPES


@singledispatch
def is_pronoun(mention):
    return mention.head_pos == 'pron'


# Make everything work on the Entity level too!
for func in [is_nominal, is_named_entity, is_proper_noun, is_pronoun]:
    @func.register(Entity)
    def _(entity):
        return any(map(func, entity))
