import itertools as it
from collections import Counter

from .entity import Entity


class Entities:
    """
    A sorted collection of Entity objects that:

     - merges two Entity objects when requested to do so
     - keeps track of which Entity objects are not allowed to be merged
     - given an Entity and optionally a filter, provides an ordered selection
       of candidate antecedents. This selection always adheres to the
       non-coreference constraints.


    Note that `entity in entities` only holds when the exact object `entity`
    is part of `entities`. Thus `copy(entity) in entities` will never hold.


    !! NB !!    For keeping track of which Entity objects must not be merged,
                Entities makes heavy use of Mention ids (because Mention
                objects themselves are not hashable). If two distinct mentions
                have the same id, they are assumed to be equal, but will not
                necessarily end up in the same Entity if they didn't start
                there.


    ## Implementation details

    To make sure we only have to sort everything once, the order of Entity
    objects is remembered by saving all Entity objects in a list.

    To have O(1) deletion of Entity objects, their ids are stored in an
    {id: index} dictionary that keeps track of whether an Entity is still in
    this Entities object. When an Entity is removed, its index is popped from
    `_contained_entities` and the Entity is replaced by None in
    `_all_entities`.
    """

    def __init__(self, entities, disjoint_mentions=(), default_filter=None):
        """
        :param entities:            a sorted collection of entities
        :param default_filter:      filter to use for `get_candidates` when
                                    none is specified
        :param disjoint_mentions:   a collection of mention-id sets that must
                                    never be in the same Entity
        """
        self.overwrite_entities(entities)

        self.default_filter = lambda x: True if default_filter is None \
            else default_filter

        self.disjoint_mentions = set()
        for disjoint_set in disjoint_mentions:
            self.mark_disjoint(disjoint_set)

        if not self.disjointness_constraints_satisfied():
            raise ValueError(
                "Initial `entities` voids disjointness constraints specified"
                " by initial `disjoint_mentions`.")

    def __repr__(self):
        return self.__class__.__name__ + f'({list(self)!r}, ' \
            f'{self.disjoint_mentions}, {self.default_filter})'

    def __contains__(self, entity):
        return self._get_entity_key(entity) in self._contained_entities

    def __len__(self):
        return len(self._contained_entities)

    def __iter__(self, end=None, increment=None):
        """
        Iterate over all remaining Entity objects.

        :param end:     index with respect to self._all_entities to stop at
        """
        return filter(
            lambda x: x is not None,
            self._all_entities[:end:increment])

    def __reversed__(self):
        return self.__iter__(increment=-1)

    def _get_entity_key(self, entity):
        return id(entity)

    def entity_sort_key(self, entity):
        return self._contained_entities[self._get_entity_key(entity)]

    def entities_before(self, entity):
        return self.__iter__(
            end=self._contained_entities[self._get_entity_key(entity)])

    def overwrite_entities(self, entities):
        """
        Discard all Entity objects in this Entities object and use the ones
        from `entities` instead.
        """
        self._all_entities = list(entities)
        self._contained_entities = {
            self._get_entity_key(entity): index
            for index, entity in enumerate(self._all_entities)
        }

    def add(self, entity):
        """
        Add an Entity to the end of this Entities.

        If `entity` is already in Entities, do nothing.
        """
        if entity not in self:
            # We want the new length minus one as the index, which is the same
            # as the old length.
            self._contained_entities[self._get_entity_key(entity)] = \
                len(self._all_entities)
            self._all_entities.append(entity)

    def remove(self, entity):
        """
        Remove an Entity from this Entities.

        If `entity` was not in Entities, raise KeyError.
        """
        try:
            index = self._contained_entities.pop(self._get_entity_key(entity))
        except KeyError:
            raise KeyError(repr(entity))
        self._all_entities[index] = None

    def discard(self, entity):
        """
        Discard an Entity from this Entities.

        If `entity` was not in Entities, do nothing.
        """
        if entity in self:
            self.remove(entity)

    def clear_entities(self):
        """
        Clear all Entity objects from this Entities.
        """
        self.overwrite_entities(())

    def clear_disjointness_constraints(self):
        """
        Clear all disjointness constraints from this Entities.
        """
        self.disjoint_mentions.clear()

    def clear_all(self):
        """
        Clear all Entity objects and disjointness constraints.
        """
        self.clear_entities()
        self.clear_disjointness_constraints()

    def mark_disjoint(self, one, other):
        """
        Mark a pair of Entity objects as pairwise disjoint.

        Under the hood, this is done by marking all the following pairs as
        disjoint:
            (mention from first Entity, mention from second Entity)

        No attention is paid to whether the Entity objects are actually in
        this Entities object.
        """
        ones_mention_ids = one.mention_attr('id')
        others_mention_ids = other.mention_attr('id')
        ids_in_both = ones_mention_ids & others_mention_ids
        if ids_in_both:
            raise ValueError(
                "Marking the these Entity objects disjoint would mark the"
                " following mention ids as disjoint with themselves, which"
                " will break most of the functionality of Entities. Mentions"
                " that would have been marked as disjoint with themselves:"
                f" {ids_in_both!r}. Entities: {one!r}, {other!r}"
            )
        return self.disjoint_mentions.update(
            frozenset((one_m, other_m))
            for one_m in ones_mention_ids
            for other_m in others_mention_ids
        )

    def disjointness_constraints_satisfied(self, entities=None):
        """
        Verify whether the disjointness constraints described by
        `self.disjoint_mentions` hold for the given entities.

        If `entities is None`, all entities in `self` are used.

        In other words: check that no entity contains mentions `a` and `b` s.t.
        `frozenset(a.id, b.id) in self.disjoint_mentions`.

        Any (m.id, m.id) pair would invalidate any Entities object. So be
        careful not to mark a mention disjoint with itself!
        """
        if entities is None:
            entities = self
        return all(
            frozenset(pair) not in self.disjoint_mentions
            for pair in it.chain.from_iterable(
                # For every combination of mentions within an entity
                # (including reflexive combinations)
                it.product(entity.mention_attr('id'), repeat=2)
                for entity in entities
            ))

    def merge_allowed(self, one, other):
        """
        Check whether merging two Entity objects would void mention
        disjointness constraints.

        This is independent of whether each entity internally voids mention
        disjointness constraints.
        """
        return all(
            frozenset((one_m, other_m)) not in self.disjoint_mentions
            for one_m in one.mention_attr('id')
            for other_m in other.mention_attr('id')
        )

    def merge(self, entity_to_keep, other):
        """
        Merge two mentions, discarding `other` afterwards.

        The merge is done in place, i.e. the returned Entity is always
        `entity_to_keep`.

        Do not verify whether the merge would validate disjointness
        constraints.

        Discard other from `self.entities` and quietly accept Entity objects
        that aren't in self.entities.

        If `entity_to_keep` is exactly the same object as `other`, `other` is
        **not** discarded (because that would also mean discarding
        `entity_to_keep`).

        !! NB !! if `entity_to_keep` happens not to be in `self.entities`,
                 it is **not** added automatically.
        """
        if entity_to_keep not in self:
            raise ValueError(
                "I can only keep an Entity if it is already mine, but"
                f" {entity_to_keep!r} not in {self!r}")
        entity_to_keep.merge(other)
        if entity_to_keep is not other:
            self.discard(other)
        return entity_to_keep

    def get_candidates(self, entity, entity_filter=None):
        """
        Get all Entity objects occurring before `entity` that pass
        `entity_filter` and would not void mention disjointness constraints if
        merged with `entity`.

        If `entity_filter` is None, use `self.default_filter`.
        """
        if entity not in self:
            raise ValueError(
                "`entity` must be contained in this Entities to be able to get"
                f" its candidates. Got: entity={entity!r}, self={self!r}")
        if entity_filter is None:
            entity_filter = self.default_filter
        return (
            candidate
            for candidate in self.entities_before(entity)
            if entity_filter(candidate)     # This filter first, because..
            and self.merge_allowed(entity, candidate)   # this one is expensive
        )

    @classmethod
    def from_mentions(cls, mentions, **kwargs):
        """
        Initialise an Entities object with singleton Entity objects from a
        sorted collection of Mention objects with unique ids.
        """
        mentions = list(mentions)

        # Verify mention ids
        ids = Counter(m.id for m in mentions)
        if len(ids) != len(mentions):
            raise ValueError(
                "Some mentions have equal ids. Duplicate ids: " +
                ', '.join(it.starmap(
                    '{!r}: {!r}'.format,
                    it.takewhile(lambda l: l[1] > 1, ids.most_common())
                ))
            )

        return cls(entities=(Entity([m]) for m in mentions), **kwargs)
