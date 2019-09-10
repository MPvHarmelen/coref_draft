import itertools as it
from .dump import get_offset_to_term_id_dict


def term_id_to_tokens(nafobj, term_id):
    term = nafobj.get_term(term_id)
    if term is None:
        raise ValueError("No term with that ID: {!r}".format(term_id))
    return [
        (ID, nafobj.get_token(ID).get_text())
        for ID in term.get_span_ids()
    ]


def safe_term_id_to_tokens(*args, **kwargs):
    try:
        return term_id_to_tokens(*args, **kwargs)
    except ValueError:
        return []


def view_mentions(nafobj, mentions):
    """
    Content of mention constituent on separate lines
    """
    return '\n'.join(
        view_mention(nafobj, mention)
        for mention in mentions.values()
    )


def view_mention(nafobj, mention):
    dic = get_offset_to_term_id_dict(nafobj)
    return '{}: {!r}'.format(
        mention.id,
        list(it.chain.from_iterable(
            term_id_to_tokens(nafobj, termID)
            for termID in map(dic.get, mention.span)
        ))
    )


def view_coref_classes(nafobj, mentions, coref_classes):
    """
    Content of mention constituent on separate lines
    """
    return '\n'.join(
        str(cID) + ':\n\t' + '\n\t'.join(
            view_mention(nafobj, mentions[mID])
            for mID in mention_ids
        )
        for cID, mention_ids in coref_classes.items()
    )
