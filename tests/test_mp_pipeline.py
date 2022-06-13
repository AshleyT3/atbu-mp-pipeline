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

# pylint: disable=unused-argument

import os
import time
from pathlib import Path
from random import randint
import logging
import concurrent.futures
from concurrent.futures import ALL_COMPLETED, Future, ProcessPoolExecutor
from turtle import st
import pytest

from atbu.mp_pipeline.exception import PipeConnectionAlreadyEof
from atbu.mp_pipeline.mp_pipeline import (
    MultiprocessingPipeline,
    PipeConnectionIO,
    PipelineStage,
    SubprocessPipelineStage,
    ThreadPipelineStage,
    PipelineWorkItem,
)
from .common_helpers import establish_random_seed

LOGGER = logging.getLogger(__name__)


def setup_module(module):
    pass


def teardown_module(module):
    pass


def queue_worker_func(parm_top_secret, parent_pid):
    assert parent_pid != os.getpid()
    return (
        parent_pid,
        os.getpid(),
        parm_top_secret,
    )


def int_stage0(wi: PipelineWorkItem):
    wi.user_obj[0] = 100
    return wi


def int_stage1(wi: PipelineWorkItem):
    wi.user_obj[0] = wi.user_obj[0] * 2
    wi.user_obj[1] = "stage1"
    return wi


def int_stage2(wi: PipelineWorkItem):
    wi.user_obj[0] = wi.user_obj[0] * 2
    wi.user_obj[2] = f"stage2: got this from parent: {wi.user_obj['parent']}"
    return wi


def always_yes(wi: PipelineWorkItem):
    return True


def test_mp_pipeline_basic(tmp_path: Path):
    sp = MultiprocessingPipeline(
        name="test_mp_pipeline_basic",
        stages=[
            SubprocessPipelineStage(
                fn_determiner=always_yes,
                fn_worker=int_stage0,
            ),
            SubprocessPipelineStage(
                fn_determiner=always_yes,
                fn_worker=int_stage1,
            ),
            SubprocessPipelineStage(
                fn_determiner=always_yes,
                fn_worker=int_stage2,
            ),
        ],
    )

    d = {}
    d["parent"] = "This is from parent"
    wi = PipelineWorkItem(d)
    f = sp.submit(wi)
    r_wi = f.result()
    assert wi == r_wi
    assert not wi.is_failed
    assert wi.user_obj["parent"] == d["parent"]
    assert wi.user_obj[1] == "stage1"
    assert wi.user_obj[2] == "stage2: got this from parent: This is from parent"
    assert wi.user_obj[0] == 400
    sp.shutdown()
    assert sp.was_graceful_shutdown


class LargePipelineWorkItem(PipelineWorkItem):
    def __init__(self) -> None:
        super().__init__(user_obj=self)
        self.is_ok = True
        self.num = 0
        self.pid = os.getpid()


class LargePipelineStage(SubprocessPipelineStage):
    def __init__(self) -> None:
        super().__init__()

    def is_for_stage(self, pwi: LargePipelineWorkItem) -> bool:
        pwi.is_ok = not pwi.is_ok
        return not pwi.is_ok

    def perform_stage_work(
        self,
        pwi: LargePipelineWorkItem,
        **kwargs,
    ):
        pwi.num += 1
        return pwi


def test_mp_pipeline_large(tmp_path: Path):
    stages = 100
    sp = MultiprocessingPipeline(
        max_simultaneous_work_items=min(os.cpu_count(), 15),
        name="test_mp_pipeline_large",
    )
    for i in range(stages):
        sp.add_stage(stage=LargePipelineStage())
    wi = LargePipelineWorkItem()
    f = sp.submit(wi)
    r_wi: PipelineWorkItem = f.result()
    assert wi == r_wi
    if r_wi.exceptions is not None:
        # Should be succesful.
        # raise the the first exception so pytest displays its message.
        raise r_wi.exceptions[0]
    assert not r_wi.is_failed
    assert r_wi.is_ok
    assert r_wi.num == 50
    sp.shutdown()
    assert sp.was_graceful_shutdown


class MixedPipelineSubprocessStage(PipelineStage):
    def __init__(self) -> None:
        super().__init__()

    @property
    def is_subprocess(self):
        return True

    def is_for_stage(self, pwi: LargePipelineWorkItem) -> bool:
        return True

    def perform_stage_work(
        self,
        pwi: LargePipelineWorkItem,
        **kwargs,
    ):
        assert pwi.pid != os.getpid()
        pwi.num += 1
        return pwi


def perform_thread_stage_work(
    pwi: LargePipelineWorkItem,
    **kwargs,
):
    assert pwi.pid == os.getpid()
    pwi.num += 1
    return pwi


def test_mp_pipeline_large_mixed(tmp_path: Path):
    sp = MultiprocessingPipeline(
        name="test_mp_pipeline_large_mixed",
        max_simultaneous_work_items=min(os.cpu_count(), 15),
    )
    for _ in range(10):
        sp.add_stage(stage=MixedPipelineSubprocessStage())
        sp.add_stage(
            stage=ThreadPipelineStage(
                fn_determiner=lambda pwi: True,
                fn_worker=perform_thread_stage_work,
            )
        )
    wi = LargePipelineWorkItem()
    f = sp.submit(wi)
    r_wi: PipelineWorkItem = f.result()
    assert wi == r_wi
    if r_wi.exceptions is not None:
        # Should be succesful.
        # raise the first exception in the list so pytest displays its message.
        raise r_wi.exceptions[0]
    assert not r_wi.is_failed
    assert r_wi.is_ok
    assert r_wi.num == 20
    assert r_wi.pid == os.getpid()
    sp.shutdown()
    assert sp.was_graceful_shutdown


def gather_func(idnum, pr: PipeConnectionIO):
    print(f"ENTER id={idnum} pid={os.getpid()}")
    results = []
    while not pr.eof:
        results.append(pr.read())
    assert pr.read() == bytes()
    print(f"EXIT id={idnum} {os.getpid()} len={len(results)}")
    pr.close()
    return results


def test_pipe_io_connection_basic(tmp_path: Path):
    ppe = ProcessPoolExecutor()
    pr, pw = PipeConnectionIO.create_reader_writer_pair()
    fut = ppe.submit(gather_func, 0, pr)
    expected = [
        "abc".encode(),
        "123".encode(),
        "the end".encode(),
    ]
    for i, e in enumerate(expected):
        if i < len(expected) - 1:
            num_written = pw.write(e)
            assert num_written == len(e)
        else:
            num_written = pw.write_eof(e)
            assert num_written == len(e)
    with pytest.raises(PipeConnectionAlreadyEof):
        pw.write_eof(b"xyz")
    r = fut.result(timeout=60)
    assert len(r) == 3
    assert r == expected


def test_pipe_io_connection_many(tmp_path: Path):
    seed = bytes([0xDB, 0x9E, 0xEC, 0x45])
    seed = establish_random_seed(tmp_path=tmp_path, random_seed=seed)
    print(f"Seed={seed.hex(' ')}")
    print(f"Parent pid={os.getpid()}")
    total_conn = 50
    ppe = ProcessPoolExecutor(max_workers=total_conn)
    rw_fut_conn: list[tuple[Future, PipeConnectionIO]] = []
    for i in range(total_conn):
        pr, pw = PipeConnectionIO.create_reader_writer_pair()
        fut = ppe.submit(gather_func, i, pr)
        rw_fut_conn.append(
            (
                i,
                fut,
                pw,
            )
        )
        print(f"#{len(rw_fut_conn)-1} submitted.")

    expected = [
        ("abc" * 1024 * 1024 * 7).encode(),
        ("123" * 1024 * 1024 * 3).encode(),
        ("the end" * 100).encode(),
    ]

    print(f"Begin writing...")

    process_writing = list(rw_fut_conn)
    while len(process_writing) > 0:
        idx = randint(0, len(process_writing) - 1)
        idnum, fut, pw = process_writing[idx]
        is_done = fut.done()
        is_running = fut.running()
        if not is_running:
            time.sleep(0.010)
            continue
        print(f"id={idnum}: is_done={is_done} is_running={is_running} {str(fut)}")
        for i, e in enumerate(expected):
            if i < len(expected) - 1:
                num_written = pw.write(e)
                assert num_written == len(e)
            else:
                num_written = pw.write_eof(e)
                assert num_written == len(e)
        with pytest.raises(PipeConnectionAlreadyEof):
            pw.write_eof(b"xyz")
        del process_writing[idx]

    print(f"Waiting for Futures...")
    while len(rw_fut_conn) > 0:
        idx = randint(0, len(rw_fut_conn) - 1)
        idnum, fut, pw = rw_fut_conn[idx]
        is_done = fut.done()
        is_running = fut.running()
        print(f"BEGIN WAIT: id={idnum}: is_done={is_done} is_running={is_running}")
        assert is_running or is_done
        r = fut.result(timeout=120)
        print(f"END WAIT: id={idnum}: is_done={is_done} is_running={is_running}")
        assert len(r) == 3
        assert r == expected
        del rw_fut_conn[idx]


class ProducerConsumerWorkItem(PipelineWorkItem):
    def __init__(self, demo_pipe_io_wrapper) -> None:
        super().__init__(auto_copy_attr=False)
        self.demo_pipe_io_wrapper = demo_pipe_io_wrapper
        self.producer_data = None # What producer sent.
        self.producer_bytes_written = None
        self.consumer_data = None # What consumer received
        self.last_observed_stage_number = -1 # For validation of stage num order.

    def stage_complete(
        self,
        stage_num: int,  # pylint: disable=unused-argument
        wi: "PipelineWorkItem",  # pylint: disable=unused-argument
        ex: Exception,
    ):
        super().stage_complete(
            stage_num=stage_num,
            wi=wi,
            ex=ex,
        )

        assert self.last_observed_stage_number < stage_num
        self.last_observed_stage_number = stage_num

        if not wi.is_failed:
            if stage_num == 0:
                self.producer_data = wi.producer_data
                self.producer_bytes_written = wi.producer_bytes_written
            elif stage_num == 1:
                self.consumer_data = wi.consumer_data


class ProducerPipelineSubprocessStage(SubprocessPipelineStage):
    def __init__(self) -> None:
        super().__init__()

    def is_for_stage(self, pwi: ProducerConsumerWorkItem) -> bool:
        return True # Yes, we want to see all work items in this stage.

    @property
    def is_pipe_with_next_stage(self):
        """Return True to indicate we want this stage and the next one
        to run in parallel, where this stage is the producer feeding a
        pipeline-supplied pipe, and the next stage is consuming from that
        same pipe (on the reader side).
        """
        return True

    def perform_stage_work(
        self,
        pwi: ProducerConsumerWorkItem,
        **kwargs,
    ):
        if not isinstance(pwi, ProducerConsumerWorkItem):
            raise ValueError(
                f"Pipeline gave us unexpected work item."
            )
        pwi.producer_data = os.urandom(10)
        if pwi.demo_pipe_io_wrapper:
            # PipeConnectionIO wraps the multiprocessing Pipe, providing
            # an io.RawIOBase interface (with limitations... i.e., seek is
            # not supported).
            with PipeConnectionIO(pwi.pipe_conn, is_write=True) as pipe_io:
                pwi.producer_bytes_written = pipe_io.write(pwi.producer_data)
        else:
            # Just use the pipe connection directly.
            pwi.pipe_conn.send_bytes(pwi.producer_data)
            pwi.producer_bytes_written = len(pwi.producer_data)
        return pwi


class ConsumerPipelineSubprocessStage(SubprocessPipelineStage):
    def __init__(self) -> None:
        super().__init__()

    def is_for_stage(self, pwi: ProducerConsumerWorkItem) -> bool:
        return True # Yes, we want to see all work items in this stage.

    def perform_stage_work(
        self,
        pwi: ProducerConsumerWorkItem,
        **kwargs,
    ):
        if pwi.demo_pipe_io_wrapper:
            # PipeConnectionIO wraps the multiprocessing Pipe, providing
            # an io.RawIOBase interface (with limitations... i.e., seek is
            # not supported).
            with PipeConnectionIO(pwi.pipe_conn, is_write=False) as pipe_io:
                pwi.consumer_data = pipe_io.read()
        else:
            # Just use the pipe connection directly.
            pwi.consumer_data = pwi.pipe_conn.recv_bytes()
        return pwi

def test_mp_pipeline_producer_consumer(tmp_path: Path):
    mpp = MultiprocessingPipeline(
        name="test_mp_producer_oncsoler",
        stages=[
            ProducerPipelineSubprocessStage(),
            ConsumerPipelineSubprocessStage()
        ]
    )
    wil = [
        ProducerConsumerWorkItem(demo_pipe_io_wrapper=True),
        ProducerConsumerWorkItem(demo_pipe_io_wrapper=False)
    ]
    fut = [mpp.submit(wi) for wi in wil]
    done, not_done = concurrent.futures.wait(fs=fut, return_when=ALL_COMPLETED)
    assert len(done) == 2
    for f in done:
        r_wi: ProducerConsumerWorkItem = f.result()
        assert r_wi.last_observed_stage_number == 1
        assert not r_wi.is_failed
        assert r_wi.producer_bytes_written == 10
        assert r_wi.producer_data == r_wi.consumer_data
    mpp.shutdown()
    assert mpp.was_graceful_shutdown
