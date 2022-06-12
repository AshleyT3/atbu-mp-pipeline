# Python Multiprocessing Pipeline
## Overview
The atbu.mp_pipeline package uses Python multiprocessing capabilities to support multi-stage pipeline capabilities, including support for dual-stage parallel execution of a producer and consumer stages, automatically providing each of those stages with pipe connection, allowing them share what is being produced/consumed.

The atbu.mp_pipeline package is currently used by the following project for supporting a backup compression pipeline stage:
- [ATBU Backup & Persistent File Information](https://github.com/AshleyT3/atbu) utility package (atbu-pkg).

Documentation: https://atbu-mp-pipeline.readthedocs.io/en/latest/

## Setup
To install atbu-common-pkg:

```
pip install atbu-mp-pipeline-pkg
```

See below for a few examples. See source code for other packages mentioned above and for additional details and usage information.

## Examples

### Basic/Simple Pipeline Example

```
import os
from multiprocessing import freeze_support
from atbu.mp_pipeline.mp_pipeline import (
    MultiprocessingPipeline,
    SubprocessPipelineStage,
    PipelineWorkItem,
)

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

def main():
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
    wi = PipelineWorkItem(d.copy())
    f = sp.submit(wi)
    r_wi: PipelineWorkItem = f.result()
    if not wi.is_failed:
        assert wi == r_wi # On success, should be equal.
        assert wi.user_obj["parent"] == d["parent"] # Should not change.
        # Should have values as set by stages...
        assert wi.user_obj[0] == 400
        assert wi.user_obj[1] == "stage1"
        assert wi.user_obj[2] == "stage2: got this from parent: This is from parent"
        print(f"Work item completed successfully:")
        print(f"  wi.user_obj[0]={wi.user_obj[0]}")
        print(f"  wi.user_obj[1]={wi.user_obj[1]}")
        print(f"  wi.user_obj[2]={wi.user_obj[2]}")
    else:
        print(f"Something did not go as planned:")
        for ex in r_wi.exceptions:
            print(f" ex={ex}")
    sp.shutdown()
    assert sp.was_graceful_shutdown

if __name__ == '__main__':
    freeze_support()
    main()
```

**Output:**
```
Work item completed successfully:
  wi.user_obj[0]=400
  wi.user_obj[1]=stage1
  wi.user_obj[2]=stage2: got this from parent: This is from parent
```

### Large Pipeline Example

```
import os
from multiprocessing import freeze_support
from atbu.mp_pipeline.mp_pipeline import (
    MultiprocessingPipeline,
    SubprocessPipelineStage,
    PipelineWorkItem,
)

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
        # Example of stage rejecting its chance to run the work item.
        # Say "no" to every other request.
        pwi.is_ok = not pwi.is_ok
        return not pwi.is_ok

    def perform_stage_work(
        self,
        pwi: LargePipelineWorkItem,
        **kwargs,
    ):
        pwi.num += 1
        return pwi

def main():
    stages = 100
    mpp = MultiprocessingPipeline(
        max_simultaneous_work_items=min(os.cpu_count(), 15),
        name="test_mp_pipeline_large",
    )
    for _ in range(stages):
        mpp.add_stage(stage=LargePipelineStage())
    print(f"Pipeline has {mpp.num_stages} stages.")
    wi = LargePipelineWorkItem()
    f = mpp.submit(wi)
    r_wi: PipelineWorkItem = f.result()
    if not r_wi.is_failed:
        assert wi == r_wi
        assert r_wi.is_ok
        assert r_wi.num == 50
        print(f"Work item completed successfully:")
        print(f"  r_wi.is_ok={r_wi.is_ok}")
        print(f"  r_wi.pid={r_wi.pid}")
    else:
        if r_wi.exceptions is not None:
            print(f"Something did not go as planned:")
            for ex in r_wi.exceptions:
                print(f" ex={ex}")
    mpp.shutdown()
    assert mpp.was_graceful_shutdown

if __name__ == '__main__':
    freeze_support()
    main()
```

**Output:**

```
Pipeline has 100 stages.
Work item completed successfully:
  r_wi.is_ok=True
  r_wi.pid=8204
  r_wi.num=50
```

### Mixed Pipeline Example

```
import os
from multiprocessing import freeze_support
from atbu.mp_pipeline.mp_pipeline import (
    MultiprocessingPipeline,
    PipelineStage,
    SubprocessPipelineStage,
    ThreadPipelineStage,
    PipelineWorkItem,
)

class LargePipelineWorkItem(PipelineWorkItem):
    def __init__(self) -> None:
        super().__init__(user_obj=self)
        self.is_ok = True
        self.num = 0
        self.pid = os.getpid()


class MixedPipelineSubprocessStage(PipelineStage):
    def __init__(self) -> None:
        super().__init__()

    @property
    def is_subprocess(self):
        return True

    def is_for_stage(self, pwi: LargePipelineWorkItem) -> bool:
        return True # Yes, this stage wants all work items.

    def perform_stage_work(
        self,
        pwi: LargePipelineWorkItem,
        **kwargs,
    ):
        # Run the work item.
        assert pwi.pid != os.getpid() # Subprocess should have different pid.
        pwi.num += 1
        return pwi


def perform_thread_stage_work(
    pwi: LargePipelineWorkItem,
    **kwargs,
):
    assert pwi.pid == os.getpid() # Thread should have same process.
    pwi.num += 1
    return pwi

def main():
    mpp = MultiprocessingPipeline(
        name="mp_pipeline_large_mixed",
        max_simultaneous_work_items=min(os.cpu_count(), 15),
    )
    for _ in range(10):
        # Add a stage using our derived-class pipeline stage.
        mpp.add_stage(stage=MixedPipelineSubprocessStage())
        # Add a stage using the library's thread pipeline stage,
        # where we specify the callable to call for both asking
        # the pipeline if it wants to run a given work item, and
        # and other to actually do the work.
        mpp.add_stage(
            stage=ThreadPipelineStage(
                fn_determiner=lambda pwi: True, # Run all work items.
                fn_worker=perform_thread_stage_work, # Call this to run them.
            )
        )
    print(f"Pipeline has {mpp.num_stages} stages.")
    wi = LargePipelineWorkItem()
    f = mpp.submit(wi)
    r_wi: PipelineWorkItem = f.result()
    if not r_wi.is_failed:
        assert wi == r_wi
        assert not r_wi.is_failed
        assert r_wi.is_ok
        assert r_wi.num == 20
        assert r_wi.pid == os.getpid()
        print(f"Work item completed successfully:")
        print(f"  r_wi.num={r_wi.num}")
        print(f"  r_wi.pid={r_wi.pid}")
    else:
        if r_wi.exceptions is not None:
            print(f"Something did not go as planned:")
            for ex in r_wi.exceptions:
                print(f" ex={ex}")
    mpp.shutdown()
    assert mpp.was_graceful_shutdown

if __name__ == '__main__':
    freeze_support()
    main()
```

**Output:**

```
Pipeline has 20 stages.
Work item completed successfully:
  r_wi.num=20
  r_wi.pid=18068
```

### Dual-stage Producer/Consumer Example

```
import os
from multiprocessing import freeze_support
import concurrent.futures
from atbu.mp_pipeline.mp_pipeline import (
    MultiprocessingPipeline,
    SubprocessPipelineStage,
    PipelineWorkItem,
    PipeConnectionIO,
)

class ProducerConsumerWorkItem(PipelineWorkItem):
    def __init__(self, demo_pipe_io_wrapper) -> None:
        super().__init__(auto_copy_attr=False)
        self.demo_pipe_io_wrapper = demo_pipe_io_wrapper
        self.producer_data = None # What producer sent.
        self.producer_bytes_written = None
        self.consumer_data = None # What consumer received

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
        try:
            if not isinstance(pwi, ProducerConsumerWorkItem):
                raise ValueError(
                    f"Producer: Pipeline gave us unexpected work item."
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
        except Exception:
            if not pwi.pipe_conn.closed:
                pwi.pipe_conn.close()
            raise


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
        try:
            if not isinstance(pwi, ProducerConsumerWorkItem):
                raise ValueError(
                    f"Consumer: Pipeline gave us unexpected work item."
                )
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
        except Exception:
            if not pwi.pipe_conn.closed:
                pwi.pipe_conn.close()
            raise

def main():
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
    done, _ = concurrent.futures.wait(
        fs=fut,
        return_when=concurrent.futures.ALL_COMPLETED
    )
    assert len(done) == 2
    for i, f in enumerate(done):
        r_wi: ProducerConsumerWorkItem = f.result()
        if not r_wi.is_failed:
            assert r_wi.producer_bytes_written == 10
            assert r_wi.producer_data == r_wi.consumer_data
            print(f"Success for #{i}:")
            print(f"  {i}: num_bytes={r_wi.producer_bytes_written}")
            print(f"  {i}: p_bytes={r_wi.producer_data.hex(' ')}")
            print(f"  {i}: c_bytes={r_wi.consumer_data.hex(' ')}")
        else:
            if r_wi.exceptions is not None:
                print(f"Something did not go as planned for #{i}:")
                for ex in r_wi.exceptions:
                    print(f"  {i}: Bad thing happened: {ex}")
    mpp.shutdown()
    assert mpp.was_graceful_shutdown

if __name__ == '__main__':
    freeze_support()
    main()
```

**Output:**

```
Success for #0:
  0: num_bytes=10
  0: p_bytes=76 d4 32 f0 4f 3f 31 30 19 00
  0: c_bytes=76 d4 32 f0 4f 3f 31 30 19 00
Success for #1:
  1: num_bytes=10
  1: p_bytes=34 d6 5c d0 be 82 62 c3 5d 61
  1: c_bytes=34 d6 5c d0 be 82 62 c3 5d 61
  ```
