class Entity:
    """
    A cluster of mentions that refer to the same concept.

    No promises are made about the order or uniqueness of mentions.

    Following multi-sieve coreference (Lee et al., 2013), an entity can be
    queried for any attribute that a mention has, and will return the set of
    their values.

    If some of the mentions have an attribute that others don't, Entity will
    quietly exclude the mentions that don't have the attribute and return the
    set of values for the mentions that do have it.
    """

    def __init__(self, mentions):
        self.mentions = list(mentions)
        if not self.mentions:
            raise ValueError("An Entity must consist of at least one Mention.")

    def __repr__(self):
        return self.__class__.__name__ + f"({self.mentions!r})"

    def __str__(self):
        return self.__class__.__name__ + f"({[m.id for m in self.mentions]!r})"

    def __eq__(self, other):
        return isinstance(other, Entity) and self.mentions == other.mentions

    def __iter__(self):
        return iter(self.mentions)

    def __contains__(self, mention):
        return mention in self.mentions

    def _merge(self, entity):
        """
        Merge a given Entity into this one.

        No attention is paid to whether any mention in `entity` is already in
        this one. Consequently, this Entity may contain duplicates after
        merging.

        If you are thinking of using this function, you probably want to use
        `Entities.merge` instead.
        """
        # Prevent infinite extension
        if entity.mentions is not self.mentions:
            self.mentions.extend(entity)

    def non_unique_mention_attr(self, attr):
        """
        Get a list of mention attribute values

        Crudely: `[getattr(mention, attr) for mention in self]`

        Raise AttributeError if none of the mentions contained in the entity
        have the requested attribute.

        If at least one mention has the requested attribute, quietly leave out
        the mentions that don't.
        """
        # Try to get all answers
        all_answers = [
            getattr(m, attr) for m in self if hasattr(m, attr)
        ]
        if not all_answers:
            raise AttributeError(
                f"None of the mentions have the attribute {attr!r}")
        return all_answers

    def mention_attr(self, attr):
        """
        Get the set of the values returned by `self.non_unique_mention_attr`

        Crudely: `{getattr(mention, attr) for mention in self}`

        Raise AttributeError if none of the mentions contained in the entity
        have the requested attribute.

        If at least one mention has the requested attribute, quietly leave out
        the mentions that don't.
        """
        return set(self.non_unique_mention_attr(attr))

    def flat_mention_attr(self, attr):
        """
        Get the union of the values returned by `self.non_unique_mention_attr`

        Crudely: `{elem for itr in self.mention_attr(att) for elem in itr}`

        Useful if the value is an iterable for every mention

        Raise AttributeError if none of the mentions contained in the entity
        have the requested attribute.

        If at least one mention has the requested attribute, quietly leave out
        the mentions that don't.
        """
        return {
            elem
            for itr in self.non_unique_mention_attr(attr)
            for elem in itr
        }
