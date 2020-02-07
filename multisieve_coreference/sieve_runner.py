import logging
from functools import partial

logger = logging.getLogger(None if __name__ == '__main__' else __name__)


class SieveRunner:
    """
    Hopefully temporary wrapper class to run a sieve.
    """
    def __init__(self, entities):
        self.entities = entities

    def run(self, sieve, **kwargs):
        """
        Run a `sieve` with `entity`, `candidates` and `mark_disjoint` as first
        three arguments, followed by all keyword arguments passed to this
        function. A `sieve` must return the `candidate` with which `entity`
        should be merged, or `None`.
        """
        for entity in self.entities:
            match = sieve(
                entity,
                self.entities.get_candidates(entity),
                partial(self.entities.mark_disjoint, entity),
                **kwargs
            )
            if match is not None:
                logger.debug(
                    "Given the first entity, the second was a match:\n"
                    f"{entity!r}\n"
                    f"{match!r}"
                )
                self.entities.merge(match, entity)
