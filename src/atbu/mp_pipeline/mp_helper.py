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
r"""Multiprocessing helpers.
"""

from atbu.common.exception import InvalidFunctionArgument

from concurrent import futures
import logging


def pending_futures(fs):
    return [f for f in fs if not f.done()]


def num_pending_futures(fs):
    return len(pending_futures(fs))


def wait_futures_to_regulate(fs, max_allowed_pending):
    if max_allowed_pending < 1:
        raise InvalidFunctionArgument
    fs = set(fs)
    num_pending = num_pending_futures(fs)
    while num_pending >= max_allowed_pending:
        logging.debug(
            f"wait_futures_to_regulate: waiting: "
            f"max_allowed_pending={max_allowed_pending} "
            f"num_pending={num_pending}"
        )
        _, fs = futures.wait(fs=fs, return_when=futures.FIRST_COMPLETED)
        num_pending = num_pending_futures(fs)
    logging.debug(
        f"wait_futures_to_regulate: no wait: "
        f"max_allowed_pending={max_allowed_pending} "
        f"num_pending={num_pending}"
    )
