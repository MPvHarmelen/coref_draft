"""
This module parses the term layer of a KAF/NAF object
"""
from __future__ import print_function
import os

from .offset_info import (
    convert_term_ids_to_offsets,
    get_offset,
    get_offsets_from_span,
    get_pos_of_term,
)

stop_words = []


def initiate_stopword_list(lang='nl'):

    global stop_words
    resources = os.path.abspath(os.path.join(
        os.path.dirname(__file__),
        "resources"
    ))

    stopfile = open(os.path.join(resources, lang, 'stop_words.txt'), 'r')
    for line in stopfile:
        stop_words.append(line.rstrip())

    stopfile.close()


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
            no_stop_words=None,
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
        :type no_stop_words:           list
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
        self.no_stop_words = [] if no_stop_words is None else no_stop_words

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
            'no_stop_words={self.no_stop_words!r}, ' \
            'main_modifiers={self.main_modifiers!r}, ' \
            'sentence_number={self.sentence_number!r}, ' \
            ')'.format(self=self)

    def add_relaxed_span_offset(self, offset):
        self.relaxed_span.append(offset)

    def add_modifier(self, mod):

        self.modifiers.append(mod)

    def add_appositive(self, app):

        self.appositives.append(app)

    def add_predicative(self, pred):

        self.predicatives.append(pred)

    def add_no_stop_word(self, nsw):

        self.no_stop_words.append(nsw)

    def add_main_modifier(self, mmod):

        self.main_modifiers.append(mmod)

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
    def from_naf(cls, nafobj, constituentInfo, head, mid):
        '''
        Create a mention object from naf information

        :param nafobj:              the input naffile
        :param constituentInfo:     information about the constituent
        :param head:                the id of the constituent's head
        :param mid:                 the mid (for creating a unique mention id
        :return:                    a `Mention` object
        '''

        head_offset = None if head is None else get_offset(nafobj, head)

        span = constituentInfo.span
        offset_ids_span = convert_term_ids_to_offsets(nafobj, span)
        mention = cls(mid, span=offset_ids_span, head_offset=head_offset)
        mention.sentence_number = get_sentence_number(nafobj, head)
        # add no stop words and main modifiers
        add_non_stopwords(nafobj, span, mention)
        add_main_modifiers(nafobj, span, mention)
        # mwe info
        full_head_tids = constituentInfo.multiword
        mention.full_head = convert_term_ids_to_offsets(nafobj, full_head_tids)
        # modifers and appositives:
        relaxed_span = offset_ids_span
        for mod_in_tids in constituentInfo.modifiers:
            mod_span = convert_term_ids_to_offsets(nafobj, mod_in_tids)
            mention.add_modifier(mod_span)
            for mid in mod_span:
                if mid > head_offset and mid in relaxed_span:
                    relaxed_span.remove(mid)
        for app_in_tids in constituentInfo.appositives:
            app_span = convert_term_ids_to_offsets(nafobj, app_in_tids)
            mention.add_appositive(app_span)
            for mid in app_span:
                if mid > head_offset and mid in relaxed_span:
                    relaxed_span.remove(mid)
        mention.relaxed_span = relaxed_span

        for pred_in_tids in constituentInfo.predicatives:
            pred_span = convert_term_ids_to_offsets(nafobj, pred_in_tids)
            mention.add_predicative(pred_span)

        # set sequence of pos FIXME: if not needed till end; remove
        # os_seq = get_pos_of_span(nafobj, span)
        # mention.set_pos_seq(pos_seq)
        # set pos of head
        if head is not None:
            head_pos = get_pos_of_term(nafobj, head)
            mention.head_pos = head_pos
            if head_pos in ['pron', 'noun', 'name']:
                analyze_nominal_information(nafobj, head, mention)

        begin_offset, end_offset = get_offsets_from_span(nafobj, span)
        mention.begin_offset = begin_offset
        mention.end_offset = end_offset

        return mention


def add_main_modifiers(nafobj, span, mention):
    '''
    Function that creates list of all modifiers that are noun or adjective
    (possibly including head itself)

    :param nafobj: input naf
    :param span: list of term ids
    :param mention: mention object
    :return:
    '''

    main_mods = []
    for tid in span:
        term = nafobj.get_term(tid)
        if term.get_pos() in ['adj', 'noun']:
            main_mods.append(tid)

    main_mods_offset = convert_term_ids_to_offsets(nafobj, main_mods)
    mention.main_modifiers = main_mods_offset


def add_non_stopwords(nafobj, span, mention):
    '''
    Function that verifies which terms in span are not stopwords and adds these
    to non-stop-word list

    :param nafobj: input naf (for linguistic information)
    :param span: list of term ids
    :param mention: mention object
    :return:
    '''
    non_stop_terms = []

    for tid in span:
        my_term = nafobj.get_term(tid)
        if not my_term.get_type() == 'closed' and \
           not my_term.get_lemma().lower() in stop_words:
            non_stop_terms.append(tid)

    non_stop_span = convert_term_ids_to_offsets(nafobj, non_stop_terms)
    mention.no_stop_words = non_stop_span


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
