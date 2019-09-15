import sys
import logging
import time
from collections import defaultdict
from pkg_resources import get_distribution

from KafNafParserPy import KafNafParser, Clp

from . import constants as c
from .constituents import create_headdep_dicts
from .dump import add_coreference_to_naf
from .mentions import get_mentions
from .entities import Entities
from .sieve_runner import SieveRunner

from .offset_info import (
    get_all_offsets,
    get_offset2string_dict,
    get_string_from_offsets
)
from .naf_info import identify_direct_quotations

logger = logging.getLogger(None if __name__ == '__main__' else __name__)


def match_some_span(entity, candidates, get_span, offset2string,
                    candidate_filter=lambda e: True):
    '''
    Merge entities that contain mentions with (full) string match.

    :param entities:        entities to use
    :param get_span:        (mention -> span) function to get the span to use
    :param offset2string:   offset2string dictionary to use
    :param entity_filter:   filter to choose which entities this sieve should
                            act upon
    '''
    # FIXME: now only surface strings, we may want to look at lemma matches
    #        as well
    # FIXME: this code calls `get_string_from_offsets` (at least) twice for
    #        every mention: once (the first time) when it is `mention` (in
    #        `entity`), and again every time that it is `candidate_mention` (in
    #        `candidate`). (Attempt at faster algorithm commented below.)

    # For every `entity`, we should break the `for mention` loop at the first
    # `candidate` with a matching `candidate_mention`.
    for mention in entity:
        mention_string = get_string_from_offsets(
            get_span(mention), offset2string)
        for candidate in filter(candidate_filter, candidates):
            for candidate_mention in candidate:
                candidate_string = get_string_from_offsets(
                    get_span(mention), offset2string)
                if candidate_string == mention_string:
                    # Candidates should be kept, because they appear
                    # earlier. (Lee et al. 2013)
                    return candidate

    # Attempt at faster algorithm (I will only finish this when this function
    # seems to take a lot of time).
    # earlier_strings = {}
    # for mention in entity:
    #     mention_string = get_string_from_offsets(
    #         get_span(mention), offset2string)
    #     if mention_string in earlier_strings:
    #         possibly_candidate = earlier_strings[mention_string]
    #         if possibly_candidate in entities.get_candidates(entity):
    #             return possibly_candidate
    #         else:
    #             # ????
    #             ...
    #     else:
    #         earlier_strings[mention_string] = entity


def match_full_name_overlap(entity, candidates, mark_disjoint, offset2string):
    '''
    Merge entities with full string match

    :param entities:        entities to use
    :param offset2string:   offset2string dictionary to use
    :return:                None (Entities is updated in place)
    '''
    return match_some_span(entity, candidates, lambda m: m.span, offset2string)


def match_relaxed_string(
        entity, candidates, mark_disjoint, offset2string, candidate_filter):
    '''
    Merge nominal entities which have the same relaxed string

    :param entities:        entities to use
    :param offset2string:   offset2string dictionary to use
    :return:                None (Entities is updated in place)
    '''
    return match_some_span(
        entity,
        candidates,
        lambda m: m.relaxed_span,
        offset2string,
        candidate_filter)


def speaker_identification(entity, candidates, mark_disjoint, quotations):
    '''
    Apply the first sieve; assigning coreference or prohibiting coreference
    based on direct speech.

    The algorithm for this function is quoted below from Lee et al. (2013),
    with check marks indicating whether the rules are actually implemented:

        - [X] <I>s assigned to the same speaker are coreferent.
        - [ ] <you>s with the same speaker are coreferent.
        - [X] The speaker and <I>s in her text are coreferent.
        (...)
        - [ ] The speaker and a mention which is not <I> in the speaker's
              utterance cannot be coreferent.
        - [ ] Two <I>s (or two <you>s, or two <we>s) assigned to different
              speakers cannot be coreferent.
        - [ ] Two different person pronouns by the same speaker cannot be
              coreferent.
        - [ ] Nominal mentions cannot be coreferent with <I>, <you>, or <we> in
              the same turn or quotation.
        - [ ] In conversations, <you> can corefer only with the previous
              speaker.
        (...)
        We define <I> as _I_, _my_, _me_, or _mine_, <we> as first person
        plural pronouns, and <you> as second person pronouns.

    The quote entities are kept, while the ones corresponding to pronouns in
    the are discarded when merged.

    :param quotations:  list of quotation objects
    :return:            None (Entities is updated in place)
    '''
    entity_span = entity.flat_mention_attr('span')
    for quote in quotations:
        if entity_span.issubset(set(quote.span)):
            source = quote.source
            addressee = quote.addressee
            topic = quote.topic
            if 'pron' in entity.mention_attr('head_pos'):
                person = entity.mention_attr('person')
                if '1' in person:
                    if topic:
                        mark_disjoint(topic)
                    if addressee:
                        mark_disjoint(addressee)
                    if source:
                        return source
                elif '2' in person:
                    if source:
                        mark_disjoint(source)
                    if topic:
                        mark_disjoint(topic)
                    if addressee:
                        return addressee
                elif '3' in person:
                    if source:
                        mark_disjoint(source)
                    if addressee:
                        mark_disjoint(addressee)
                    if topic:
                        # Why should every third person pronoun refer to
                        # the `topic` of the quote?
                        # There can be multiple genders and/or
                        # multiplicities in the pronouns, and therefore
                        # they shouldn't all refer to the same topic??
                        return topic
            elif source:
                mark_disjoint(source)
                # TODO once vocative check installed; also prohibit linking
                # names to speaker


def identify_some_structures(entity, candidates, structure_name):
    """
    Assigns coreference for some structures in place

    :param entities:        entities to use
    :param get_structures:  name of the Mention attribute that is an iterable
                            of (hashable) spans.
    :return:                None (Entities is updated in place)
    """
    structures = entity.flat_mention_attr(structure_name)
    for candidate in candidates:
        if any(mention.span in structures for mention in candidate):
            return candidate


def identify_appositive_structures(entity, candidates, mark_disjoint):
    '''
    Assigns coreference for appositive structures in place

    :param entities:    entities to use
    :return:            None (Entities is updated in place)
    '''
    identify_some_structures(entity, candidates, 'appositives')


def identify_predicative_structures(entity, candidates, mark_disjoint):
    '''
    Assigns coreference for predicative structures in place

    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:                None (Entities is updated in place)
    '''
    identify_some_structures(entity, candidates, 'predicatives')


def resolve_relative_pronoun_structures(entity, candidates, mark_disjoint):
    '''
    Identifies relative pronouns and assigns them to the class of the noun
    they're modifying

    :param entities:    entities to use
    :return:            None (Entities is updated in place)
    '''
    if any(entity.mention_attr('is_relative_pronoun')):
        head_offsets = entity.mention_attr('head_offsets')
        for candidate in candidates:
            # If any of the `head_offsets` of this entity appear in the
            # `modifiers` of the candidate
            if head_offsets & candidate.flat_mention_attr('modifiers'):
                return candidate


def resolve_reflexive_pronoun_structures(entity, candidates, mark_disjoint):
    '''
    Merge two entities containing mentions for which all of the following hold:
     - they are in the same sentence
     - they aren't contained in each other
     - other is before mention

    But this algorithm is wrong for Dutch (thinks Martin):

     - it's far too eager:
        it does not check whether the antecedent is the subject.
     - it's too strict:
        "[zich] wassen deed [hij] elke dag"
        is a counter-example for the last rule

    :param entities:    entities to use
    :return:            None (Entities is updated in place)
    '''
    for mention in entity:
        if mention.is_reflexive_pronoun:
            sent_nr = mention.sentence_number
            for candidate in candidates:
                for cand_mention in candidate:
                    if cand_mention.sentence_number == sent_nr and \
                       mention.head_offset not in cand_mention.span and \
                       cand_mention.head_offset < mention.head_offset:
                        # We've found what we want!
                        return candidate


def identify_acronyms_or_alternative_names(entity, candidates, mark_disjoint):
    '''
    Identifies structures that add alternative name

    This function, does **not** do any acronym detection.
    It does merge two named entities if one modifies the other.

    According to Lee et al. (2013), this should adhere to the following
    algorithm:

    > both mentions are tagged as NNP and one of them is an acronym of the
    > other (e.g., [Agence France Presse] ... [AFP]). Our acronym detection
    > algorithm marks a mention as an acronym of another if its text equals the
    > sequence of upper case characters in the other mention. The algorithm is
    > simple, but our error analysis suggests it nonetheless does not lead to
    > errors.

    :param entities:    entities to use
    :return:            None (Entities is updated in place)
    '''
    # FIXME: input specific
    correct_types = {
        'PER',  # person
        'ORG',  # organisation
        'LOC',  # location
        'MISC'  # miscellaneous
    }
    # modifiers is of type `list(tuple(offset))`
    # If this entity is a named one
    if correct_types.intersection(entity.mention_attr('entity_type')):
        for candidate in candidates:
            etypes = candidate.mention_attr('entity_type')
            if correct_types.intersection(etypes):
                e_modifies_c = entity.mention_attr('span').intersection(
                    candidate.flat_mention_attr('modifiers')
                )
                c_modifies_e = candidate.mention_attr('span').intersection(
                    entity.flat_mention_attr('modifiers')
                )
                if e_modifies_c or c_modifies_e:
                    return candidate


def get_sentence_mentions(mentions):

    sentenceMentions = defaultdict(list)

    for mid, mention in mentions.items():
        snr = mention.sentence_number
        sentenceMentions[snr].append(mid)

    return sentenceMentions


def add_coref_prohibitions(mentions, coref_info):
    """
    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    """
    sentenceMentions = get_sentence_mentions(mentions)
    for snr, mids in sentenceMentions.items():
        for mid in mids:
            mention = mentions.get(mid)
            corefs = set()
            for c_class in coref_info.classes_of_mention(mention):
                corefs |= coref_info.coref_classes[c_class]
            for same_sent_mid in mids:
                if same_sent_mid != mid and same_sent_mid not in corefs:
                    mention.coreference_prohibited.append(same_sent_mid)


def apply_precise_constructs(entity, candidates, mark_disjoint):
    '''
    Function that moderates the precise constructs (calling one after the
    other)

    :param entities:    entities to use
    :return:            None (Entities is updated in place)
    '''
    # return the first match, or None
    return \
        identify_appositive_structures(entity, candidates, mark_disjoint) or \
        identify_predicative_structures(entity, candidates, mark_disjoint) or \
        resolve_relative_pronoun_structures(
            entity, candidates, mark_disjoint) or \
        identify_acronyms_or_alternative_names(
            entity, candidates, mark_disjoint) or \
        resolve_reflexive_pronoun_structures(
            entity, candidates, mark_disjoint) or \
        None
    # f. Demonym Israel, Israeli (later)


def find_strict_head_antecedents(mention, mentions, sieve, offset2string):
    '''
    Function that looks at which other mentions might be antecedent for the
    current mention

    :param mention:  current mention
    :param mentions: dictionary of all mentions
    :return:         list of antecedent ids
    '''
    head_string = offset2string.get(mention.head_offset)
    non_stopwords = get_string_from_offsets(
        mention.non_stopwords, offset2string)
    main_mods = get_string_from_offsets(
        mention.main_modifiers, offset2string)
    antecedents = []
    for mid, comp_mention in mentions.items():
        # offset must be smaller to be antecedent and not i-to-i
        if comp_mention.head_offset < mention.head_offset and \
           not mention.head_offset <= comp_mention.end_offset:
            if head_string == offset2string.get(
               comp_mention.head_offset):
                match = True
                full_span = get_string_from_offsets(
                    comp_mention.span, offset2string)
                if sieve in ['5', '7']:
                    for non_stopword in non_stopwords:
                        if non_stopword not in full_span:
                            match = False
                if sieve in ['5', '6']:
                    for mmod in main_mods:
                        if mmod not in full_span:
                            match = False
                if match:
                    antecedents.append(mid)

    return antecedents


def apply_strict_head_match(
        entity, candidates, mark_disjoint, offset2string, sieve):
    """
    :param entities:        entities to use
    :param offset2string:   offset2string dictionary to use
    :param sieve:           ID of the sieve as a string
    :return:                None (Entities is updated in place)
    """
    # FIXME: parser specific check for pronoun
    # FIXME: lots of things are calculated repeatedly and forgotten again.
    # entity level "Word inclusion"
    non_stopwords = set(map(
        offset2string.get,
        entity.flat_mention_attr('non_stopwords')
    ))
    # For any mention in this entity that isn't a pronoun
    for mention in (m for m in entity if m.head_pos != 'pron'):
        head_word = offset2string[mention.head_offset]
        main_mods = set(map(offset2string.get, mention.main_modifiers))
        for antecedent in candidates:
            # "Entity head match", i.e.:
            #   the mention `head_word` matches _any_ head word of mentions
            #   in the `antecedent` entity.
            antecedent_head_words = map(
                offset2string.get,
                antecedent.mention_attr('head_offset')
            )
            # entity level "Word inclusion", i.e.:
            #   all the non-stop words in `entity` are included in the set
            #   of non-stop words in the `antecedent` entity.
            antecedent_non_stopwords = set(map(
                offset2string.get,
                antecedent.flat_mention_attr('non_stopwords')
            ))
            if head_word in antecedent_head_words and \
               (sieve == '7' or non_stopwords <= antecedent_non_stopwords):
                # "Not I-within-I" is ignored for Dutch
                if sieve == '6':
                    return antecedent
                else:
                    # "Compatible modifiers only", i.e.:
                    #   the `mention`s modifiers are all included in in the
                    #   modifiers of the `antecedent_mention`. (...)
                    #   For this feature we only use modifiers that are
                    #   nouns or adjectives. (Thus `main_modifiers` instead
                    #   of `modifiers`.)
                    for antecedent_mention in antecedent:
                        antecedent_main_mods = set(map(
                            offset2string.get, antecedent.main_modifiers
                        ))
                        if main_mods <= antecedent_main_mods:
                            # We've found an adequate antecedent!
                            # Merging is done just before breaking the
                            # `for antecedent` loop, to reduce double code
                            # and the number of break statements.
                            # To make sure the `continue` statement below
                            # isn't run, we should break this
                            # `for antecedent_mention` loop.
                            return antecedent


def only_identical_numbers(span1, span2, offset2string):

    word1 = get_string_from_offsets(span1, offset2string)
    word2 = get_string_from_offsets(span2, offset2string)

    for letter in word1:
        if letter.isdigit() and letter not in word2:
            return False

    return True


def contains_number(span, offset2string):

    for letter in get_string_from_offsets(span, offset2string):
        if letter.isdigit():
            return True

    return False


def find_head_match_coreferents(mention, mentions, offset2string):
    '''
    Function that looks at which mentions might be antecedent for the current
    mention

    :param mention: current mention
    :param mentions: dictionary of all mentions
    :return: list of mention coreferents
    '''

    boffset = mention.begin_offset
    eoffset = mention.end_offset
    full_head_string = get_string_from_offsets(
        mention.full_head, offset2string)
    contains_numbers = contains_number(mention.span, offset2string)

    coreferents = []

    for mid, comp_mention in mentions.items():
        if mid != mention.id and \
           comp_mention.entity_type in ['PER', 'ORG', 'LOC']:
            # mention may not be included in other mention
            if not comp_mention.begin_offset <= boffset and \
               comp_mention.end_offset >= eoffset:
                match = True
                comp_string = get_string_from_offsets(
                    comp_mention.full_head, offset2string)
                for word in full_head_string.split():
                    if word not in comp_string:
                        match = False
                comp_contains_numbers = contains_number(
                   comp_mention.span, offset2string)
                if contains_numbers and comp_contains_numbers:
                    if not only_identical_numbers(
                            mention.span, comp_mention.span, offset2string):
                        match = False
                if match:
                    coreferents.append(mid)

    return coreferents


def apply_proper_head_word_match(entities, offset2string):
    # FIXME: tool specific output for entity type
    correct_types = {
        'PER',  # person
        'ORG',  # organisation
        'LOC',  # location
        'MISC'  # miscellaneous
    }
    for entity in entities:
        ...  # First do the abstraction to fix spaghetti code
    for mention in mentions.values():
        if mention.entity_type in correct_types:
            coreferents = find_head_match_coreferents(
                mention, mentions, offset2string)
            if len(coreferents) > 0:
                coref_info.add_coref_class(coreferents + [mention.id])


def find_relaxed_head_antecedents(mention, mentions, offset2string):
    '''
    Function that identifies antecedents for which relaxed head match applies

    :param mention:
    :param mentions:
    :return:
    '''

    boffset = mention.begin_offset
    full_head_string = get_string_from_offsets(
        mention.full_head, offset2string)
    non_stopwords = get_string_from_offsets(
        mention.non_stopwords, offset2string)
    antecedents = []

    for mid, comp_mention in mentions.items():
        # we want only antecedents
        if comp_mention.end_offset < boffset:
            if comp_mention.entity_type == mention.entity_type:
                match = True
                full_comp_head = get_string_from_offsets(
                    comp_mention.full_head, offset2string)
                for word in full_head_string.split():
                    if word not in full_comp_head:
                        match = False
                full_span = get_string_from_offsets(
                    comp_mention.span, offset2string)
                for non_stopword in non_stopwords:
                    if non_stopword not in full_span:
                        match = False
                if match:
                    antecedents.append(mid)

    return antecedents


def apply_relaxed_head_match(mentions, coref_info, offset2string):
    """
    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    """
    for mention in mentions.values():
        if mention.entity_type in ['PER', 'ORG', 'LOC', 'MISC']:
            antecedents = find_relaxed_head_antecedents(
                mention, mentions, offset2string)
            if len(antecedents) > 0:
                coref_info.add_coref_class(antecedents + [mention.id])


def is_compatible(string1, string2):
    '''
    Generic function to check if values are not incompatible
    :param string1: first string
    :param string2: second string
    :return: boolean
    '''
    # if either is underspecified, they are not incompatible
    if string1 is None or string2 is None:
        return True
    if len(string1) == 0 or len(string2) == 0:
        return True
    if string1 == string2:
        return True

    return False


def check_compatibility(mention1, mention2):

    if not is_compatible(mention1.number, mention2.number):
        return False
    if not is_compatible(mention1.gender, mention2.gender):
        return False
    # speaker/addressee 1/2 person was taken care of earlier on
    if not is_compatible(mention1.person, mention2.person):
        return False
    if not is_compatible(mention1.entity_type, mention2.entity_type):
        return False

    return True


def get_candidates_and_distance(mention, mentions):

    candidates = {}
    sent_nr = mention.sentence_number
    for mid, comp_mention in mentions.items():
        if mention.head_offset > comp_mention.head_offset:
            csnr = comp_mention.sentence_number
            # only consider up to 3 preceding sentences
            if csnr <= sent_nr <= csnr + 3:
                # check if not prohibited
                if mid not in mention.coreference_prohibited:
                    if check_compatibility(mention, comp_mention):
                        candidates[mid] = comp_mention.head_offset

    return candidates


def identify_closest_candidate(mention_index, candidates):
    distance = 1000000
    antecedent = None
    for candidate, head_index in candidates.items():
        candidate_distance = mention_index - head_index
        if candidate_distance < distance:
            distance = candidate_distance
            antecedent = candidate
    return antecedent


def identify_antecedent(mention, mentions):

    candidates = get_candidates_and_distance(mention, mentions)
    mention_index = mention.head_offset
    antecedent = identify_closest_candidate(mention_index, candidates)

    return antecedent


def resolve_pronoun_coreference(mentions, coref_info):
    """
    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    """
    for mention in mentions.values():
        # we only deal with unresolved pronouns here
        if mention.head_pos == 'pron' and \
           len(coref_info.classes_of_mention(mention)) == 0:
            antecedent = identify_antecedent(mention, mentions)
            if antecedent is not None:
                coref_info.add_coref_class([antecedent, mention.id])


def remove_singleton_coreference_classes(coref_classes):
    singletons = set()
    for cID, mention_ids in coref_classes.items():
        if len(mention_ids) < 2:
            singletons.add(cID)

    for cID in singletons:
        del coref_classes[cID]


def post_process(nafobj, mentions, coref_info,
                 fill_gaps=c.FILL_GAPS_IN_OUTPUT,
                 include_singletons=c.INCLUDE_SINGLETONS_IN_OUTPUT):
    # Remove unused mentions
    reffed_mentions = coref_info.referenced_mentions()
    for ID in tuple(mentions):
        if ID not in reffed_mentions:
            del mentions[ID]

    # Fill gaps in the used mentions
    if fill_gaps:
        all_offsets = get_all_offsets(nafobj)
        for mention in mentions.values():
            mention.fill_gaps(all_offsets)

    if not include_singletons:
        remove_singleton_coreference_classes(coref_info.coref_classes)


def initialize_global_dictionaries(nafobj):
    logger.debug("create_headdep_dicts")
    create_headdep_dicts(nafobj)


def resolve_coreference(nafin,
                        fill_gaps=c.FILL_GAPS_IN_OUTPUT,
                        include_singletons=c.INCLUDE_SINGLETONS_IN_OUTPUT,
                        language=c.LANGUAGE):

    logger.info("Initializing...")
    logger.debug("create_offset_dicts")
    offset2string = get_offset2string_dict(nafin)
    initialize_global_dictionaries(nafin)

    logger.info("Finding mentions...")
    mentions = get_mentions(nafin, language)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        from .util import view_mentions
        logger.debug(
            "Mentions: {}".format(
                view_mentions(nafin, mentions)
            )
        )

    # Order matters (a lot), but `mentions` is an OrderedDict (hopefully :)
    entities = Entities.from_mentions(mentions.values())
    sieve_runner = SieveRunner(entities)

    logger.info("Finding quotations...")
    quotations = identify_direct_quotations(nafin, entities)

    logger.info("Sieve 1: Speaker Identification")
    sieve_runner.run(speaker_identification, quotations=quotations)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        from .util import view_entities
        logger.debug(
            "Entities: {}".format(
                view_entities(nafin, entities)
            )
        )

    logger.info("Sieve 2: String Match")
    sieve_runner.run(match_full_name_overlap, offset2string=offset2string)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Entities: {}".format(
                view_entities(nafin, entities)
            )
        )

    logger.info("Sieve 3: Relaxed String Match")
    nominal_poses = {'name', 'noun'}

    def entity_filter(entity):
        return bool(
            nominal_poses.intersection(entity.mention_attr('head_pos')))

    sieve_runner.run(
        match_relaxed_string,
        entity_filter,
        offset2string=offset2string,
        candidate_filter=entity_filter)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Entities: {}".format(
                view_entities(nafin, entities)
            )
        )

    logger.info("Sieve 4: Precise constructs")
    sieve_runner.run(apply_precise_constructs)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Entities: {}".format(
                view_entities(nafin, entities)
            )
        )

    logger.info("Sieve 5-7: Strict Head Match")
    for sieve in ['5', '6', '7']:
        sieve_runner.run(
            apply_strict_head_match,
            offset2string=offset2string,
            sieve=sieve
        )

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Entities: {}".format(
                view_entities(nafin, entities)
            )
        )

    logger.info("Sieve 8: Proper Head Word Match")
    sieve_runner.run(apply_proper_head_word_match, offset2string=offset2string)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Entities: {}".format(
                view_entities(nafin, entities)
            )
        )

    logger.info("Sieve 9: Relaxed Head Match")
    apply_relaxed_head_match(mentions, coref_info, offset2string)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Entities: {}".format(
                view_entities(nafin, entities)
            )
        )

    logger.info("Sieve 10")

    logger.info("\tAdd coreferences prohibitions")
    add_coref_prohibitions(mentions, coref_info)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Entities: {}".format(
                view_entities(nafin, entities)
            )
        )

    logger.info("\tResolve relative pronoun coreferences")
    resolve_pronoun_coreference(mentions, coref_info)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Entities: {}".format(
                view_entities(nafin, entities)
            )
        )

    logger.info("Post processing...")
    post_process(
        nafin,
        mentions,
        coref_info,
        fill_gaps=fill_gaps,
        include_singletons=include_singletons
    )

    return coref_info.coref_classes, mentions


def process_coreference(
        nafin,
        fill_gaps=c.FILL_GAPS_IN_OUTPUT,
        include_singletons=c.INCLUDE_SINGLETONS_IN_OUTPUT,
        language=c.LANGUAGE):
    """
    Process coreferences and add to the given NAF.

    Note that coreferences are added in place.
    """
    coref_classes, mentions = resolve_coreference(
        nafin,
        fill_gaps=fill_gaps,
        include_singletons=include_singletons,
        language=language
    )
    logger.info("Adding coreference information to NAF...")
    add_coreference_to_naf(nafin, coref_classes, mentions)


def add_naf_header(nafobj, begintime):

    endtime = time.strftime('%Y-%m-%dT%H:%M:%S%Z')
    lp = Clp(
        name="vua-multisieve-coreference",
        version=get_distribution(__name__.split('.')[0]).version,
        btimestamp=begintime,
        etimestamp=endtime)
    nafobj.add_linguistic_processor('coreferences', lp)


def main(argv=None):
    # args and options left for later
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('-l', '--level', help="Logging level", type=str.upper,
                        default='WARNING')
    parser.add_argument(
        '-s',
        '--include-singletons',
        help="Whether to include singletons in the output",
        action='store_true',
    )
    parser.add_argument(
        '-f',
        '--fill-gaps',
        help="Whether to fill gaps in mention spans",
        action='store_true',
    )
    parser.add_argument(
        '--language',
        help="RFC5646 language tag of language data to use. Currently only"
        " reads a different set of stopwords. Defaults to {}".format(
            c.LANGUAGE),
        default=c.LANGUAGE
    )
    cmdl_args = vars(parser.parse_args(argv))
    logging.basicConfig(level=cmdl_args.pop('level'))

    # timestamp begintime
    begintime = time.strftime('%Y-%m-%dT%H:%M:%S%Z')

    logger.info("Reading...")
    nafobj = KafNafParser(sys.stdin)
    logger.info("Processing...")
    process_coreference(nafobj, **cmdl_args)

    # adding naf header information
    add_naf_header(nafobj, begintime)
    logger.info("Writing...")
    nafobj.dump()


if __name__ == '__main__':
    main()
