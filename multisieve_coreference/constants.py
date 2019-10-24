INCLUDE_SINGLETONS_IN_OUTPUT = False
FILL_GAPS_IN_OUTPUT = False
LANGUAGE = 'nl-NL'


def TERM_FILTER(naf, term):
    return naf.get_term(term).get_pos() != 'punct'
