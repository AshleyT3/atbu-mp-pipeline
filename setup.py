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
r"""setup.py
"""

from pathlib import Path
import setuptools

# read the contents of your README file
this_dir = Path(__file__).parent.absolute()
readme_md_path = this_dir / "README.md"
long_description = readme_md_path.read_text()

setuptools.setup(
    name="atbu-mp-pipeline-pkg",
    version="0.0.9",
    author="Ashley R. Thomas",
    author_email="ashley.r.thomas.701@gmail.com",
    description= (
        "ATBU atbu.mp_pipeline package, a multiprocessing work item pipeline."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/AshleyT3/atbu-mp-pipeline",
    project_urls={
        "Bug Tracker": "https://github.com/AshleyT3/atbu-mp-pipeline/issues",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    package_dir={"": "src"},
    packages=setuptools.find_namespace_packages(where="src"),
    python_requires=">=3.9",
    install_requires=[
        "atbu-common-pkg >= 0.0.3",
    ]
)
