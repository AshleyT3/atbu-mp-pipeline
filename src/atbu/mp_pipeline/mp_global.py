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
from typing import Callable


from atbu.common.exception import (
    QueueListenerNotStarted,
    QueueListenerAlreadyStarted,
)

from .exception import (
    GlobalContextNotSet,
)


class ProcessThreadContextMixin:
    """A mixin to add useful functions for logging performed by
    multiprocessing classes.
    """

    @property
    def our_process(self):
        """Return the current process returned by
        :meth:`multiprocessing.current_process()`.
        """
        return multiprocessing.current_process()

    @property
    def our_thread(self):
        """Return the current thread returned by
        :meth:`threading.current_thread()`.
        """
        return threading.current_thread()

    @property
    def our_thread_name(self):
        """Returns the current thread's name.
        """
        return self.our_thread.name

    def get_exec_context_log_stamp_str(self):
        """Return a string useful for logging which contains the current
        PID, TID, and thread name.
        """
        current_process = self.our_process
        current_thread = self.our_thread
        return (
            f"PID={os.getpid()} TID={current_thread.native_id} "
            f"t_name={current_thread.getName()} cp.pid={current_process.pid} "
            f"c_p={str(current_process)} c_t={str(current_thread)}"
        )


class _MultiprocessGlobalContext:
    """Initialize a global context instance.
    
    MP global context. WARNING: Do not add any member
    variables that cannot be pickled, or generally avoid
    doing so if sharing is not needed.

    Args:
        logging_queue (:obj:`multiprocessing.Queue`): A multiprocessing
            shared process queue.
        logging_level (:obj:`str`): The Python logging level (i.e., "INFO",
            "DEBUG").
        verbosity_level (:obj:`int`): The verbosity level.
    """
    def __init__(self, logging_queue, logging_level, verbosity_level):

        self._global_logging_queue = logging_queue
        # The global logging level.
        self.global_logging_level = logging_level
        # THe global verbosity level.
        self.global_verbosity_level = verbosity_level

    @property
    def global_logging_queue(self):
        return self._global_logging_queue

    def create_queue_handler_logger(self, log_level=None, init_msg=None):
        logger = logging.getLogger()
        handler = logging.handlers.QueueHandler(self._global_logging_queue)
        logger.addHandler(handler)
        _track_logging_handler(handler)
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
        _untrack_logging_handler(handler)

    def _perform_queue_logger_deadlock_workaround(self, logger, init_msg=None):
        """Perform a workaround for
        `https://github.com/python/cpython/issues/91555`.
        """
        if not init_msg:
            init_msg = (
                f"Initializing queue logger: "
                f"PID={os.getpid()} level={logger.level}"
            )
        orig_level = logger.level
        logger.setLevel("INFO")
        # Without some message, the output of blank lines looks odd.
        # Add a message here to at least give indication of source/cause.
        logger.debug("Initializing subprocess.")
        logger.debug(init_msg)
        logger.setLevel(orig_level)
        return logger


_GLOBAL_CONTEXT: _MultiprocessGlobalContext = None
_PARENT_QUEUE_LISTENER: logging.handlers.QueueListener = None
_QUEUE_HANDLER: logging.handlers.QueueHandler = None
_CREATED_LOGGING_HANDLERS: set = set()
_IS_GLOBAL_QUEUE_HANDLER_SETUP: bool = False


def global_init(logging_level="INFO", verbosity_level=0):
    """Initialize the parent process global context for itself and
    all its subprocesses.

    The parent process should call this function once to initialize
    global context used for global logging.

    Args:
        logging_level (:obj:`str`):The Python logging level.
        verbosity_level (:obj:`int`): The verbosity level.
    """
    global _GLOBAL_CONTEXT
    if _GLOBAL_CONTEXT:
        return
    # Create system global logging mp Queue.
    _GLOBAL_CONTEXT = _MultiprocessGlobalContext(
        logging_queue=multiprocessing.Queue(),
        logging_level=logging_level,
        verbosity_level=verbosity_level,
    )


def set_verbosity_level(level):
    """Set the global verbosity level. The verbosity level's meaning
    is determined by the application's interpretation of it.

    Args:
        level (int): The verbosity level.

    Raises:
        GlobalContextNotSet: Raised if :func:`global_init` has not been called.
    """
    global_init()
    if not _GLOBAL_CONTEXT:
        raise GlobalContextNotSet()
    _GLOBAL_CONTEXT.global_verbosity_level = int(level)


def get_verbosity_level() -> int:
    """Get the current global verbosity level. The verbosity level's meaning
    is determined by the application's interpretation of it.

    Raises:
        GlobalContextNotSet: Raised if :func:`global_init` has not been called.

    Returns:
        int: The verbosity level.
    """
    global_init()
    if not _GLOBAL_CONTEXT:
        raise GlobalContextNotSet()
    return _GLOBAL_CONTEXT.global_verbosity_level


def _global_init_subprocess(
    global_context_from_parent: _MultiprocessGlobalContext
):
    """Called as part of subprocess initialization.

    Args:
        global_context_from_parent (_type_): _description_
    """
    global _GLOBAL_CONTEXT
    _GLOBAL_CONTEXT = global_context_from_parent
    _connect_root_logger_to_global_logging_queue()


def get_process_pool_exec_init_func(
) -> Callable[[_MultiprocessGlobalContext], None]:
    """Get the function to pass as `initializer' to
    `concurrent.futures.ProcessPoolExecutor`.

    This function would typically be used along with the
    :func:`get_process_pool_exec_init_args` function when initializing a
    `concurrent.futures.ProcessPoolExecutor`.

    Example usage:

    .. code-block:: python

        ppe = ProcessPoolExecutor(
            max_workers=max_workers_each,
            initializer=get_process_pool_exec_init_func():,
            initargs=get_process_pool_exec_init_args(),
        )

    Returns:
        :obj:`Callable`: An initialization function called by a subprocess.
    """
    return _global_init_subprocess


def get_process_pool_exec_init_args(
) -> tuple[_MultiprocessGlobalContext]:
    """Get the value to pass as `initargs' to
    `concurrent.futures.ProcessPoolExecutor`.

    This function would typically be used along with the
    :func:`get_process_pool_exec_init_func` function when initializing a
    `concurrent.futures.ProcessPoolExecutor`.

    Example usage:

    .. code-block:: python

        ppe = ProcessPoolExecutor(
            max_workers=max_workers_each,
            initializer=get_process_pool_exec_init_func():,
            initargs=get_process_pool_exec_init_args(),
        )

    Returns:
        object: An argument for the subprocess initialization function.
            The caller need not concern itself with its type/context.
    """
    return (_GLOBAL_CONTEXT,)


def _track_logging_handler(*handlers):
    _CREATED_LOGGING_HANDLERS.update(handlers)


def _untrack_logging_handler(*handlers):
    untracked = []
    for h in handlers:
        if h in _CREATED_LOGGING_HANDLERS:
            untracked.append(h)
            _CREATED_LOGGING_HANDLERS.remove(h)
    return untracked


def _start_global_queue_listener(*logging_handlers):
    global _PARENT_QUEUE_LISTENER
    if not _GLOBAL_CONTEXT:
        raise GlobalContextNotSet(f"global_context not initialized.")
    if _PARENT_QUEUE_LISTENER:
        raise QueueListenerAlreadyStarted(
            f"parent_queue_listener already started."
        )
    _PARENT_QUEUE_LISTENER = logging.handlers.QueueListener(
        _GLOBAL_CONTEXT.global_logging_queue, *logging_handlers
    )
    _track_logging_handler(*logging_handlers)
    _PARENT_QUEUE_LISTENER.start()


def _stop_global_queue_listener():
    global _PARENT_QUEUE_LISTENER
    if not _PARENT_QUEUE_LISTENER:
        raise QueueListenerNotStarted(f"parent_queue_listener not started.")
    p = _PARENT_QUEUE_LISTENER

    untracked_handlers = _untrack_logging_handler(*p.handlers)

    _PARENT_QUEUE_LISTENER = None
    p.stop()
    p.handlers = ()

    return untracked_handlers


def switch_to_non_queued_logging():
    """Switch to non-queued logging which is also logging without latency which
    is useful for certain commands that have the potential to interact with the
    user at the command-line, where logging latency can be problematic with
    interleaved with non-logging I/O.
    """
    # pylint: disable=broad-except
    try:
        handlers = _stop_global_queue_listener()
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
    """Remove `logging.StreamHandler` handlers from the root logger.

    This can be used for re-initializing logging and it can help to avoid
    double-logging output to console by blindly adding handlers without removing
    existing handlers.
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
    """Remove any handlers specifically added by this module, but not any
    others.

    This can be used for re-initializing logging.
    """
    all_loggers = [logging.root] + [
        logging.getLogger(name)
        for name in logging.root.manager.loggerDict  # pylint: disable=no-member
    ]
    for l in all_loggers:
        for h in l.handlers:
            if h in _CREATED_LOGGING_HANDLERS:
                l.handlers.remove(h)
                _untrack_logging_handler(h)


def initialize_logging(
    logfile,
    loglevel,
    verbosity_level,
    log_console_detail
):
    """Initialize global multiprocessing shared logging.

    Once initialized, this parent process, and all its subprocesses, will
    ultimately log to this parent process's handler, typically outputting to the
    console and, if specified on the command line, a log file.

    Use :func:`deinitialize_logging` to de-initialize before the application
    exits.

    Args:
        logfile (str): The path to a log file, if any. If None, do not log
            to file.
        loglevel (str): The Python logging level.
        verbosity_level (int): The verbosity level. This should default to zero.
            The meaning of added verbosity for values greater than zero is
            app-defined by the process/subprocess calling
            :func:`get_verbosity_level` and taking desired action, often to log
            more than otherwise at the given Python logging level.
        log_console_detail (bool): If True, prefix console output with detailed
            timestamps and other information otherwise relegated to the logfile
            output.

    Raises:
        GlobalContextNotSet: The `global_init` or subprocess initialization
            function :func:`get_process_pool_exec_init_func` was not
            specified/called.
    """
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
        file_handler = logging.FileHandler(
            filename=logfile,
            encoding="utf-8"
        )
        file_handler.setLevel(file_log_level)
        file_handler.setFormatter(detailed_formatter)
        handlers += (file_handler,)

    _start_global_queue_listener(*handlers)


def deinitialize_logging():
    """Teardown logging initialized via :func:`initialize_logging`.

    This is often called as part of process exit/cleanup.
    """
    _stop_global_queue_listener()
    remove_created_logging_handlers()


def initialize_logging_basic():
    """Setup basic logging without having to specify any detailed
    setup parameters.

    Command line arguments often specify the details of the type of
    logging/verbosity desired by a user. In such cases, this can be
    used early during app statrtup until such time as full logging
    setup can proceed.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
