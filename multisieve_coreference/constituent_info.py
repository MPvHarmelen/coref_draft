from collections import defaultdict

from . import constituents as csts
from .constituents import get_constituent


class Constituent:
    '''
    This class contains the main constructional information of mentions
    '''

    def __init__(self, head_id, span=None, multiword=None, modifiers=None,
                 appositives=None, predicatives=None):
        '''
        Constructor for the Constituent object.

        If None, the following arguments are automatically generated using
        `head_id`:
            - `span`
            - `multiword`
            - `modifiers`
            - `appositives`
            - `predicatives`
        '''
        self.head_id = head_id
        self.span = get_constituent(head_id) if span is None else span

        # Set the default values for `multiword`, `modifiers` and `appositives`
        self.multiword = get_multiword_expressions(self.head_id) \
            if multiword is None \
            else multiword
        self.modifiers = get_modifiers(self.head_id) \
            if modifiers is None \
            else modifiers
        self.appositives = get_appositives(self.head_id) \
            if appositives is None \
            else appositives

        # Override the default if something different was passed
        if multiword is not None:
            self.multiword = multiword
        if modifiers is not None:
            self.modifiers = modifiers
        if appositives is not None:
            self.appositives = appositives

        if predicatives is None:
            self.predicatives = []
            self._add_predicative_information()
        else:
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

    def add_predicative(self, pred):

        self.predicatives.append(pred)

    def _add_predicative_information(self):
        '''
        Function that checks if mention is subject in a predicative structure
        and, if so, adds predicative info to constituent object
        '''

        for headID, headrel in csts.dep2heads.get(self.head_id, []):
            if headrel == 'hd/su':
                headscomps = csts.head2deps.get(headID)
                for depID, deprel in headscomps:
                    if deprel in ['hd/predc', 'hd/predm']:
                        predicative = get_constituent(depID)
                        self.add_predicative(predicative)


def get_multiword_expressions(head_id):
    return [
        ID
        for ID, relation in csts.head2deps.get(head_id, [])
        if relation == 'mwp/mwp'
    ]


def get_modifiers(head_id):
    return [
        get_constituent(ID)
        for ID, relation in csts.head2deps.get(head_id, [])
        if relation == 'hd/mod'
    ]


def get_appositives(head_id):
    return [
        get_constituent(ID)
        for ID, relation in csts.head2deps.get(head_id, [])
        if relation == 'hd/app'
    ]


def get_named_entities(nafobj):
    '''
    Function that runs to entity layer and registers named entities

    :param nafobj: the input nafobject
    :return:       a list of (type, entity)-pairs
    '''
    # For administration purposes, spans will point to (type, entity)-pairs.
    # In the end, we'll just return a list of entities.
    entities = dict()

    for entity in nafobj.get_entities():
        etype = entity.get_type()
        for ref in entity.get_references():
            span = ref.get_span().get_span_ids()
            constituent = Constituent(
                find_head_in_span(span),
                multiword=span
            )
            # Check uniqueness of the entity span
            # bug in cltl-spotlight; does not check whether entity has already
            # been found
            span = frozenset(span)
            # If this span is smaller than or equal to some existing span,
            # this entity can be ignored
            if any(span <= other_span for other_span in entities.keys()):
                continue
            else:
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


def find_head_in_span(span):
    '''
    Find the first term in the `span` that is the head of a constituent that
    contains the whole `span`.

    If no such term exists, `find_closest_to_head` is used as fallback.

    :param span:    list of term identifiers
    :return:        term identifier of head
    '''

    head_term = None
    for term in span:
        constituent = get_constituent(term)
        if set(span) < constituent:
            if head_term is None:
                head_term = term
        #    else:
        #        print('span has more than one head')
    if head_term is None:
        head_term = find_closest_to_head(span)
    return head_term


def find_closest_to_head(span):
    """
    Find the term that heads the most terms in `span`.

    If there is a tie, the term occurring first is taken.
    """
    if len(span) == 1:
        return span[0]

    head_term_candidates = defaultdict(list)

    for tid in span:
        if tid in csts.head2deps:
            count = 0
            for deprel in csts.head2deps:
                if deprel[0] in span:
                    count += 1
            head_term_candidates[count].append(tid)
    if len(head_term_candidates) > 0:
        max_deps = sorted(head_term_candidates.keys())[-1]
        best_candidates = head_term_candidates.get(max_deps)
        if len(best_candidates) > 0:
            return best_candidates[0]

    return span[0]
