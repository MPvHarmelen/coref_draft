def get_offset2string_dict(nafobj):

    offset2string = {}

    for token in nafobj.get_tokens():
        identifier = int(token.get_offset())
        surface_string = token.get_text()
        offset2string[identifier] = surface_string

    return offset2string


def get_strings_from_offsets(id_span, offset2string):
    """
    Convert an iterable of offsets to a list of strings.
    """
    return [offset2string.get(mid) for mid in id_span]


def get_all_offsets(nafobj):
    return [
        int(token.get_offset()) for token in nafobj.get_tokens()
    ]


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

    :param nafobj:  input naf
    :param span:    list of term identifiers
    :return:        begin_offset, end_offset
    '''

    begin_offsets = []
    end_offsets = []
    for termid in span:
        offset = get_offset(nafobj, termid)
        length = get_term_length(nafobj, termid)
        begin_offsets.append(offset)
        end_offsets.append(offset+length)

    # FIXME: Using 0 as default seems bug-prone.
    #        Try what happens when returning None instead.

    # `default` isn't yet an accepted keyword argument for min/max in Python 2
    begin_offset = min(begin_offsets) if len(begin_offsets) else 0
    end_offset = min(end_offsets) if len(end_offsets) else 0

    return begin_offset, end_offset


def get_offset_to_term_id_dict(nafobj):
    token_id_dict = {}
    for token in nafobj.get_tokens():
        token_id_dict[token.get_id()] = token

    dic = {}
    for term in nafobj.get_terms():
        tid = term.get_id()
        for token in map(token_id_dict.get, term.get_span_ids()):
            dic[int(token.get_offset())] = tid
    return dic
