"""
This module parses the term layer of a KAF/NAF object
"""
from __future__ import print_function
import os
import logging

from collections import OrderedDict

from .naf_info import get_pos_of_term
from .constituent_info import get_named_entities, get_constituents
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
    mention_constituents = get_constituents(mention_heads)
    if logger.getEffectiveLevel() <= logging.DEBUG:
        import itertools as it
        logger.debug("Mention candidate constituents: {}".format('\n'.join(
            it.starmap('{}: {!r}'.format, mention_constituents.items())
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
    Function that merges information from entity mentions
    :param mentions: dictionary mapping mention number to specific mention
    :return: list of mentions where identical spans are merged
    '''

    final_mentions = {}

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

    mention_constituents = get_mention_constituents(nafobj)
    mentions = OrderedDict()
    for head, constituent in mention_constituents.items():
        mid = 'm' + str(len(mentions))
        mention = Mention.from_naf(nafobj, stopwords, constituent, head, mid)
        mentions[mid] = mention

    entities = get_named_entities(nafobj)
    for entity, constituent in entities.items():
        mid = 'm' + str(len(mentions))
        mention = Mention.from_naf(nafobj, stopwords, constituent, entity, mid)
        mention.entity_type = constituent.etype
        mentions[mid] = mention

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
    '''

    def __init__(
            self,
            id,
            span,
            head_offset=None,
            head_pos=None,
            number='',
            gender='',
            person='',
            full_head=None,
            relaxed_span=None,
            entity_type=None,
            in_quotation=False,
            is_relative_pronoun=False,
            is_reflective_pronoun=False,
            coreference_prohibited=None,
            modifiers=None,
            appositives=None,
            predicatives=None,
            non_stopwords=None,
            main_modifiers=None,
            sentence_number='',
            ):
        '''
        Constructor of the mention
        #TODO: revise so that provides information needed for some sieve;
        #STEP 1: seive 3 needs option to remove post-head modifiers

        :type span:                    list
        :type head_offset:             int
        :type head_pos:                str
        :type number:                  str
        :type gender:                  str
        :type person:                  str
        :type full_head:               list
        :type relaxed_span:            list
        :type entity_type:             str
        :type in_quotation:            bool
        :type is_relative_pronoun:     bool
        :type is_reflective_pronoun:   bool
        :type coreference_prohibited:  list
        :type begin_offset:            str
        :type end_offset:              str
        :type modifiers:               list
        :type appositives:             list
        :type predicatives:            list
        :type non_stopwords:           list
        :type main_modifiers:          list
        :type sentence_number:         str
        '''

        self.id = id   # confirmed
        self.span = span
        self.head_offset = head_offset
        self.head_pos = head_pos

        self.full_head = [] if full_head is None else full_head

        self.begin_offset = self.span[0]
        self.end_offset = self.span[-1]
        self.sentence_number = sentence_number

        self.relaxed_span = [] if relaxed_span is None else relaxed_span
        self.non_stopwords = [] if non_stopwords is None else non_stopwords

        self.coreference_prohibited = [] if coreference_prohibited is None \
            else coreference_prohibited

        self.modifiers = [] if modifiers is None else modifiers
        self.main_modifiers = [] if main_modifiers is None else main_modifiers
        self.appositives = [] if appositives is None else appositives
        self.predicatives = [] if predicatives is None else predicatives

        self.number = number
        self.gender = gender
        self.person = person
        self.entity_type = entity_type

        self.in_quotation = in_quotation
        self.is_relative_pronoun = is_relative_pronoun
        self.is_reflective_pronoun = is_reflective_pronoun

    def __repr__(self):
        return self.__class__.__name__ + '(' + \
            'id={self.id!r}, ' \
            'span={self.span!r}, ' \
            'number={self.number!r}, ' \
            'gender={self.gender!r}, ' \
            'person={self.person!r}, ' \
            'head_offset={self.head_offset!r}, ' \
            'full_head={self.full_head!r}, ' \
            'head_pos={self.head_pos!r}, ' \
            'relaxed_span={self.relaxed_span!r}, ' \
            'entity_type={self.entity_type!r}, ' \
            'in_quotation={self.in_quotation!r}, ' \
            'is_relative_pronoun={self.is_relative_pronoun!r}, ' \
            'is_reflective_pronoun={self.is_reflective_pronoun!r}, ' \
            'coreference_prohibited={self.coreference_prohibited!r}, ' \
            'modifiers={self.modifiers!r}, ' \
            'appositives={self.appositives!r}, ' \
            'predicatives={self.predicatives!r}, ' \
            'non_stopwords={self.non_stopwords!r}, ' \
            'main_modifiers={self.main_modifiers!r}, ' \
            'sentence_number={self.sentence_number!r}, ' \
            ')'.format(self=self)

    def add_modifier(self, mod):

        self.modifiers.append(mod)

    def add_appositive(self, app):

        self.appositives.append(app)

    def add_no_stopword(self, nsw):

        self.non_stopwords.append(nsw)

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
            self.span = full_content[start:end + 1]

    @classmethod
    def from_naf(cls, nafobj, stopwords, constituent_info, head, mid):
        '''
        Create a mention object from naf information

        :param nafobj:              the input naffile
        :param constituent_info:    information about the constituent
        :param head:                the id of the constituent's head
        :param mid:                 the mid (for creating a unique mention id
        :return:                    a `Mention` object
        '''

        head_offset = None if head is None else get_offset(nafobj, head)

        span_ids = constituent_info.span
        span_offsets = convert_term_ids_to_offsets(nafobj, span_ids)
        mention = cls(
            mid,
            span=span_offsets,
            head_offset=head_offset,
            non_stopwords=get_non_stopwords(nafobj, stopwords, span_ids),
            full_head=convert_term_ids_to_offsets(
                nafobj, constituent_info.multiword),
            sentence_number=get_sentence_number(nafobj, head),
            main_modifiers=get_main_modifiers(nafobj, span_ids),
            predicatives=[
                convert_term_ids_to_offsets(nafobj, pred_ids)
                for pred_ids in constituent_info.predicatives
            ]
        )

        # modifers and appositives:
        relaxed_span = span_offsets
        for mod_in_tids in constituent_info.modifiers:
            mod_span = convert_term_ids_to_offsets(nafobj, mod_in_tids)
            mention.add_modifier(mod_span)
            for mid in mod_span:
                if mid > head_offset and mid in relaxed_span:
                    relaxed_span.remove(mid)

        for app_in_tids in constituent_info.appositives:
            app_span = convert_term_ids_to_offsets(nafobj, app_in_tids)
            mention.add_appositive(app_span)
            for mid in app_span:
                if mid > head_offset and mid in relaxed_span:
                    relaxed_span.remove(mid)
        mention.relaxed_span = relaxed_span

        # set POS of head
        if head is not None:
            head_pos = get_pos_of_term(nafobj, head)
            mention.head_pos = head_pos
            if head_pos in ['pron', 'noun', 'name']:
                analyze_nominal_information(nafobj, head, mention)

        begin_offset, end_offset = get_offsets_from_span(nafobj, span_ids)
        mention.begin_offset = begin_offset
        mention.end_offset = end_offset

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


def analyze_nominal_information(nafobj, term_id, mention):

    myterm = nafobj.get_term(term_id)
    morphofeat = myterm.get_morphofeat()
    identify_and_set_person(morphofeat, mention)
    identify_and_set_gender(morphofeat, mention)
    identify_and_set_number(morphofeat, myterm, mention)
    set_is_relative_pronoun(morphofeat, mention)


def get_sentence_number(nafobj, head):

    myterm = nafobj.get_term(head)
    tokid = myterm.get_span().get_span_ids()[0]
    mytoken = nafobj.get_token(tokid)
    sent_nr = int(mytoken.get_sent())

    return sent_nr


def identify_and_set_person(morphofeat, mention):

    if '1' in morphofeat:
        mention.person = '1'
    elif '2' in morphofeat:
        mention.person = '2'
    elif '3' in morphofeat:
        mention.person = '3'


def identify_and_set_number(morphofeat, myterm, mention):

    if 'ev' in morphofeat:
        mention.number = 'ev'
    elif 'mv' in morphofeat:
        mention.number = 'mv'
    elif 'getal' in morphofeat:
        lemma = myterm.get_lemma()
        if lemma in ['haar', 'zijn', 'mijn', 'jouw', 'je']:
            mention.number = 'ev'
        elif lemma in ['ons', 'jullie', 'hun']:
            mention.number = 'mv'


def identify_and_set_gender(morphofeat, mention):

    if 'fem' in morphofeat:
        mention.gender = 'fem'
    elif 'masc' in morphofeat:
        mention.gender = 'masc'
    elif 'onz,' in morphofeat:
        mention.gender = 'neut'


def set_is_relative_pronoun(morphofeat, mention):

    if 'betr,' in morphofeat:
        mention.is_relative_pronoun = True
    if 'refl,' in morphofeat:
        mention.is_reflective_pronoun = True
