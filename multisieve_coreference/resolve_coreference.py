import sys
import logging
import time
import itertools as it
from pkg_resources import get_distribution

from KafNafParserPy import KafNafParser, Clp

from . import constants as c
from .constituents import create_headdep_dicts
from .dump import add_coreference_to_naf
from .mentions import get_mentions
from .entities import Entities
from .sieve_runner import SieveRunner
from .filters import is_named_entity, is_nominal, is_proper_noun, is_pronoun
from .constraints import (
    check_entity_head_match,
    check_word_inclusion,
    check_compatible_modifiers_only,
    check_not_i_within_i,
)
from .offset_info import (
    get_all_offsets,
    get_offset2string_dict,
    get_strings_from_offsets
)
from .naf_info import identify_direct_quotations

logger = logging.getLogger(None if __name__ == '__main__' else __name__)


def match_some_span(entity, candidates, mark_disjoint, get_span, offset2string,
                    entity_filter=lambda e: True):
    '''
    Merge entities that contain mentions with (full) string match.

    :param get_span:        (mention -> span) function to get the span to use
    :param offset2string:   {offset: string} dictionary to use
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
    if not entity_filter(entity):
        return

    for mention in entity:
        mention_string = get_strings_from_offsets(
            get_span(mention), offset2string)
        for candidate in filter(entity_filter, candidates):
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
    :return:    first matching candidate
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


def identify_some_structures(
        entity, candidates, mark_disjoint, structure_name):
    """
    Assigns coreference for some structures in place

    :param structure_name:  name of the Mention attribute that is an iterable
                            of (hashable) spans.
    :return:                first matching candidate
    """
    structures = entity.flat_mention_attr(structure_name)
    for candidate in candidates:
        if any(mention.span in structures for mention in candidate):
            return candidate


def resolve_relative_pronoun_structures(entity, candidates, mark_disjoint):
    '''
    Identifies relative pronouns and assigns them to the class of the noun
    they're modifying

    :return:    first matching candidate
    '''
    if any(entity.mention_attr('is_relative_pronoun')):
        head_offsets = entity.mention_attr('head_offset')
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

    :return:    first matching candidate
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

    :return:    first matching candidate
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


def apply_precise_constructs(entity, candidates, mark_disjoint):
    '''
    Function that moderates the precise constructs (calling one after the
    other)

    :return:    first matching candidate
    '''
    # return the first match, or None
    return \
        identify_some_structures(
            entity, candidates, mark_disjoint, 'appositives') or \
        identify_some_structures(
            entity, candidates, mark_disjoint, 'predicatives') or \
        resolve_relative_pronoun_structures(
            entity, candidates, mark_disjoint) or \
        identify_acronyms_or_alternative_names(
            entity, candidates, mark_disjoint) or \
        resolve_reflexive_pronoun_structures(
            entity, candidates, mark_disjoint) or \
        None
    # f. Demonym Israel, Israeli (later)


def apply_strict_head_match(
        entity, candidates, mark_disjoint, offset2string, sieve_name):
    """
    Pass 5 - Strict Head Match.

    Linking a mention to an antecedent based on the naive matching of their
    head words generates many spurious links because it completely ignores
    possibly incompatible modifiers (Elsner and Charniak 2010). For example,
    _Yale University_ and _Harvard University_ have similar head words, but
    they are obviously different entities. To address this issue, this pass
    implements several constraints that must all be matched in order to yield a
    link (constraints marked by an X are actually implemented):

     - [X] Not a pronoun (This constraint is not from Lee et al. (2013))

     - [X] Entity head match - the mention head word matches any head word of
           mentions in the antecedent entity. Note that this feature is
           actually more relaxed than naive head matching in a pair of mentions
           because here it is satisfied when the mention's head matches the
           head of any mention in the candidate entity.

     - [X] Word inclusion - all the non-stop words in the current entity to be
           solved are included in the set of non-stop words in the antecedent
           entity. This heuristic exploits the discourse property that states
           that it is uncommon to introduce novel information in later mentions
           (Fox 1993). Typically, mentions of the same entity become shorter
           and less informative as the narrative progresses.
           !! Disabled iff `sieve` is `'7'` !!


     - [X] Compatible modifiers only - the mention's modifiers are all included
           in the modifiers of the antecedent candidate. This feature models
           the same discourse property as the previous feature, but it focuses
           on the two individual mentions to be linked, rather than their
           corresponding entities. For this feature we only use modifiers that
           are nouns or adjectives.
           !! Disabled iff `sieve` is `'6'` !!

     - [X] Not i-within-i - the two mentions are not in an i-within-i
           construct, that is, one cannot be a child NP in the other's NP
           constituent (Chomsky 1981). See `check_not_i_within_i` for how it is
           implemented here.

    Documentation string adapted from Lee et al. (2013).

    :param offset2string:   {offset: string} dictionary to use
    :param sieve_name:      name of the sieve as a string
    :return:                first matching candidate
    """
    # FIXME: lots of things are calculated repeatedly and forgotten again.

    # For any mention in this entity that isn't a pronoun
    mentions = [m for m in entity if not is_pronoun(m)]
    if not mentions:
        return

    # Make the loop more readable by currying.
    def check_entity_head_match_this_entity(antecedent):
        return check_entity_head_match(
            antecedent,
            entity=entity,
            offset2string=offset2string)

    def check_word_inclusion_this_entity(antecedent):
        return check_word_inclusion(
            antecedent,
            entity=entity,
            offset2string=offset2string)

    for antecedent in candidates:
        if check_entity_head_match_this_entity(antecedent) and \
           (sieve_name == '7' or check_word_inclusion_this_entity(antecedent)):
            pairs = [
                (antecedent_mention, mention)
                for antecedent_mention in antecedent
                for mention in mentions
                if check_not_i_within_i(antecedent_mention, mention)
            ]
            if pairs and (sieve_name == '6' or
               any(map(check_compatible_modifiers_only, pairs))):
                return antecedent


def get_numbers(mention, offset2string):
    """
    Get the set of numbers in this mention (as per `str.isdigit`).

    A word containing only digits is considered a number.

    :param mention:         mention to get numbers of
    :param offset2string:   {offset: string} dictionary to use
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

    This documentation string is adapted from Lee et al. (2013)

    :param offset2string:   {offset: string} dictionary to use
    :return:                first matching candidate
    """
    if not is_proper_noun(entity):
        return

    # FIXME: Location mismatches?!
    for mention in entity:
        mention_head = get_strings_from_offsets(
            mention.full_head, offset2string)
        mention_numbers = get_numbers(mention, offset2string)

        for antecedent in candidates:
            # Proper nouns only
            antecedent_mentions = filter(is_proper_noun, antecedent)
            # "Not i-within-i"
            antecedent_mentions = (
                antecedent_mention
                for antecedent_mention in antecedent_mentions
                if check_not_i_within_i(antecedent_mention, mention)
            )
            for antecedent_mention in antecedent_mentions:
                antecedent_head = get_strings_from_offsets(
                    antecedent_mention.full_head, offset2string)
                # "if they have the same head word"
                if mention_head == antecedent_head:
                    # "No numeric mismatches", i.e.:
                    #   the second mention cannot have a number that does not
                    #   appear in the antecedent
                    antecedent_numbers = get_numbers(
                        antecedent_mention, offset2string)
                    if antecedent_numbers >= mention_numbers:
                        return antecedent


def apply_relaxed_head_match(entity, candidates, mark_disjoint, offset2string):
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

    :param offset2string:   {offset: string} dictionary to use
    :return:                first matching candidate
    """
    if not is_named_entity(entity):
        return

    for antecedent in filter(is_named_entity, candidates):
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

    :param max_sentence_distance:   maximum allowed sentence distance between
                                    coreferent pronouns
    :return:                        first matching candidate
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

    logger.info("Sieve 2: Exact Match")
    sieve_runner.run(
        match_some_span,
        get_span=lambda m: m.span,
        offset2string=offset2string)

    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.debug(
            "Entities: {}".format(
                view_entities(nafin, entities)
            )
        )

    logger.info("Sieve 3: Relaxed String Match")

    sieve_runner.run(
        match_some_span,
        get_span=lambda m: m.relaxed_span,
        entity_filter=is_nominal,
        offset2string=offset2string)

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
    for sieve_name in ['5', '6', '7']:
        sieve_runner.run(
            apply_strict_head_match,
            offset2string=offset2string,
            sieve_name=sieve_name
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
    sieve_runner.run(apply_relaxed_head_match, offset2string=offset2string)

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
    entities = resolve_coreference(
        nafin,
        fill_gaps=fill_gaps,
        include_singletons=include_singletons,
        language=language
    )
    logger.info("Adding coreference information to NAF...")
    add_coreference_to_naf(nafin, entities)


def add_naf_header(nafobj, begintime):

    endtime = time.strftime(c.TIMESTAMP_FORMAT)
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
    begintime = time.strftime(c.TIMESTAMP_FORMAT)

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
