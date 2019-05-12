def get_offset(nafobj, term_id):
    '''
    Function that returns beginning offset of term
    :param nafobj: input naf
    :param term_id: id of term in question
    :return:
    '''

    return min(
        int(nafobj.get_token(wid).get_offset())
        for wid in nafobj.get_term(term_id).get_span_ids()
    )


def convert_term_ids_to_offsets(nafobj, seq):
    '''
    Convert a sequence of term IDs to a list of offsets
    :param nafobj:  input naf object
    :param seq:     sequence of term IDs
    :return:        a list of offsets
    '''

    return sorted(
        get_offset(nafobj, tid)
        for tid in seq
    )


def get_term_length(nafobj, term_id):
    '''
    Function that returns the length of a term
    :param nafobj: input naf
    :param term_id: id of term in question
    :return:
    '''

    my_term = nafobj.get_term(term_id)
    length = 0
    expected_offset = 0
    for wid in my_term.get_span().get_span_ids():
        my_token = nafobj.get_token(wid)
        offset = int(my_token.get_offset())
        token_length = int(my_token.get_length())
        length += token_length
        if expected_offset != 0 and expected_offset != offset:
            length += offset - expected_offset
        expected_offset = offset + token_length

    return length


def get_offsets_from_span(nafobj, span):
    '''
    Function that identifies begin and end offset for a span of terms
    :param nafobj: input naf
    :param span: list of term identifiers
    :return:
    '''

    offsets = []
    end_offsets = []
    for termid in span:
        offset = get_offset(nafobj, termid)
        length = get_term_length(nafobj, termid)
        offsets.append(offset)
        end_offsets.append(offset+length)

    begin_offset = 0
    end_offset = 0
    if len(offsets) > 0:
        begin_offset = min(offsets)
        end_offset = max(end_offsets)

    return begin_offset, end_offset
