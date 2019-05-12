import logging
from collections import defaultdict, OrderedDict

from .mention_data import create_mention
from .offset_info import (
    convert_term_ids_to_offsets,
    get_offsets_from_span,
    get_offset
)
from .quotation import Cquotation
from .constituent_info import get_named_entities, get_constituents
from .quotation_naf import CquotationNaf
from . import constituents as csts
from .constituents import get_constituent

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


def get_string_of_term(nafobj, tid):

    my_term = nafobj.get_term(tid)
    termstring = ''
    latest_offset = '-1'

    for wid in my_term.get_span().get_span_ids():
        my_tok = nafobj.get_token(wid)
        # add space between tokens
        if len(termstring) > 0 and int(my_tok.get_offset) > latest_offset:
            termstring += ' '
        termstring += my_tok.get_text()
        latest_offset = int(my_tok.get_offset()) + int(my_tok.get_length())
    return termstring


def get_string_of_span(nafobj, span):

    mstring = ''
    latest_offset = -1
    for tid in span:
        my_term = nafobj.get_term(tid)
        for wid in my_term.get_span().get_span_ids():
            my_tok = nafobj.get_token(wid)
            # add space between tokens
            if len(mstring) > 0 and int(my_tok.get_offset()) > latest_offset:
                mstring += ' '
            mstring += my_tok.get_text()
            latest_offset = int(my_tok.get_offset()) + int(my_tok.get_length())
    return mstring


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


def get_mentions(nafobj):
    '''
    Function that creates mention objects based on mentions retrieved from NAF
    :param nafobj: input naf
    :return: list of Mention objects
    '''

    mention_constituents = get_mention_constituents(nafobj)
    mentions = OrderedDict()
    for head, constituentInfo in mention_constituents.items():
        mid = 'm' + str(len(mentions))
        mention = create_mention(nafobj, constituentInfo, head, mid)
        mentions[mid] = mention

    entities = get_named_entities(nafobj)
    for entity, constituent in entities.items():
        mid = 'm' + str(len(mentions))
        mention = create_mention(nafobj, constituent, entity, mid)
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


def get_quotation_spans(nafobj):
    '''
    Function that goes through nafobj and identifies spans of quotations
    :param nafobj: input naf
    :return: list of quotation objects with span defined
    '''

    # FIXME investigate on development corpus what to do with embedded
    # quotations; for now we'll assume a double quotation within a single
    # quote is an error

    in_double_quotation = False
    in_single_quotation = False
    quotations = []
    for term in nafobj.get_terms():
        if term.get_lemma() in ['"', '&amp;amp;amp;quot;']:
            if not in_double_quotation:
                in_double_quotation = True
                myQuote = CquotationNaf()
                myQuote.beginquote = term.get_id()
            else:
                in_double_quotation = False
                myQuote.endquote = term.get_id()
                quotations.append(myQuote)
            # break off single quotation if double quotation found during this
            if in_single_quotation:
                in_single_quotation = False
        elif in_double_quotation:
            myQuote.add_span_id(term.get_id())

        if term.get_lemma() == "'":
            if not in_single_quotation:
                in_single_quotation = True
                myQuoteSingle = CquotationNaf()
                myQuoteSingle.beginquote = term.get_id()
            else:
                in_single_quotation = False
                myQuoteSingle.endquote = term.get_id()
                quotations.append(myQuoteSingle)
        elif in_single_quotation:
            myQuoteSingle.add_span_id(term.get_id())

    return quotations


def create_set_of_tids_from_tidfunction(tidfunctionlist):

    tids = set()
    for tidfunc in tidfunctionlist:
        tids.add(tidfunc[0])

    return tids


def find_relevant_spans(deps, outside_ids):

    for dep in deps:
        if dep[0] in outside_ids and dep[1] in ['nucl/tag', 'dp/dp']:
            return dep[0]

    return None


def analyze_head_relations(nafobj, head_term, head2deps):

    dependents = head2deps.get(head_term)
    speaker = None
    addressee = None
    topic = None
    # FIXME: we want to check the preposition
    # FIXME: no dependents case does occur; check with bigger corpus
    if dependents is not None:
        for dep in dependents:
            if dep[1] == 'hd/su':
                speaker = get_constituent(dep[0])
            elif dep[1] == 'hd/obj2':
                term = nafobj.get_term(dep[0])
                if term.get_pos() == 'prep':
                    if dep[0] in head2deps:
                        for deprel in head2deps.get(dep[0]):
                            if deprel[1] == 'hd/obj1':
                                addressee = get_constituent(deprel[0])
                else:
                    addressee = get_constituent(dep[0])
            elif dep[1] in ['hd/mod']:
                term = nafobj.get_term(dep[0])
                if term.get_pos() == 'prep':

                    if dep[0] in head2deps:
                        # override addressee by complement if headed by
                        # preposition
                        for deprel in head2deps.get(dep[0]):
                            if deprel[1] == 'hd/obj1':
                                if term.get_lemma() == 'tegen':
                                    addressee = get_constituent(deprel[0])
                                elif term.get_lemma() == 'over':
                                    topic = get_constituent(deprel[0])

    return speaker, addressee, topic


def identify_direct_links_to_sip(nafobj, quotation):
    '''
    Function that identifies
    :param head2deps: dictionary linking head to dependents
    :param quotation: the quotation itself
    :return: boolean indicating whether source was found
    '''

    for tid in quotation.span:
        deps = csts.head2deps.get(tid)
        if deps is not None:
            # The first element of every tuple
            depids = set(next(iter(zip(*deps))))
            # if one of deps falls outside of quote, it can be linked to the
            # sip
            span_with_quotes = quotation.span + [
                quotation.beginquote, quotation.endquote
            ]
            my_joint_set = depids.difference(span_with_quotes)
            if len(my_joint_set) > 0:
                head_term = find_relevant_spans(deps, my_joint_set)
                if head_term is not None:
                    speaker, addressee, topic = analyze_head_relations(
                        nafobj, head_term, csts.head2deps)
                    if speaker is not None:
                        speaker_in_offsets = convert_term_ids_to_offsets(
                            nafobj, speaker)
                        quotation.source = speaker_in_offsets
                    if addressee is not None:
                        addressee_in_offsets = convert_term_ids_to_offsets(
                            nafobj, addressee)
                        quotation.addressee = addressee_in_offsets
                    if topic is not None:
                        topic_in_offsets = convert_term_ids_to_offsets(
                            nafobj, topic)
                        quotation.topic = topic_in_offsets


def check_if_quotation_contains_dependent(quotation):
    # FIXME: verify on larger set of development corpus whether this behaviour
    # is correct
    bad_relations = [
        'cmp/body',
        'hd/predc',
        'hd/obj1',
        'hd/vc',
        'hd/su',
        'hd/pc'
    ]
    # expected_rels = [
    #     'hd/app',
    #     'tag/nucl',
    #     '--/--',
    #     'dp/dp',
    #     '-- / --',
    #     'nucl/sat'
    # ]
    for tid in quotation.span:
        heads = csts.dep2heads.get(tid)
        if heads is not None:
            headids = create_set_of_tids_from_tidfunction(heads)
            span_with_quotes = quotation.span + [
                quotation.beginquote, quotation.endquote]
            if len(headids.difference(set(span_with_quotes))) > 0:
                for headid in headids.difference(set(span_with_quotes)):
                    for headrel in heads:
                        if headrel[0] == headid:
                            if headrel[1] in bad_relations:
                                return False
                            elif headrel[1] in ['crd/cnj']:
                                motherheadrels = csts.dep2heads.get(headrel[0])
                                if motherheadrels is not None:
                                    for mhid in motherheadrels:
                                        if mhid[1] in bad_relations:
                                            return False
                                        # elif not mhid[1] in expected_rels:
                                        #     print(
                                        #         tid,
                                        #         headids.difference(
                                        #             set(span_with_quotes)),
                                        #         'has outside head')
                                        #     print(motherheadrels)
                            # FIXME: debugs need to be checked out on bigger
                            # corpus; set up development mode
                            # elif not headrel[1] in expected_rels:
                            #     print(
                            #         tid,
                            #         headids.difference(set(span_with_quotes)),
                            #         'has outside head')
                            #     print(heads, quotation.span)
    return True


def get_sentences_of_quotation(nafobj, quotation):

    sentences = set()

    for tid in quotation.span:
        term = nafobj.get_term(tid)
        wid = term.get_span().get_span_ids()[0]
        token = nafobj.get_token(wid)
        sentence_nr = token.get_sent()
        # storing them as integers; they need to be sorted later
        sentences.add(int(sentence_nr))
    return sentences


def get_previous_and_next_sentence(sentences):

    ordered_sentences = sorted(sentences)
    if len(ordered_sentences) > 0:
        previous_sentence = ordered_sentences[0] - 1
        following_sentence = ordered_sentences[-1] + 1
    else:
        previous_sentence = 0
        following_sentence = 0

    return previous_sentence, following_sentence


def retrieve_sentence_preceding_sip(nafobj, terms):
    source_head = None
    for tid in terms:
        myterm = nafobj.get_term(tid)
        if myterm.get_lemma() == 'volgens':
            deps = csts.head2deps.get(tid)
            if deps is not None:
                for dep in deps:
                    if dep[1] == 'hd/obj1':
                        source_head = dep[0]

    return source_head


def retrieve_quotation_following_sip(nafobj, terms):

    source_head = None
    for tid in terms:
        myterm = nafobj.get_term(tid)
        if myterm.get_lemma() == 'aldus':
            deps = csts.head2deps.get(tid)
            if deps is not None:
                for dep in deps:
                    if dep[1] == 'hd/obj1':
                        source_head = dep[0]

    return source_head


def identify_addressee_or_topic_relations(nafobj, tid, quotation):

    # FIXME: language specific function
    heads = csts.dep2heads.get(tid)
    if heads is not None:
        for headrel in heads:
            headterm = nafobj.get_term(headrel[0])
            if headterm.get_lemma() == 'tegen' or headrel[1] == 'hd/obj2':
                myconstituent = get_constituent(headterm.get_id())
                addressee = convert_term_ids_to_offsets(nafobj, myconstituent)
                quotation.addressee = addressee
                return True
            elif headterm.get_lemma() == 'over':
                myconstituent = get_constituent(headterm.get_id())
                topic = convert_term_ids_to_offsets(nafobj, myconstituent)
                quotation.topic = topic
                return True
    return False


def get_candidates_not_part_of_addressee_topic(candidate_names, quotation):

    remaining_candidates = []
    covered_tids = quotation.addressee + quotation.topic
    for tid in candidate_names:
        if tid not in covered_tids:
            myconstituent = get_constituent(tid)
            remaining_candidates.append(myconstituent)
            covered_tids += myconstituent
    return remaining_candidates


def extract_full_names_or_prons(nafobj, constituents):

    names = []
    for const in constituents:
        name = []
        for tid in const:
            term = nafobj.get_term(tid)
            if term.get_pos() == 'name':
                name.append(tid)
        if len(name) == 0 and len(const) != 0:
            names.append(const)
        else:
            names.append(name)
    return names


def get_closest(candidates):

    closest = []
    selected_cand = []
    for cand in candidates:
        candnums = create_ordered_number_span(cand)
        if len(closest) == 0 or candnums[-1] > closest[-1]:
            closest = candnums
            selected_cand = cand
    return selected_cand


def identify_primary_candidate(candidates):

    for cand in candidates:
        for tid in cand:
            if tid in csts.dep2heads:
                for headrel in csts.dep2heads:
                    if headrel[1] == 'hd/su':
                        return cand

    # if no highest ranking found, return closest candidate
    return get_closest(candidates)


def find_name_or_pronoun(nafobj, preceding_terms, quotation):

    # FIXME: not over paragraph borders; if nothing found, sentence after can
    #        also work
    candidate_names = []
    for tid in preceding_terms:
        term = nafobj.get_term(tid)
        if term.get_pos() == 'name' or term.get_pos() == 'pron':
            if not identify_addressee_or_topic_relations(
               nafobj, tid, quotation):
                candidate_names.append(term.get_id())

    # change make dictionary with head term to constituent
    if len(candidate_names) > 0:
        remaining_candidates = get_candidates_not_part_of_addressee_topic(
            candidate_names, quotation)
        if len(remaining_candidates) > 0:
            candidates = extract_full_names_or_prons(
                nafobj, remaining_candidates)
            if len(candidates) == 1:
                candidate_in_offsets = convert_term_ids_to_offsets(
                    nafobj, candidates[0])
                quotation.source = candidate_in_offsets
            else:
                candidate = identify_primary_candidate(candidates)
                candidate_in_offsets = convert_term_ids_to_offsets(
                    nafobj, candidate)
                quotation.source = candidate_in_offsets


def create_ordered_number_span(term_list):

    number_list = []
    for tid in term_list:
        if 't_' in tid:
            tnumber = int(tid.lstrip('t_'))
            number_list.append(tnumber)
        elif 't' in tid:
            tnumber = int(tid.lstrip('t'))
            number_list.append(tnumber)

    return sorted(number_list)


def get_preceding_terms_in_sentence(first_sentence, quotation_span):
    # FIXME; move to offset based ids earlier; then this hack is not necessary
    quotation_numbers = create_ordered_number_span(quotation_span)
    preceeding_terms = []
    if len(quotation_numbers) > 0:
        for tid in first_sentence:
            if 't_' in tid:
                tnumber = int(tid.lstrip('t_'))
                if tnumber < quotation_numbers[0]:
                    preceeding_terms.append(tid)
            elif 't' in tid:
                tnumber = int(tid.lstrip('t'))
                if tnumber < quotation_numbers[0]:
                    preceeding_terms.append(tid)
    return preceeding_terms


def get_following_terms_in_sentence(last_sentence, quotation_span):

    # FIXME; move to offset based ids earlier; then this hack is not necessary
    quotation_numbers = create_ordered_number_span(quotation_span)
    following_terms = []
    for tid in last_sentence:
        if 't_' in tid:
            tnumber = int(tid.lstrip('t_'))
            if tnumber > quotation_numbers[0]:
                following_terms.append(tid)
        elif 't' in tid:
            tnumber = int(tid.lstrip('t'))
            if tnumber > quotation_numbers[0]:
                following_terms.append(tid)
    return following_terms


def identify_source_introducing_constructions(
        nafobj, quotation, sentence_to_term):
    '''
    Function that identifies structures that introduce sources of direct quotes
    :param nafobj: the input nafobj
    :param quotation: the quotation
    :return: None
    '''

    sentences = get_sentences_of_quotation(nafobj, quotation)
    prev_sent, follow_sent = get_previous_and_next_sentence(sentences)
    # FIXME: find out using development data whether preceding and following
    #        sentence should be taken into account or not
    # preceding_terms = sentence_to_term.get(str(prev_sent)) + \
    #     sentence_to_term.get(str(prev_sent + 1))

    # start with 'aldus' construction; this is more robust
    following_sentence = sentence_to_term.get(str(follow_sent - 1))
    source_head = None
    if following_sentence is not None:
        following_terms = get_following_terms_in_sentence(
            following_sentence, quotation.span)
        source_head = retrieve_quotation_following_sip(nafobj, following_terms)

    if source_head is None:
        preceding_terms = get_preceding_terms_in_sentence(
            sentence_to_term.get(str(prev_sent + 1)), quotation.span)
        source_head = retrieve_sentence_preceding_sip(nafobj, preceding_terms)

    if source_head is not None:
        source_constituent = get_constituent(source_head)
        source_in_offsets = convert_term_ids_to_offsets(
            nafobj, source_constituent)
        quotation.source = source_in_offsets
    else:
        find_name_or_pronoun(nafobj, preceding_terms, quotation)
    # 3. check previous sentence for name or pronoun


def get_sentence_to_terms(nafobj):

    token2terms = {}
    for term in nafobj.get_terms():
        tokens = term.get_span().get_span_ids()
        for tok in tokens:
            token2terms[tok] = term.get_id()

    sentence2terms = defaultdict(list)
    for token in nafobj.get_tokens():
        sent_nr = token.get_sent()
        term_id = token2terms.get(token.get_id())
        sentence2terms[sent_nr].append(term_id)

    return sentence2terms


def get_reduced_list_of_quotations(toremove, found_quotations):

    reduced_quotations = []
    for quote in found_quotations:
        wrong = False
        for wrong_quote in toremove:
            if set(quote.span) == set(wrong_quote.span):
                wrong = True
        if not wrong:
            reduced_quotations.append(quote)
    return reduced_quotations


def identify_direct_quotations(nafobj, mentions):
    '''
    Function that identifies direct quotations in naf
    :param nafobj: input naf object
    :return:
    '''

    nafquotations = get_quotation_spans(nafobj)
    toremove = []
    for quotation in nafquotations:
        identify_direct_links_to_sip(nafobj, quotation)
        if len(quotation.source) == 0:
            # this can lead to indication of quotation being attribution rather
            # than quotation
            if check_if_quotation_contains_dependent(quotation):
                sentence_to_terms = get_sentence_to_terms(nafobj)
                identify_source_introducing_constructions(
                    nafobj, quotation, sentence_to_terms)
            else:
                toremove.append(quotation)

    finalnafquotations = get_reduced_list_of_quotations(
        toremove, nafquotations)
    quotations = []
    for qid, nafquotation in enumerate(finalnafquotations):
        myquote = create_coref_quotation_from_quotation_naf(
            nafobj, nafquotation, mentions, qid)
        quotations.append(myquote)

    return quotations


def link_span_ids_to_mentions(span, mentions):
    '''
    Find out whether `span` corresponds to a mention candidate and, if so,
    which one
    :param span: list of span ids
    :param mentions: object containing all candidate mentions
    :return:
    '''

    for key, mention in mentions.items():
        if set(span) == set(mention.span):
            return key

    for key, mention in mentions.items():
        if set(span).issubset(set(mention.span)) or set(span).issuperset(
           mention.span):
            return key

    # import traceback
    # print(traceback.extract_stack(limit=2)[-1][2] + " - span: " + str(span))


def create_coref_quotation_from_quotation_naf(
        nafobj, nafquotation, mentions, quote_id):
    '''
    Function that turns naf quotation object into quotation object to be passed
    on to multisieve
    :param nafobj: input naf
    :param nafquotation: quotation object with naf specific information
    :param quote_id: identifier for quotation
    :return:
    '''

    myQuote = Cquotation(quote_id)

    quotespan = convert_term_ids_to_offsets(nafobj, nafquotation.span)
    myQuote.span = quotespan

    quotestring = get_string_of_span(nafobj, nafquotation.span)
    myQuote.string = quotestring

    beginoffset, endoffset = get_offsets_from_span(nafobj, nafquotation.span)
    myQuote.begin_offset = beginoffset
    myQuote.end_offset = endoffset

    if len(nafquotation.source) > 0:
        source_mention_id = link_span_ids_to_mentions(
            nafquotation.source, mentions)
        myQuote.source = source_mention_id
    if len(nafquotation.addressee) > 0:
        addressee_mention_id = link_span_ids_to_mentions(
            nafquotation.addressee, mentions)
        myQuote.addressee = addressee_mention_id
    if len(nafquotation.topic) > 0:
        topic_mention_id = link_span_ids_to_mentions(
            nafquotation.topic, mentions)
        myQuote.topic = topic_mention_id

    return myQuote


def get_offset2string_dicts(nafobj):

    offset2string = {}
    offset2lemma = {}

    for term in nafobj.get_terms():
        identifier = get_offset(nafobj, term.get_id())
        lemma = term.get_lemma()
        offset2lemma[identifier] = lemma

    for token in nafobj.get_tokens():
        identifier = int(token.get_offset())
        surface_string = token.get_text()
        offset2string[identifier] = surface_string

    return offset2string, offset2lemma
