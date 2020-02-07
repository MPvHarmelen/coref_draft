"""
Two-Mention or two-Entity constraints.

The first argument must always be the candidate antecedent, while the second
argument must be the Mention/Entity occurring later.

Not all constraints are necessarily available at both the Mention _and_ the
Entity level. Moreover, some constraints may take an Entity as antecedent and a
Mention that occurs later, or visa versa.
"""


def check_entity_head_match(antecedent, entity, offset2string):
    """
    Entity head match

    The head word of _any_ mention in `entity` (exactly) matches the head word
    of _any_ mentions in the `antecedent` entity.

    :param antecedent:      candidate antecedent Entity
    :param entity:          Entity under considerations
    :param offset2string:   {offset: surface_string} dictionary
    """
    antecedent_head_words = {
        offset2string[offset]
        for offset in antecedent.mention_attr('head_offset')
    }
    entity_head_words = {
        offset2string[offset]
        for offset in entity.mention_attr('head_offset')
    }
    return bool(entity_head_words & antecedent_head_words)


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

    This description can either be interpreted as:

    > Every constituent that modifies `mention` should occur as modifying
    > constituent of `antecedent_mention`.

    or as:

    > All the tokens that appear as modifiers of `mention` should also appear
    > as modifiers of `antecedent_mention`.

    This code interprets it the **2nd** way.
    """
    main_mods = {
        offset2string[m]
        for mods in mention.main_modifiers
        for m in mods
    }
    antecedent_main_mods = {
        offset2string[m]
        for mods in antecedent_mention.main_modifiers
        for m in mods
    }
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
