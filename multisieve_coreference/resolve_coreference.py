import sys
import logging
import time
import itertools as it
from collections import defaultdict
from pkg_resources import get_distribution
from functools import partial

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
    get_strings_from_offsets
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
    # FIXME: this code calls `get_strings_from_offsets` (at least) twice for
    #        every mention: once (the first time) when it is `mention` (in
    #        `entity`), and again every time that it is `candidate_mention` (in
    #        `candidate`). (Attempt at faster algorithm commented below.)

    # For every `entity`, we should break the `for mention` loop at the first
    # `candidate` with a matching `candidate_mention`.
    for mention in entity:
        mention_string = get_strings_from_offsets(
            get_span(mention), offset2string)
        for candidate in filter(candidate_filter, candidates):
            for candidate_mention in candidate:
                candidate_string = get_strings_from_offsets(
                    get_span(mention), offset2string)
                if candidate_string == mention_string:
                    # Candidates should be kept, because they appear
                    # earlier. (Lee et al. 2013)
                    return candidate

    # Attempt at faster algorithm (I will only finish this when this function
    # seems to take a lot of time).
    # earlier_strings = {}
    # for mention in entity:
    #     mention_string = get_strings_from_offsets(
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
    non_stopwords = get_strings_from_offsets(
        mention.non_stopwords, offset2string)
    main_mods = get_strings_from_offsets(
        mention.main_modifiers, offset2string)
    antecedents = []
    for mid, comp_mention in mentions.items():
        # offset must be smaller to be antecedent and not i-to-i
        if comp_mention.head_offset < mention.head_offset and \
           not mention.head_offset <= comp_mention.end_offset:
            if head_string == offset2string.get(
               comp_mention.head_offset):
                match = True
                full_span = get_strings_from_offsets(
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
            if head_word in antecedent_head_words and \
               (sieve == '7' or check_word_inclusion(antecedent, entity)):
                # "Not i-within-i", i.e.:
                #   the two mentions are not in an i-within-i constructs, that
                #   is, one cannot be a child NP in the other's NP constituent
                # In this case, this is interpreted as "one mention does not
                # fully contain the other"
                for antecedent_mention in antecedent:
                    if check_not_i_within_i(antecedent_mention, mention):
                        # "Compatible modifiers only", i.e.:
                        #   the `mention`s modifiers are all included in in the
                        #   modifiers of the `antecedent_mention`. (...)
                        #   For this feature we only use modifiers that are
                        #   nouns or adjectives. (Thus `main_modifiers` instead
                        #   of `modifiers`.)
                        if sieve == '6':
                            return antecedent
                        else:
                            antecedent_main_mods = set(map(
                                offset2string.get, antecedent.main_modifiers
                            ))
                            if main_mods <= antecedent_main_mods:
                                return antecedent


def check_word_inclusion(antecedent, entity):
    """
    entity level "Word inclusion", i.e.:
      all the non-stop words in `entity` are included in the set
      of non-stop words in the `antecedent` entity.
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


def check_not_i_within_i(mention1, mention2):
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
    """
    boffset1 = mention1.begin_offset
    eoffset1 = mention1.end_offset
    boffset2 = mention2.begin_offset
    eoffset2 = mention2.end_offset
    return (
        (boffset2 > boffset1 and eoffset2 > eoffset1)
        or
        (eoffset1 > eoffset2 and boffset1 > boffset2)
    )


def only_identical_numbers(span1, span2, offset2string):

    word1 = get_strings_from_offsets(span1, offset2string)
    word2 = get_strings_from_offsets(span2, offset2string)

    for letter in word1:
        if letter.isdigit() and letter not in word2:
            return False

    return True


def contains_number(span, offset2string):

    for letter in get_strings_from_offsets(span, offset2string):
        if letter.isdigit():
            return True

    return False


def get_numbers(mention, offset2string):
    """
    Get the set of numbers in this mention (as per `str.isdigit`).

    A word containing only digits is considered a number.
    """
    return {
        word
        for word in get_strings_from_offsets(mention.span, offset2string)
        if word.isdigit()
    }


def apply_proper_head_word_match(
        entity, candidates, mark_disjoint, offset2string):
    """
    Pass 8 - Proper Head Word Match. This sieve marks two mentions headed by
    proper nouns as coreferent if they have the same head word and satisfy the
    following constraints (constraints marked by X are implemented):

     - [X] Not i-within-i
     - [ ] No location mismatches - the modifiers of two mentions cannot
           contain different location named entities, other proper nouns, or
           spatial modifiers. For example, [Lebanon] and [southern Lebanon] are
           not coreferent.
     - [X] No numeric mismatches - the second mention cannot have a number that
           does not appear in the antecedent, e.g., [people] and
           [around 200 people] (in that order) are not coreferent.

    This documentation string is adopted from Lee et al. (2013)
    """
    # FIXME: tool specific output for entity type
    correct_types = {
        'PER',  # person
        'ORG',  # organisation
        'LOC',  # location
        'MISC'  # miscellaneous
    }
    # FIXME: Location mismatches?!
    # FIXME: Why is this different?
    correct_antecedent_types = {'PER', 'ORG', 'LOC'}
    for mention in entity:
        mention_head = get_strings_from_offsets(
            mention.full_head, offset2string)
        mention_numbers = get_numbers(mention)
        check_not_i_within_i_for_this_mention = partial(
            check_not_i_within_i, mention)
        for antecedent in candidates:
            # Filter by type (I guess this is to implement the
            # "headed by proper nouns" part)
            antecedent_mentions = filter(
                lambda c: c.entity_type in correct_antecedent_types,
                antecedent)
            # "Not i-within-i"
            antecedent_mentions = filter(
                check_not_i_within_i_for_this_mention,
                antecedent_mentions
            )
            for antecedent_mention in antecedent_mentions:
                antecedent_head = get_strings_from_offsets(
                    antecedent_mention.full_head, offset2string)
                # "if they have the same head word"
                if mention_head == antecedent_head:
                    # "No numeric mismatches", i.e.:
                    #   the second mention cannot have a number that does not
                    #   appear in the antecedent
                    antecedent_numbers = get_numbers(antecedent_mention)
                    if antecedent_numbers >= mention_numbers:
                        return antecedent


def apply_relaxed_head_match(
        entity, candidates, mark_disjoint, candidate_filter, offset2string):
    """
    Pass 9 - Relaxed Head Match.

    This pass relaxes the entity head match heuristic by allowing the mention
    head to match any word in the antecedent entity. For example, this
    heuristic matches the mention Sanders to an entity containing the mentions
    {Sauls, the judge, Circuit Judge N. Sanders Sauls}. To maintain high
    precision, this pass requires that both mention and antecedent be labelled
    as named entities and the types coincide. Furthermore, this pass
    implements a conjunction of the given features with word inclusion and not
    i-within-i. This pass yields less than 0.4 point improvement in most
    metrics.

    Quoted from Lee et al. (2013)

    Things marked by an X are implemented:
     - [X] mention head must match any word in the antecedent entity
     - [ ] ~~both mention and antecedent be labelled as named entities~~
           this filter is not implemented within the sieve, but at a slightly
           higher level (TODO: Maybe it should be implemented here)
     - [X] the types coincide
     - [X] not i-within-i
     - [X] word inclusion

    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    """
    for antecedent in filter(candidate_filter, candidates):
        antecedent_entity_type = antecedent.mention_attr('entity_type')
        antecedent_words = set(get_strings_from_offsets(
            antecedent.flat_mention_attr('span'), offset2string))
        for mention in entity:
            mention_head = set(get_strings_from_offsets(
                mention.full_head, offset2string))
            # entity centric way of interpreting "the types coincide"
            if mention.entity_type in antecedent_entity_type and \
               mention_head <= antecedent_words and \
               check_not_i_within_i(antecedent, entity) and \
               check_word_inclusion(antecedent, entity):
                return antecedent


def resolve_pronoun_coreference(
        entity, candidates, mark_disjoint, max_sentence_distance):
    """
    We implement pronominal coreference resolution using an approach standard
    for many decades: enforcing agreement constraints between the coreferent
    mentions. We use the following attributes for these constraints (actually
    implemented constraints are marked with X):

     - [X] Number - we assign number attributes based on:
         - [X] a static list for pronouns;
         - [ ] NER labels: mentions marked as a named entity are considered
               singular with the exception of organizations, which can be both
               singular and plural;
         - [ ] part of speech tags: NN*S tags are plural and all other NN* tags
               are singular; and
         - [ ] a static dictionary from Bergsma and Lin (2006).

     - [X] Gender - we assign gender attributes from static lexicons from
           Bergsma and Lin (2006), and Ji and Lin (2009).

     - [X] Person - we assign person attributes only to pronouns.
         - [ ] We do not enforce this constraint when linking two pronouns,
               however, if one appears within quotes. This is a simple
               heuristic for speaker detection (e.g., I and she point to the
               same person in “[I] voted my conscience,” [she] said).

     - [ ] Animacy - we set animacy attributes using:
         - [ ] a static list for pronouns;
         - [ ] NER labels (e.g., PERSON is animate whereas LOCATION is not);
         - [ ] a dictionary bootstrapped from the Web (Ji and Lin 2009).

     - [X] NER label - from the Stanford NER.
     - [X] Pronoun distance - sentence distance between a pronoun and its
           antecedent cannot be larger than 3.

    When we cannot extract an attribute, we set the corresponding value to
    unknown and treat it as a wildcard—that is, it can match any other value.
    As expected, pronominal coreference resolution has a big impact on

    The above is quoted from Lee et al. (2013).

    !! NB !! The extraction of features is mostly implemented in `mention.py`.
             Most of the features are already reported by Alpino.

    :param mentions:    dictionary of all available mention objects (key is
                        mention id)
    :param coref_info:  CoreferenceInformation with current coreference classes
    :return:            None (mentions and coref_classes are updated in place)
    """
    # we only deal with unresolved pronouns here
    if {'pron'} == entity.mention_attr('head_pos'):
        # Sentence distance
        sentence_number = entity.mention_attr('sentence_number')
        max_sent_nr = max(sentence_number) + max_sentence_distance
        min_sent_nr = min(sentence_number) - max_sentence_distance
        # Number
        number = entity.mention_attr('number')
        # Gender
        gender = entity.mention_attr('gender')
        # Person
        person = entity.mention_attr('person')
        # Named entity label
        label = entity.mention_attr('entity_type')
        for candidate in candidates:
            # Entity centric sentence distance
            close_enough = any(
                min_sent_nr <= n <= max_sent_nr
                for n in candidate.mention_attr('sentence_number'))
            if close_enough:
                cnd_number = entity.mention_attr('number')
                cnd_gender = entity.mention_attr('gender')
                cnd_person = entity.mention_attr('person')
                cnd_label = entity.mention_attr('entity_type')
                if (not cnd_number or not number or cnd_number & number) and \
                   (not cnd_gender or not gender or cnd_gender & gender) and \
                   (not cnd_person or not person or cnd_person & person) and \
                   (not cnd_label or not label or cnd_label & label):
                    return candidate


def remove_singleton_entities(entities):
    """
    Remove singleton Entity objects in-place from the given `entities`.
    """
    for entity in entities:
        if len(entity) < 2:
            entities.remove(entity)


def post_process(nafobj, entities, fill_gaps=c.FILL_GAPS_IN_OUTPUT,
                 include_singletons=c.INCLUDE_SINGLETONS_IN_OUTPUT):
    # Fill gaps in the used mentions
    if fill_gaps:
        all_offsets = get_all_offsets(nafobj)
        for mention in it.chain.from_iterable(entities):
            mention.fill_gaps(all_offsets)

    if not include_singletons:
        remove_singleton_entities(entities)


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

    def is_nominal(entity):
        return bool(
            nominal_poses.intersection(entity.mention_attr('head_pos')))

    sieve_runner.run(
        match_relaxed_string,
        is_nominal,
        offset2string=offset2string,
        candidate_filter=is_nominal)

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

    def is_named_entity(entity):
        """
        If `entity_type` is not None, this was a named entity.
        """
        return bool(entity.mention_attr('entity_type'))

    logger.info("Sieve 9: Relaxed Head Match")
    sieve_runner.run(
        apply_relaxed_head_match,
        is_named_entity,
        candidate_filter=is_named_entity,
        offset2string=offset2string)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Entities: {}".format(
                view_entities(nafin, entities)
            )
        )

    logger.info("Sieve 10")

    logger.info("\tResolve relative pronoun coreferences")
    sieve_runner.run(resolve_pronoun_coreference, max_sentence_distance=3)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Entities: {}".format(
                view_entities(nafin, entities)
            )
        )

    logger.info("Post processing...")
    post_process(
        nafin,
        entities,
        fill_gaps=fill_gaps,
        include_singletons=include_singletons
    )

    return entities


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
