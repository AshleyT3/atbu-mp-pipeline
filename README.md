# atbu-mp-pipeline-pkg (atbu.mp_pipeline) package
## Overview
The atbu.mp_pipeline package uses Python multiprocessing capabilities to support multi-stage pipeline capabilities, including support for dual-stage parallel execution of a producer and consumer stages, automatically providing each of those stages with pipe connection, allowing them share what is being produced/consumed.

The atbu.mp_pipeline package is currently used by the following project for supporting a backup compression pipeline stage:
- [ATBU Backup & Persistent File Information](https://github.com/AshleyT3/atbu) utility package (atbu-pkg).

## Setup
To install atbu-common-pkg:

```
pip install atbu-mp-pipeline-pkg
```

See source code for this and the other packages mentioned above for details and usage information.
