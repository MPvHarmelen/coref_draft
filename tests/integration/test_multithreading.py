# from functools import reduce
# from operator import attrgetter
import sys
from queue import Queue
from threading import Thread, Barrier

from .run_and_compare import run_integration


def catching_run_factory(run, barrier, exception_queue):
    def inner(*args, **kwargs):
        # Synchronise the threads
        barrier.wait()
        try:
            run(*args, **kwargs)
        except Exception as e:
            exception_queue.put(e)
    return inner


def test_multithreading(tmp_path, easy_expected_to_succeed, easy_in_dir,
                        easy_correct_out_dir):
    easy_expected_to_succeed = list(easy_expected_to_succeed)
    exception_queue = Queue()
    barrier = Barrier(len(easy_expected_to_succeed))
    catching_run_integration = catching_run_factory(
        run_integration,
        barrier,
        exception_queue,
    )
    threads = [
        Thread(
            target=catching_run_integration,
            args=(
                filename,
                easy_in_dir,
                easy_correct_out_dir,
                str(tmp_path / filename)
            ),
            kwargs={'use_subprocess': False}
        )
        for filename in easy_expected_to_succeed
    ]

    # Start all of them, hopefully fast enough that a few will have to run at
    # the same time.
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if not exception_queue.empty():
        raise RuntimeError(
            f"There were (approximately) {exception_queue.qsize()} crashed"
            " threads. The first one should be on the trace of this exception."
        ) from exception_queue.get()


# The following code only works for Python 3.8 or higher :(
import threading    # noqa


class intolerant_threads:
    """

    Context manager that propagates all exceptions to the main thread.
    """
    def __init__(self):
        if sys.version_info < (3, 8):
            raise NotImplementedError(
                "This code uses `threading.excepthook`, which is only"
                " implemented for Python 3.8 or higher. See: "
                "https://docs.python.org/3.8/library/threading.html#threading.excepthook"  # noqa
            )
        self._old_hook = None

    def __enter__(self):
        self._old_hook = threading.excepthook
        threading.excepthook = self.excepthook
        return self

    def __exit__(self, *i_dont_know_what_these_args_do):
        threading.excepthook = self._old_hook

    @staticmethod
    def excepthook(args):
        """Propagate all exceptions to the main thread."""
        sys.excepthook(args.exc_type, args.exc_value, args.exc_traceback)
