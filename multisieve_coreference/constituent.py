class Constituent:
    '''
    This class contains the main constructional information of mentions

    All the different spans contain term identifiers, not offsets.
    '''

    def __init__(self, head_id, span, multiword, modifiers, appositives,
                 predicatives=()):
        self.head_id = head_id
        self.span = span
        self.multiword = multiword
        self.modifiers = modifiers
        self.appositives = appositives
        self.predicatives = predicatives

    def __repr__(self):
        return self.__class__.__name__ + '(' \
            'head_id={self.head_id}, ' \
            'span={self.span}, ' \
            'multiword={self.multiword}, ' \
            'modifiers={self.modifiers}, ' \
            'appositives={self.appositives}, ' \
            'predicatives={self.predicatives}, ' \
            ')'.format(self=self)

    @classmethod
    def from_constituency_trees(cls, constituency_trees, head_id=None,
                                span=None, multiword=None, modifiers=None,
                                appositives=None, predicatives=None, **kwargs):
        """
        At least one of `head_id` or `span` must be not None.
        If the other is None, it's calculated from the one that isn't, with the
        use of `constituency_trees`.

        If None, the following arguments are automatically extracted from
        `constituency_trees`:
            - `multiword`
            - `modifiers`
            - `appositives`
            - `predicatives`
        """
        if head_id is None and span is None:
            raise TypeError(
                "At least one of `head_id` or `span` must be not None."
                f" Got: head_id={head_id!r} and span={span!r}.")
        if span is None:
            span = constituency_trees.get_constituent(head_id)
        elif head_id is None:
            head_id = constituency_trees.find_head_in_span(span)

        # Set default values
        if multiword is None or modifiers is None or appositives is None:
            multiword = cls.get_multiword_expressions(
                head_id,
                constituency_trees)

            modifiers = cls.get_modifiers(
                head_id,
                constituency_trees)

            appositives = cls.get_appositives(
                head_id,
                constituency_trees)

        if predicatives is None:
            predicatives = cls.get_predicative_information(
                head_id,
                constituency_trees)

        return cls(
            head_id=head_id,
            span=span,
            multiword=multiword,
            modifiers=modifiers,
            appositives=appositives,
            predicatives=predicatives,
            **kwargs
        )

    @staticmethod
    def get_multiword_expressions(head_id, constituency_trees):
        return tuple(
            ID
            for ID, relation in constituency_trees.head2deps.get(head_id, [])
            if relation == 'mwp/mwp'
        )

    @staticmethod
    def get_modifiers(head_id, constituency_trees):
        return tuple(
            constituency_trees.get_constituent(ID)
            for ID, relation in constituency_trees.head2deps.get(head_id, [])
            if relation == 'hd/mod'
        )

    @staticmethod
    def get_appositives(head_id, constituency_trees):
        return tuple(
            constituency_trees.get_constituent(ID)
            for ID, relation in constituency_trees.head2deps.get(head_id, [])
            if relation == 'hd/app'
        )

    @staticmethod
    def get_predicative_information(head_id, constituency_trees):
        subjects = (
            headID
            for headID, headrel in constituency_trees.dep2heads.get(
                    head_id, [])
            if headrel == 'hd/su'
        )
        return tuple(
            constituency_trees.get_constituent(depID)
            for headID in subjects
            for depID, deprel in constituency_trees.head2deps.get(headID)
            if deprel in ['hd/predc', 'hd/predm']
        )


def get_named_entities(nafobj, constituency_trees):
    '''
    Function that runs to entity layer and registers named entities

    :param nafobj: the input nafobject
    :return:       a list of (type, constituent)-pairs
    '''
    # For administration purposes, spans will point to (type, span)-pairs.
    # In the end, we'll just return a list of (type, span)-pairs.
    entities = dict()

    for entity in nafobj.get_entities():
        etype = entity.get_type()
        for ref in entity.get_references():
            span = ref.get_span().get_span_ids()
            # Check uniqueness of the entity span
            # bug in cltl-spotlight; does not check whether entity has already
            # been found
            span = frozenset(span)
            # If this span is smaller than or equal to some existing span,
            # this entity can be ignored
            if any(span <= other_span for other_span in entities.keys()):
                continue

            constituent = Constituent.from_constituency_trees(
                constituency_trees,
                span=tuple(span),
                multiword=tuple(span),
            )
            # If this span is larger than some existing span,
            # the existing entity should be replaced by this entity.
            # This is done by removing all entities that have smaller spans
            # and then adding this entity.
            to_delete = [
                other_span
                for other_span in entities
                if other_span < span
            ]
            for other_span in to_delete:
                del entities[other_span]
            entities[span] = (etype, constituent)

    return list(entities.values())
