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
r"""ATBU mp_pipeline exceptions.
"""

from atbu.common.exception import AtbuException


class GlobalContextNotSet(AtbuException):
    """Global multiprocessing context has not been initialized.

    The global context currently relates to global state shared
    by a parent and all its subprocesses, currently used for
    initialization, configuration, use of global logging, related
    listeners, etc.

    A parent process initializes global context by calling the
    following:

    .. code-block:: python

        global_init()

    A subprocess initializes global context by having the parent
    specify the following on submission:

    .. code-block:: python

        get_process_pool_exec_init_func()
        get_process_pool_exec_init_args()

    Example:

    .. code-block:: python

        ppe = ProcessPoolExecutor(
            max_workers=max_workers_each,
            initializer=get_process_pool_exec_init_func():,
            initargs=get_process_pool_exec_init_args(),
        )

    Args:
        message (str): Human readable string describing the exception.
        cause (:obj:`object`, optional): Object relating to cause.

    Attributes:
        message (str): Human readable string describing the exception.
        cause (:obj:`object`, optional): Object relating to cause.
    """
    def __init__(self, message: str = None, cause=None):
        self._cause = cause
        super().__init__(message=message, cause=cause)


class PipelineResultIsNotPipelineWorkItem(AtbuException):
    def __init__(self, message: str = None, cause=None):
        self._cause = cause
        super().__init__(message=message, cause=cause)


class PipelineLastStageError(AtbuException):
    def __init__(self, message: str = None, cause=None):
        self._cause = cause
        super().__init__(message=message, cause=cause)


class PipelineFutureStuckPendingError(AtbuException):
    def __init__(self, message: str = None, cause=None):
        self._cause = cause
        super().__init__(message=message, cause=cause)


class InvalidPipeConnectionMessage(AtbuException):
    def __init__(self, message: str = None, cause=None):
        self._cause = cause
        super().__init__(message=message, cause=cause)


class PipeConnectionAlreadyEof(AtbuException):
    def __init__(self, message: str = None, cause=None):
        self._cause = cause
        super().__init__(message=message, cause=cause)
