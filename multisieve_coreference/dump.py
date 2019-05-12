import logging

from KafNafParserPy.span_data import Cspan, Ctarget
from KafNafParserPy.coreference_data import Ccoreference

from .offset_info import get_offset_to_term_id_dict

logger = logging.getLogger(None if __name__ == '__main__' else __name__)


def add_coreference_to_naf(nafobj, corefclasses, mentions):

    start_count = get_starting_count(nafobj)
    coref_according_to_offset = get_ordered_coreference_chains(
        corefclasses,
        mentions
    )

    offset2termid = get_offset_to_term_id_dict(nafobj)

    for mids in coref_according_to_offset:
        mids = set(mids)
        nafCoref = Ccoreference()
        cid = 'co' + str(start_count)
        start_count += 1
        nafCoref.set_id(cid)
        nafCoref.set_type('entity')
        data = sorted(
            (
                offset2termid[mention.head_offset],
                map(offset2termid.get, mention.span)
            )
            for mention in map(mentions.get, mids)
        )
        if logger.getEffectiveLevel() <= logging.DEBUG:
            logger.debug("Mentions:\n")
            for mid in mids:
                logger.debug("{}: {}".format(mid, mentions.get(mid)))
        for head_id, term_id_span in data:
            if logger.getEffectiveLevel() <= logging.DEBUG:
                term_id_span = list(term_id_span)
                logger.debug("cid: {}".format(cid))
                logger.debug("head ID: {}".format(head_id))
                logger.debug("TID span: {}".format(term_id_span))
            coref_span = create_span(term_id_span, head_id)
            nafCoref.add_span_object(coref_span)
        nafobj.add_coreference(nafCoref)


def create_span(term_id_span, head_id):
    '''
    Creates naf span object where head id is set
    :param term_id_span: list of term ids
    :param head_id: identifier for the head id
    :return: naf span object
    '''

    mySpan = Cspan()
    for term in term_id_span:
        if term == head_id:
            myTarget = Ctarget()
            myTarget.set_id(term)
            myTarget.set_as_head()
            mySpan.add_target(myTarget)
        else:
            mySpan.add_target_id(term)
    return mySpan


def get_ordered_coreference_chains(corefclasses, mentions):
    '''
    Function that creates new coreference dictionary with index of first
    mention as key (for ordering)

    :param corefclasses: identified coreference classes
    :return: dictionary of coreference classes with new indeces
    '''

    coref_dict = {}

    for mids in corefclasses.values():
        first_index = float('inf')
        for mid in mids:
            mention = mentions[mid]
            if mention.head_offset < first_index:
                first_index = mention.head_offset
        coref_dict[first_index] = mids

    return [coref_dict[k] for k in sorted(coref_dict)]


def get_starting_count(nafobj):

    coref_counter = 1
    for coref in nafobj.get_corefs():
        coref_counter += 1

    return coref_counter
