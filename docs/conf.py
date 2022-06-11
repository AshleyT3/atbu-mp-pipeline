# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#

import sys
import os
import pathlib
import subprocess

our_dir = pathlib.Path(__file__).parent
sys.path.insert(0, (our_dir / "src/atbu/mp_pipeline").resolve().as_posix())
static_subdir = our_dir / "_static"
static_subdir.mkdir(exist_ok=True)

# Remove apidocs/* files which are not needed.
# This avoids warnings without :orhpan:.
apidocs_subdir = our_dir / "apidocs"
apidocs_modules_rst_path = apidocs_subdir / "modules.rst"
apidocs_atbu_rst_path = apidocs_subdir / "atbu.rst"
apidocs_modules_rst_path.unlink(missing_ok=True)
apidocs_atbu_rst_path.unlink(missing_ok=True)

# Detect if we are running on read the docs
is_running_on_rtd = os.environ.get('READTHEDOCS', '').lower() == 'true'
if is_running_on_rtd:
    cmd = "sphinx-apidoc -d 4 ../src/atbu -o apidocs/ --implicit-namespaces"
    subprocess.call(cmd, shell=True)

# -- Project information -----------------------------------------------------

project = 'atbu-mp-pipeline'
copyright = '2022, Ashley R. Thomas'
author = 'Ashley R. Thomas'


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.autosummary',
    'myst_parser',
]
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'classic'
#html_theme = "alabaster"
html_theme_options = {
    "codebgcolor": "#ECECEC",
    "body_min_width": "60%"
}
# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']
# Classic causes the following which causes the left column
# field labels for parm/return to have pinkish background.
# Overriding to have white matching the field values.
# th, dl.field-list > dt {
#     background-color: #ede;
# }
html_css_files = [
    'css/custom.css',
]

# Napoleon settings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc  = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
