import sys
import logging
import time
from collections import defaultdict
from pkg_resources import get_distribution

from KafNafParserPy import KafNafParser, Clp

from . import constants as c
from .coref_info import CoreferenceInformation
from .constituents import create_headdep_dicts
from .dump import add_coreference_to_naf
from .mentions import get_mentions

from .offset_info import (
    get_all_offsets,
    get_offset2string_dict,
    get_string_from_offsets
)
from .naf_info import identify_direct_quotations

logger = logging.getLogger(None if __name__ == '__main__' else __name__)


def match_some_span(mentions, coref_info, get_span, offset2string):
    '''
    Function that places entities with full string match in the same
    coreference group

    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    '''
    found_entities = {}
    coref_classes = coref_info.coref_classes
    # FIXME: verify (when evaluating) whether prohibited needs to be taken into
    #        account here
    # FIXME 2: now only surface strings, we may want to look at lemma matches
    #          as well
    for mid, mention in mentions.items():
        if mention.head_pos in ['name', 'noun']:
            mention_string = get_string_from_offsets(
                get_span(mention), offset2string)
            if mention_string in found_entities:
                coref_id = found_entities[mention_string]
                coref_classes[coref_id].add(mention.id)
            else:
                classes_of_mention = coref_info.classes_of_mention(mention.id)
                if len(classes_of_mention) == 0:
                    # Don't merge because merging may change the IDs in
                    # `found_entities`
                    coref_id = coref_info.add_coref_class(
                        [mention.id],
                        merge=False
                    )
                else:
                    # coref classes will usually have a length 1; if not, it
                    # doesn't matter which one is picked
                    coref_id = next(iter(classes_of_mention))
                found_entities[mention_string] = coref_id


def match_full_name_overlap(mentions, coref_info, offset2string):
    '''
    Function that places entities with full string match in the same
    coreference group

    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    '''
    match_some_span(mentions, coref_info, lambda m: m.span, offset2string)


def match_relaxed_string(mentions, coref_info, offset2string):
    '''
    Function that matches mentions which have the same relaxed head

    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    '''
    match_some_span(
        mentions, coref_info, lambda m: m.relaxed_span, offset2string)


def included_in_direct_speech(quotations, mention, coref_info):
    '''
    Function that verifies whether mention is included in some quotation
    :param quotations:  list of quotation objects
    :param mention:     one specific `Mention`
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    '''
    mention_span_set = set(mention.span)
    for quote in quotations:
        if mention_span_set.issubset(set(quote.span)):
            # FIXME check if needed
            mention.in_quotation = True
            source = quote.source
            addressee = quote.addressee
            topic = quote.topic
            if mention.head_pos == 'pron':
                if mention.person == '1':
                    if source:
                        coref_info.add_coref_class([mention.id, source])
                    if topic:
                        mention.coreference_prohibited.append(topic)
                    if addressee:
                        mention.coreference_prohibited.append(addressee)
                elif mention.person == '2':
                    if source:
                        mention.coreference_prohibited.append(source)
                    if topic:
                        mention.coreference_prohibited.append(topic)
                    if addressee:
                        coref_info.add_coref_class([mention.id, addressee])
                elif mention.person == '3':
                    if source:
                        mention.coreference_prohibited.append(source)
                    if topic:
                        coref_info.add_coref_class([mention.id, topic])
                    if addressee:
                        mention.coreference_prohibited.append(addressee)
            elif source:
                    mention.coreference_prohibited.append(source)
                # FIXME this bad indentation could indicate a mistake. Check
                # with algorithm from paper
                # TODO once vocative check installed; also prohibit linking
                # names to speaker


def direct_speech_interpretation(quotations, mentions, coref_info):
    '''
    Function that applies the first sieve; assigning coreference or prohibited
    coreference based on direct speech

    :param quotations:  list of quotation objects
    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    '''
    for mid, mention in mentions.items():
        included_in_direct_speech(quotations, mention, coref_info)


def identify_span_matching_mention(span, mid, mentions):
    """
    Find the mentions different from `mid` that have the same span as `span`.

    :param span:        span to match mention spans against
    :param mid:         ID of the mention that should be ignored
    :param mentions:    {ID: mention} dictionary of all mentions to consider
    :return:            list of IDs of mentions that have `span` as their span
    """

    matching_mentions = []
    for ment_id, mention in mentions.items():
        if not ment_id == mid:
            if set(mention.span) == set(span):
                matching_mentions.append(ment_id)

    return matching_mentions


def identify_some_structures(mentions, coref_info, get_structures):
    """
    Assigns coreference for some structures in place

    :param mentions:       dictionary of all available mention objects (key is
                           mention id)
    :param coref_info:     CoreferenceInformation with current coreference
                           classes
    :param get_structures: function that returns a list of spans given a
                           `Mention` object.
    :return:               None (mentions and coref_classes are updated in
                           place)
    """
    for mid, mention in mentions.items():
        structures = get_structures(mention)
        for structure in structures:
            matching_mentions = identify_span_matching_mention(
                structure,
                mid,
                mentions
            )
            if len(matching_mentions) > 0:
                coref_info.add_coref_class([mid] + matching_mentions)


def identify_appositive_structures(mentions, coref_info):
    '''
    Assigns coreference for appositive structures in place

    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    '''
    identify_some_structures(mentions, coref_info, lambda m: m.appositives)


def identify_predicative_structures(mentions, coref_info):
    '''
    Assigns coreference for predicative structures in place

    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    '''
    identify_some_structures(mentions, coref_info, lambda m: m.predicatives)


def get_closest_match_relative_pronoun(mentions, matching, mention_index):

    candidates = {}
    for mid in matching:
        mention = mentions.get(mid)
        offset = mention.head_offset
        candidates[mention] = offset
    antecedent = identify_closest_candidate(mention_index, candidates)
    return antecedent


def resolve_relative_pronoun_structures(mentions, coref_info):
    '''
    Identifies relative pronouns and assigns them to the class of the noun
    they're modifying

    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    '''
    for mid, mention in mentions.items():
        if mention.is_relative_pronoun:
            matching = []
            for omid, othermention in mentions.items():
                if not omid == mid and \
                   mention.head_offset not in othermention.span:
                    for mod in othermention.modifiers:
                        if mention.head_offset in mod:
                            matching.append(omid)
            if len(matching) == 1:
                coref_info.add_coref_class(matching + [mid])
            elif len(matching) > 1:
                mention_index = mention.head_offset
                my_match = get_closest_match_relative_pronoun(
                    mentions,
                    matching,
                    mention_index
                )
                coref_info.add_coref_class([my_match.id, mid])


def resolve_reflexive_pronoun_structures(mentions, coref_info):
    '''
    Identifies mention that is correct coreference for reflexives

    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    '''
    for mid, mention in mentions.items():
        if mention.is_reflexive_pronoun:
            matching = []
            sent_nr = mention.sentence_number
            for omid, othermention in mentions.items():
                if othermention.sentence_number == sent_nr:
                    if not omid == mid and \
                       mention.head_offset not in othermention.span:
                        if int(othermention.head_offset) < mention.head_offset:
                            matching.append(omid)
            if len(matching) == 1:
                coref_info.add_coref_class(matching + [mid])
            elif len(matching) > 1:
                mention_index = mention.head_offset
                my_match = get_closest_match_relative_pronoun(
                    mentions,
                    matching,
                    mention_index
                )
                coref_info.add_coref_class([my_match.id, mid])


def identify_acronyms_or_alternative_names(mentions, coref_info):
    '''
    Identifies structures that add alternative name

    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    '''
    # FIXME input specific
    for mid, mention in mentions.items():
        if mention.entity_type in ['PER', 'ORG', 'LOC', 'MISC'] and \
           len(mention.modifiers) > 0:
            final_matches = []
            for mod in mention.modifiers:
                matching_mentions = identify_span_matching_mention(
                    mod,
                    mid,
                    mentions
                )
                for matchid in matching_mentions:
                    mymatch = mentions.get(matchid)
                    if mymatch.entity_type in ['PER', 'ORG', 'LOC', 'MISC']:
                        final_matches.append(matchid)
            if len(final_matches) > 0:
                coref_info.add_coref_class(final_matches + [mid])


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


def apply_precise_constructs(mentions, coref_info):
    '''
    Function that moderates the precise constructs (calling one after the
    other)

    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    '''
    identify_appositive_structures(mentions, coref_info)
    identify_predicative_structures(mentions, coref_info)
    resolve_relative_pronoun_structures(mentions, coref_info)
    identify_acronyms_or_alternative_names(mentions, coref_info)
    resolve_reflexive_pronoun_structures(mentions, coref_info)
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


def apply_strict_head_match(mentions, coref_info, offset2string, sieve='5'):
    """
    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :param sieve:       ID of the sieve as a string
    :return:            None (mentions and coref_classes are updated in place)
    """
    # FIXME: parser specific check for pronoun
    for mention in mentions.values():
        if not mention.head_pos == 'pron':
            antecedents = find_strict_head_antecedents(
                mention,
                mentions,
                sieve,
                offset2string,
            )
            if len(antecedents) > 0:
                coref_info.add_coref_class(antecedents + [mention.id])


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


def apply_proper_head_word_match(mentions, coref_info, offset2string):

    # FIXME: tool specific output for entity type
    for mention in mentions.values():
        if mention.entity_type in ['PER', 'ORG', 'LOC', 'MISC']:
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

    logger.info("Finding quotations...")
    quotations = identify_direct_quotations(nafin, mentions)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        from .util import view_mentions
        logger.debug(
            "Mentions just before S1: {}".format(
                view_mentions(nafin, mentions)
            )
        )

    coref_info = CoreferenceInformation()

    logger.info("Sieve 1: Speaker Identification")
    direct_speech_interpretation(quotations, mentions, coref_info)
    coref_info.merge()

    if logger.getEffectiveLevel() <= logging.DEBUG:
        from .util import view_coref_classes
        logger.debug(
            "Coreference classes: {}".format(
                view_coref_classes(nafin, mentions, coref_info.coref_classes)
            )
        )

    logger.info("Sieve 2: String Match")
    match_full_name_overlap(mentions, coref_info, offset2string)
    coref_info.merge()

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Coreference classes: {}".format(
                view_coref_classes(nafin, mentions, coref_info.coref_classes)
            )
        )

    logger.info("Sieve 3: Relaxed String Match")
    match_relaxed_string(mentions, coref_info, offset2string)
    coref_info.merge()

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Coreference classes: {}".format(
                view_coref_classes(nafin, mentions, coref_info.coref_classes)
            )
        )

    logger.info("Sieve 4: Precise constructs")
    apply_precise_constructs(mentions, coref_info)
    coref_info.merge()

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Coreference classes: {}".format(
                view_coref_classes(nafin, mentions, coref_info.coref_classes)
            )
        )

    logger.info("Sieve 5-7: Strict Head Match")
    apply_strict_head_match(mentions, coref_info, offset2string)
    coref_info.merge()

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Coreference classes: {}".format(
                view_coref_classes(nafin, mentions, coref_info.coref_classes)
            )
        )

    logger.info("Sieve 8: Proper Head Word Match")
    apply_proper_head_word_match(mentions, coref_info, offset2string)
    coref_info.merge()

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Coreference classes: {}".format(
                view_coref_classes(nafin, mentions, coref_info.coref_classes)
            )
        )

    logger.info("Sieve 9: Relaxed Head Match")
    apply_relaxed_head_match(mentions, coref_info, offset2string)
    coref_info.merge()

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Coreference classes: {}".format(
                view_coref_classes(nafin, mentions, coref_info.coref_classes)
            )
        )

    logger.info("Sieve 10")

    logger.info("\tAdd coreferences prohibitions")
    add_coref_prohibitions(mentions, coref_info)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Coreference classes: {}".format(
                view_coref_classes(nafin, mentions, coref_info.coref_classes)
            )
        )

    logger.info("\tResolve relative pronoun coreferences")
    resolve_pronoun_coreference(mentions, coref_info)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Coreference classes: {}".format(
                view_coref_classes(nafin, mentions, coref_info.coref_classes)
            )
        )

    coref_info.merge()

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Coreference classes: {}".format(
                view_coref_classes(nafin, mentions, coref_info.coref_classes)
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
