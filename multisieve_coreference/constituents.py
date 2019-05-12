import logging

from .constituency_trees import ConstituencyTrees

logger = logging.getLogger(None if __name__ == '__main__' else __name__)

tree = None
head2deps = None
dep2heads = None


def get_constituent(head):
    """
    Get all the terms in the constituent of which `head` is the head.
    """
    return tree.get_constituent(head)


def create_headdep_dicts(
        nafobj,
        term_filter=lambda naf, t: naf.get_term(t).get_pos() != 'punct'):
    '''
    Function that creates dictionaries of dep to heads and head to deps
    :param nafobj: nafobj from input file
    :return: None
    '''

    global tree, head2deps, dep2heads
    tree = ConstituencyTrees.from_naf(nafobj, term_filter)
    head2deps = tree.head2deps
    dep2heads = tree.dep2heads
