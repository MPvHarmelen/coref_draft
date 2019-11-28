"""
Two-Mention or two-Entity constraints.

The first argument must always be the candidate antecedent, while the second
argument must be the Mention/Entity occurring later.

Not all constraints are necessarily available at both the Mention _and_ the
Entity level. Moreover, some constraints take an Entity as antecedent and a
Mention that occurs later, or visa versa.
"""


def check_entity_head_match(antecedent, mention, offset2string):
    """
    Entity head match

    The `mention.head_word` matches _any_ head word of mentions in the
    `antecedent` entity.

    :param antecedent:  candidate antecedent Entity
    :param mention:     Mention under considerations
    :param offset2string:   {offset: surface_string} dictionary
    """
    head_word = offset2string[mention.head_offset]
    antecedent_head_words = map(
        offset2string.get,
        antecedent.mention_attr('head_offset')
    )
    return head_word in antecedent_head_words


def check_word_inclusion(antecedent, entity, offset2string):
    """
    entity level "Word inclusion", i.e.:
      all the non-stop words in `entity` are included in the set
      of non-stop words in the `antecedent` entity.

    :param antecedent:      candidate antecedent Entity
    :param entity:          Entity under consideration
    :param offset2string:   {offset: surface_string} dictionary
    """
    non_stopwords = set(map(
        offset2string.get,
        entity.flat_mention_attr('non_stopwords')
    ))
    antecedent_non_stopwords = set(map(
        offset2string.get,
        antecedent.flat_mention_attr('non_stopwords')
    ))
    return non_stopwords <= antecedent_non_stopwords


def check_compatible_modifiers_only(
        antecedent_mention, mention, offset2string):
    """
    Compatible modifiers only

    The `mention`s modifiers are all included in the modifiers of the
    `antecedent_mention`. (...) For this feature we only use modifiers that
    are nouns or adjectives. (Thus `main_modifiers` instead of `modifiers`.)

    Documentation string adapted from Lee et al. (2013)
    """
    main_mods = {offset2string[mod] for mod in mention.main_modifiers}
    antecedent_main_mods = {
        offset2string[mod] for mod in antecedent_mention.main_modifiers}
    return main_mods <= antecedent_main_mods


def check_not_i_within_i(antecedent_mention, mention):
    """
    Check whether one of the two mentions fully contains the other.

    "Not i-within-i", i.e.:
      the two mentions are not in an i-within-i constructs, that
      is, one cannot be a child NP in the other's NP constituent

    In this case, this is interpreted as "one mention does not
    fully contain the other"


    The following expression is equivalent to the one below
    not_i_within_i = not (
        (boffset2 <= boffset1 and eoffset1 <= eoffset2)
        or
        (boffset1 <= boffset2 and eoffset2 <= eoffset1)
    )

    This constraint is symmetric.

    :param antecedent_mention:  candidate antecedent Mention
    :param mention:     Mention under considerations
    """
    boffset1 = antecedent_mention.begin_offset
    eoffset1 = antecedent_mention.end_offset
    boffset2 = mention.begin_offset
    eoffset2 = mention.end_offset
    return (
        (boffset2 > boffset1 and eoffset2 > eoffset1)
        or
        (eoffset1 > eoffset2 and boffset1 > boffset2)
    )
