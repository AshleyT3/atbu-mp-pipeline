# Copyright 2022 Ashley R. Thomas
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
r"""Global queued logging used by parent and subprocesses.
"""

import os
import sys
import logging
import logging.handlers
import multiprocessing
import threading


from atbu.common.exception import (
    QueueListenerNotStarted,
    QueueListenerAlreadyStarted,
)

from .exception import (
    GlobalContextNotSet,
)


class ProcessThreadContextMixin:
    """A mixin to add useful functions for logging performed
    by multiprocessing classes.
    """

    @property
    def our_process(self):
        return multiprocessing.current_process()

    @property
    def our_thread(self):
        return threading.current_thread()

    @property
    def our_thread_name(self):
        return self.our_thread.name

    def get_exec_context_log_stamp_str(self):
        current_process = self.our_process
        current_thread = self.our_thread
        return (
            f"PID={os.getpid()} TID={current_thread.native_id} "
            f"t_name={current_thread.getName()} cp.pid={current_process.pid} "
            f"c_p={current_process} c_t={current_thread}"
        )


class MultiprocessGlobalContext:
    """MP global context. WARNING: Do not add any member variables that cannot be pickled, or
    generally avoid doing so if sharing is not needed.
    """

    def __init__(self, logging_queue, logging_level, verbosity_level):
        self._global_logging_queue = logging_queue
        self.global_logging_level = logging_level
        self.global_verbosity_level = verbosity_level

    @property
    def global_logging_queue(self):
        return self._global_logging_queue

    def create_queue_handler_logger(self, log_level=None, init_msg=None):
        logger = logging.getLogger()
        handler = logging.handlers.QueueHandler(self._global_logging_queue)
        logger.addHandler(handler)
        track_logging_handler(handler)
        if log_level:
            logger.setLevel(log_level)
        else:
            logger.setLevel(self.global_logging_level)
        return (
            self._perform_queue_logger_deadlock_workaround(
                logger=logger, init_msg=init_msg
            ),
            handler,
        )

    def remove_queue_handler_logger(self, handler):
        if not handler:
            return
        logger = logging.getLogger()
        if not logger:
            return
        for h in logger.handlers:
            if handler == h:
                logger.handlers.remove(h)
                break
        untrack_logging_handler(handler)

    def _perform_queue_logger_deadlock_workaround(self, logger, init_msg=None):
        if not init_msg:
            init_msg = (
                f"Initializing queue logger: PID={os.getpid()} level={logger.level}"
            )
        orig_level = logger.level
        logger.setLevel("INFO")
        # Without some message, the output of blank lines looks odd.
        # Add a message here to at least give indication of source/cause.
        logger.debug("Initializing subprocess.")
        logger.debug(init_msg)
        logger.setLevel(orig_level)
        return logger


_GLOBAL_CONTEXT: MultiprocessGlobalContext = None
_PARENT_QUEUE_LISTENER: logging.handlers.QueueListener = None
_QUEUE_HANDLER: logging.handlers.QueueHandler = None
_CREATED_LOGGING_HANDLERS: set = set()
_IS_GLOBAL_QUEUE_HANDLER_SETUP: bool = False


def global_init_subprocess(global_context_from_parent):
    global _GLOBAL_CONTEXT
    _GLOBAL_CONTEXT = global_context_from_parent
    _connect_root_logger_to_global_logging_queue()


def global_init(logging_level="INFO", verbosity_level=0):
    global _GLOBAL_CONTEXT
    if _GLOBAL_CONTEXT:
        return
    # Create system global logging mp Queue.
    _GLOBAL_CONTEXT = MultiprocessGlobalContext(
        logging_queue=multiprocessing.Queue(),
        logging_level=logging_level,
        verbosity_level=verbosity_level,
    )


def get_process_pool_exec_init_func():
    return global_init_subprocess


def get_process_pool_exec_init_args():
    return (_GLOBAL_CONTEXT,)


def track_logging_handler(*handlers):
    _CREATED_LOGGING_HANDLERS.update(handlers)


def untrack_logging_handler(*handlers):
    untracked = []
    for h in handlers:
        if h in _CREATED_LOGGING_HANDLERS:
            untracked.append(h)
            _CREATED_LOGGING_HANDLERS.remove(h)
    return untracked


def start_global_queue_listener(*logging_handlers):
    global _PARENT_QUEUE_LISTENER
    if not _GLOBAL_CONTEXT:
        raise GlobalContextNotSet(f"global_context not initialized.")
    if _PARENT_QUEUE_LISTENER:
        raise QueueListenerAlreadyStarted(f"parent_queue_listener already started.")
    _PARENT_QUEUE_LISTENER = logging.handlers.QueueListener(
        _GLOBAL_CONTEXT.global_logging_queue, *logging_handlers
    )
    track_logging_handler(*logging_handlers)
    _PARENT_QUEUE_LISTENER.start()


def stop_global_queue_listener():
    global _PARENT_QUEUE_LISTENER
    if not _PARENT_QUEUE_LISTENER:
        raise QueueListenerNotStarted(f"parent_queue_listener not started.")
    p = _PARENT_QUEUE_LISTENER

    untracked_handlers = untrack_logging_handler(*p.handlers)

    _PARENT_QUEUE_LISTENER = None
    p.stop()
    p.handlers = ()

    return untracked_handlers


def switch_to_non_queued_logging():
    """Switch to non-queued logging which is also logging
    without latency which is useful for certain commands that
    have the potential to interact with the user at the
    command-line, where logging latency can be problematic
    with interleaved with non-logging I/O.
    """
    # pylint: disable=broad-except
    try:
        handlers = stop_global_queue_listener()
    except Exception:
        return
    # Transfer handlers relating to queued listener output
    # directly to the root logger handler.
    root_logger = logging.getLogger()
    for h in handlers:
        root_logger.addHandler(h)
    # Stop supplying queue_handler.
    _GLOBAL_CONTEXT.remove_queue_handler_logger(handler=_QUEUE_HANDLER)


def _connect_root_logger_to_global_logging_queue():
    global _IS_GLOBAL_QUEUE_HANDLER_SETUP
    global _QUEUE_HANDLER
    if not _GLOBAL_CONTEXT:
        raise GlobalContextNotSet()
    if _IS_GLOBAL_QUEUE_HANDLER_SETUP:
        return
    # Root logger writes to queue handler going to global queue.
    _, _QUEUE_HANDLER = _GLOBAL_CONTEXT.create_queue_handler_logger()
    _IS_GLOBAL_QUEUE_HANDLER_SETUP = True


def remove_root_stream_handlers():
    """Remove logging.StreamHandler handlers from root
    logger. This helps to avoid double-logging output
    to console once normal atbu logging infra is setup.
    When doing this, we do not want to touch handlers
    added by pytest etc.
    """
    # pylint: disable=unidiomatic-typecheck

    # The following will not work...
    #     if isinstance(h, logging.StreamHandler):
    # ...because pytest's additions get removed.
    # Two choices:
    # a) Detect and ignore pytest's additions which
    # would require import _pytest and use of other
    # underscore types.
    # b) Do not use isinstance, instead of use type(h)
    # with 'is' operator and look specifically for
    # StreamHandlers.
    # We chose latter 'b' for now. Can always try
    # other ways if this does not work but this
    # seems less fragile as it does not take on
    # _pytest dependencies in a rough sense.
    for h in logging.root.handlers:
        if type(h) is logging.StreamHandler:
            logging.root.handlers.remove(h)


def remove_created_logging_handlers():
    all_loggers = [logging.root] + [
        logging.getLogger(name)
        for name in logging.root.manager.loggerDict  # pylint: disable=no-member
    ]
    for l in all_loggers:
        for h in l.handlers:
            if h in _CREATED_LOGGING_HANDLERS:
                l.handlers.remove(h)
                untrack_logging_handler(h)


def initialize_logging(logfile, loglevel, verbosity_level, log_console_detail):
    if not _GLOBAL_CONTEXT:
        raise GlobalContextNotSet()
    file_log_level = logging.DEBUG
    console_log_level = logging.INFO
    _GLOBAL_CONTEXT.global_logging_level = logging.INFO
    _GLOBAL_CONTEXT.global_verbosity_level = 0
    if loglevel is not None:
        file_log_level = loglevel
        console_log_level = loglevel
        _GLOBAL_CONTEXT.global_logging_level = loglevel
    if verbosity_level is not None:
        _GLOBAL_CONTEXT.global_verbosity_level = verbosity_level

    detailed_formatter = logging.Formatter(
        fmt=(
            "%(asctime)s.%(msecs)03d PID=%(process)-05d TID=%(thread)-05d "
            "%(name)-12s %(levelname)-8s %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _connect_root_logger_to_global_logging_queue()

    # Handlers to add to the global queue listener which are
    # final consumers of the logging records.
    handlers = ()

    # Console output.
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setLevel(console_log_level)
    if log_console_detail:
        stream_handler.setFormatter(detailed_formatter)
    handlers += (stream_handler,)

    if logfile is not None:
        file_handler = logging.FileHandler(logfile)
        file_handler.setLevel(file_log_level)
        file_handler.setFormatter(detailed_formatter)
        handlers += (file_handler,)

    start_global_queue_listener(*handlers)


def set_verbosity_level(level):
    global_init()
    if not _GLOBAL_CONTEXT:
        raise GlobalContextNotSet()
    _GLOBAL_CONTEXT.global_verbosity_level = int(level)


def get_verbosity_level() -> int:
    global_init()
    if not _GLOBAL_CONTEXT:
        raise GlobalContextNotSet()
    return _GLOBAL_CONTEXT.global_verbosity_level


def deinitialize_logging():
    stop_global_queue_listener()
    remove_created_logging_handlers()


def initialize_logging_basic():
    """Setup basic used during before command line processing and
    primary logging setup established.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
