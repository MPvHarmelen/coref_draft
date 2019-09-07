"""
This module parses the term layer of a KAF/NAF object
"""
from __future__ import print_function
import os
import logging

from collections import OrderedDict

from .naf_info import get_pos_of_term
from .constituent_info import get_named_entities, Constituent
from .offset_info import (
    convert_term_ids_to_offsets,
    get_offset,
    get_offsets_from_span,
)


logger = logging.getLogger(None if __name__ == '__main__' else __name__)


def get_relevant_head_ids(nafobj):
    '''
    Get a list of term ids that head potential mentions
    :param nafobj: input nafobj
    :return: list of term ids (string)
    '''

    nominal_pos = ['noun', 'pron', 'name']
    mention_heads = []
    for term in nafobj.get_terms():
        pos_tag = term.get_pos()
        # check if possessive pronoun
        if pos_tag in nominal_pos or \
           pos_tag == 'det' and 'VNW(bez' in term.get_morphofeat():
            mention_heads.append(term.get_id())

    return mention_heads


def get_mention_constituents(nafobj):
    '''
    Function explores various layers of nafobj and retrieves all mentions
    possibly referring to an entity

    :param nafobj:  input nafobj
    :return:        dictionary of head term with as value constituent object
    '''
    mention_heads = get_relevant_head_ids(nafobj)

    logger.debug("Mention candidate heads: {!r}".format(mention_heads))

    mention_constituents = [Constituent(head) for head in mention_heads]

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug("Mention candidate constituents: {}".format('\n'.join(
            map('{!r}'.format, mention_constituents)
        )))

    return mention_constituents


def read_stopword_set(language):
    """
    Read a list of stopwords for the given language from the `resources`
    directory that ships with this package.

    :param lang:    language tag in accordance with [RFC5646][]
    :return:        a list of stopwords

    [RFC5646]: https://tools.ietf.org/html/rfc5646#section-2.2
    """

    resources = os.path.abspath(os.path.join(
        os.path.dirname(__file__),
        "resources"
    ))

    stopfilename = os.path.join(resources, language, 'stopwords.txt')

    with open(stopfilename, 'r') as stopfile:
        return {line.rstrip() for line in stopfile}


def merge_two_mentions(mention1, mention2):
    '''
    Merge information from mention 1 into mention 2
    :param mention1:
    :param mention2:
    :return: updated mention
    '''
    # FIXME; The comments here do not correspond to the code and therefore the
    #        code may be horribly wrong.
    if mention1.head_offset == mention2.head_offset:
        if set(mention1.span) == set(mention2.span):
            # if mention1 does not have entity type, take the one from entity 2
            if mention2.entity_type is None:
                mention2.entity_type = mention1.entity_type
        else:
            # if mention2 has no entity type, it's span is syntax based
            # (rather than from the NERC module)
            if mention1.entity_type is None:
                mention2.span = mention1.span
    else:
        if mention1.entity_type is None:
            mention2.head_offset = mention1.head_offset
        else:
            mention2.entity_type = mention1.entity_type

    return mention2


def merge_mentions(mentions):
    '''
    Merge mentions that have an identical span or head.

    Keeps the position of the earliest duplicate mention.

    :param mentions: (possibly ordered) {id: mention} dictionary
    :return:         (possibly ordered) {id: mention} dictionary
    '''

    final_mentions = type(mentions)()

    # TODO: create merge function and merge identical candidates
    # TODO: This code is O(m**2), but it shouldn't have to be, because we can
    #       use the ordering of mentions that came from different sources.

    for m, val in mentions.items():
        for prevm, preval in final_mentions.items():
            if val.head_offset == preval.head_offset or \
               set(val.span) == set(preval.span):
                updated_mention = merge_two_mentions(val, preval)
                final_mentions[prevm] = updated_mention
                break
        else:
            final_mentions[m] = val

    return final_mentions


def get_mentions(nafobj, language):
    '''
    Function that creates mention objects based on mentions retrieved from NAF
    :param nafobj: input naf
    :return: list of Mention objects
    '''

    stopwords = read_stopword_set(language)

    mentions = OrderedDict()
    for constituent in get_mention_constituents(nafobj):
        mid = 'm' + str(len(mentions))
        mentions[mid] = Mention.from_naf(
            nafobj, stopwords, constituent, id=mid)

    for entity_type, constituent in get_named_entities(nafobj):
        mid = 'm' + str(len(mentions))
        mentions[mid] = Mention.from_naf(
            nafobj, stopwords, constituent, id=mid,
            entity_type=entity_type)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        from .util import view_mentions
        logger.debug(
            "Mentions before merging: {}".format(
                view_mentions(nafobj, mentions))
        )

    mentions = merge_mentions(mentions)

    return mentions


class Mention:
    '''
    This class covers information about mentions that is relevant for
    coreference resolution.

    `span` and other things store _offsets_.

    All attributes must contain hashable values.
    '''

    # FIXME: begin and end offset are required arguments because the end_offset
    #        is not necessarily the last offset in the span, as the offsets may
    #        be more fine grained than the term level.
    #        Although AFAIK no term will exist with an offset strictly between
    #        span[-1] and end_offset + 1, apparently Antske thought it
    #        worthwhile to write `get_offsets_from_span` to exactly calculate
    #        the offset of the **end** of the last term, instead of just using
    #        the offset of the **start** of the last term.
    #        Someone should try what happens when this last option is used.
    def __init__(
            self,
            id,
            span,
            relaxed_span=(),
            full_head=(),
            head_offset=None,
            begin_offset=None,
            end_offset=None,
            head_pos=None,
            number=None,
            gender=None,
            person=None,
            entity_type=None,
            is_relative_pronoun=False,
            is_reflexive_pronoun=False,
            coreference_prohibited=None,
            modifiers=(),
            appositives=(),
            predicatives=(),
            non_stopwords=(),
            main_modifiers=(),
            sentence_number=(),
            ):
        '''
        Constructor of the mention
        #TODO: revise so that provides information needed for some sieve;
        #STEP 1: sieve 3 needs option to remove post-head modifiers

        :type span:                    tuple
        :type relaxed_span:            tuple
        :type full_head:               tuple
        :type head_offset:             int
        :type begin_offset:            int
        :type end_offset:              int
        :type head_pos:                str
        :type number:                  str
        :type gender:                  str
        :type person:                  str
        :type entity_type:             str
        :type is_relative_pronoun:     bool
        :type is_reflexive_pronoun:    bool
        :type coreference_prohibited:  list
        :type modifiers:               tuple
        :type appositives:             tuple
        :type predicatives:            tuple
        :type non_stopwords:           tuple
        :type main_modifiers:          tuple
        :type sentence_number:         int
        '''

        self.id = id   # confirmed
        self.span = tuple(span)

        self.full_head = full_head
        self.relaxed_span = relaxed_span

        self.head_offset = head_offset
        self.begin_offset = begin_offset
        self.end_offset = end_offset

        self.head_pos = head_pos

        self.sentence_number = sentence_number

        self.non_stopwords = non_stopwords

        self.coreference_prohibited = [] if coreference_prohibited is None \
            else list(coreference_prohibited)

        self.modifiers = modifiers
        self.main_modifiers = main_modifiers
        self.appositives = appositives
        self.predicatives = predicatives

        self.number = number
        self.gender = gender
        self.person = person
        self.entity_type = entity_type

        self.is_relative_pronoun = is_relative_pronoun
        self.is_reflexive_pronoun = is_reflexive_pronoun

    def __repr__(self):
        return self.__class__.__name__ + '(' + \
            'id={self.id!r}, ' \
            'span={self.span!r}, ' \
            'relaxed_span={self.relaxed_span!r}, ' \
            'full_head={self.full_head!r}, ' \
            'head_offset={self.head_offset!r}, ' \
            'begin_offset={self.begin_offset!r}, ' \
            'end_offset={self.end_offset!r}, ' \
            'head_pos={self.head_pos!r}, ' \
            'number={self.number!r}, ' \
            'gender={self.gender!r}, ' \
            'person={self.person!r}, ' \
            'entity_type={self.entity_type!r}, ' \
            'is_relative_pronoun={self.is_relative_pronoun!r}, ' \
            'is_reflexive_pronoun={self.is_reflexive_pronoun!r}, ' \
            'coreference_prohibited={self.coreference_prohibited!r}, ' \
            'modifiers={self.modifiers!r}, ' \
            'appositives={self.appositives!r}, ' \
            'predicatives={self.predicatives!r}, ' \
            'non_stopwords={self.non_stopwords!r}, ' \
            'main_modifiers={self.main_modifiers!r}, ' \
            'sentence_number={self.sentence_number!r}, ' \
            ')'.format(self=self)

    def fill_gaps(self, full_content, allow_adding=lambda _: True):
        """
        Find and fill gaps in the span of this mention.

        :param full_content:  list of things in spans for the whole document
        :param allow_adding:  (offset) -> bool function deciding whether a
                              missing term may be added or the gap should be
                              left as is.
        """
        if len(self.span) >= 2:
            start = full_content.index(self.span[0])
            end = full_content.index(self.span[-1], start)
            self.span = tuple(full_content[start:end + 1])

    @classmethod
    def from_naf(cls, nafobj, stopwords, constituent_info, **kwargs):
        '''
        Create a mention object from naf information

        :param nafobj:              the input naffile
        :param constituent_info:    information about the constituent
        :param head:                the id of the constituent's head
        :param mid:                 the mid (for creating a unique mention id
        :return:                    a `Mention` object
        '''

        head_offset = get_offset(nafobj, constituent_info.head_id)

        span_ids = constituent_info.span
        span_offsets = convert_term_ids_to_offsets(nafobj, span_ids)
        begin_offset, end_offset = get_offsets_from_span(nafobj, span_ids)

        # get POS of head
        head_pos = get_pos_of_term(nafobj, constituent_info.head_id)

        # modifiers and appositives:
        modifiers, appositives = [], []

        relaxed_span = list(span_offsets)
        for mod_in_tids in constituent_info.modifiers:
            mod_span = convert_term_ids_to_offsets(nafobj, mod_in_tids)
            modifiers.append(mod_span)
            for mid in mod_span:
                if mid > head_offset and mid in relaxed_span:
                    relaxed_span.remove(mid)

        for app_in_tids in constituent_info.appositives:
            app_span = convert_term_ids_to_offsets(nafobj, app_in_tids)
            appositives.append(app_span)
            for mid in app_span:
                if mid > head_offset and mid in relaxed_span:
                    relaxed_span.remove(mid)

        extra_kwargs = {}
        if head_pos in ['pron', 'noun', 'name']:
            extra_kwargs['person'], \
                extra_kwargs['gender'], \
                extra_kwargs['number'], \
                extra_kwargs['is_relative_pronoun'], \
                extra_kwargs['is_reflexive_pronoun'] = \
                analyze_nominal_information(nafobj, constituent_info.head_id)

        extra_kwargs.update(kwargs)

        mention = cls(
            span=span_offsets,
            relaxed_span=relaxed_span,
            full_head=convert_term_ids_to_offsets(
                nafobj, constituent_info.multiword),
            head_offset=head_offset,
            begin_offset=begin_offset,
            end_offset=end_offset,
            head_pos=head_pos,
            modifiers=modifiers,
            appositives=appositives,
            predicatives=[
                convert_term_ids_to_offsets(nafobj, pred_ids)
                for pred_ids in constituent_info.predicatives
            ],
            non_stopwords=get_non_stopwords(nafobj, stopwords, span_ids),
            main_modifiers=get_main_modifiers(nafobj, span_ids),
            sentence_number=get_sentence_number(
                nafobj, constituent_info.head_id),
            **extra_kwargs
        )

        return mention


def get_main_modifiers(nafobj, span):
    '''
    Function that creates list of all modifiers that are noun or adjective
    (possibly including head itself)

    :param nafobj:  input naf
    :param span:    list of term ids
    :return:        list of offsets of main modifiers
    '''

    main_mods = []
    for tid in span:
        term = nafobj.get_term(tid)
        if term.get_pos() in ['adj', 'noun']:
            main_mods.append(tid)

    return convert_term_ids_to_offsets(nafobj, main_mods)


def get_non_stopwords(nafobj, stopwords, span):
    '''
    Function that verifies which terms in span are not stopwords and adds these
    to non-stopword list

    :param nafobj: input naf (for linguistic information)
    :param span: list of term ids
    :param mention: mention object
    :return:
    '''
    non_stop_terms = []

    for tid in span:
        my_term = nafobj.get_term(tid)
        if not my_term.get_type() == 'closed' and \
           not my_term.get_lemma().lower() in stopwords:
            non_stop_terms.append(tid)

    return convert_term_ids_to_offsets(nafobj, non_stop_terms)


def analyze_nominal_information(nafobj, term_id):

    term = nafobj.get_term(term_id)
    morphofeat = term.get_morphofeat()
    return (
        identify_person(morphofeat),
        identify_gender(morphofeat),
        identify_number(morphofeat, term),
        is_relative_pronoun(morphofeat),
        is_reflexive_pronoun(morphofeat),
    )


def get_sentence_number(nafobj, head):

    myterm = nafobj.get_term(head)
    tokid = myterm.get_span().get_span_ids()[0]
    mytoken = nafobj.get_token(tokid)
    sent_nr = int(mytoken.get_sent())

    return sent_nr


def identify_person(morphofeat):
    if '1' in morphofeat:
        return '1'
    elif '2' in morphofeat:
        return '2'
    elif '3' in morphofeat:
        return '3'


def identify_number(morphofeat, myterm):
    if 'ev' in morphofeat:
        return 'ev'
    elif 'mv' in morphofeat:
        return 'mv'
    elif 'getal' in morphofeat:
        lemma = myterm.get_lemma()
        if lemma in ['haar', 'zijn', 'mijn', 'jouw', 'je']:
            return 'ev'
        elif lemma in ['ons', 'jullie', 'hun']:
            return 'mv'


def identify_gender(morphofeat):
    if 'fem' in morphofeat:
        return 'fem'
    elif 'masc' in morphofeat:
        return 'masc'
    elif 'onz,' in morphofeat:      # FIXME: Should this comma be here?
        return 'neut'


def is_relative_pronoun(morphofeat):
    return 'betr,' in morphofeat    # FIXME: Should this comma be here?


def is_reflexive_pronoun(morphofeat):
    return 'refl,' in morphofeat    # FIXME: Should this comma be here?
