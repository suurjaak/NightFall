# -*- coding: utf-8 -*-
"""
Setup.py for NightFall.

------------------------------------------------------------------------------
This file is part of NightFall - screen color dimmer for late hours.
Released under the MIT License.

@author      Erki Suurjaak
@created     28.01.2022
@modified    01.02.2022
------------------------------------------------------------------------------
"""
import os
import re
import sys

import setuptools

ROOTPATH  = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOTPATH, "src"))

from nightfall import conf


PACKAGE = conf.Name.lower()


def readfile(path):
    """Returns contents of path, relative to current file."""
    root = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(root, path)) as f: return f.read()

def get_description():
    """Returns package description from README."""
    LINK_RGX = r"\[([^\]]+)\]\(([^\)]+)\)"  # 1: content in [], 2: content in ()
    linkify = lambda s: "#" + re.sub(r"[^\w -]", "", s).lower().replace(" ", "-")
    # Unwrap local links like [Page link](#page-link) and [LICENSE.md](LICENSE.md)
    repl = lambda m: m.group(1 if m.group(2) in (m.group(1), linkify(m.group(1))) else 0)
    return re.sub(LINK_RGX, repl, readfile("README.md"))


setuptools.setup(
    name                 = PACKAGE,
    version              = conf.Version,
    description          = conf.Title,
    url                  = "https://github.com/suurjaak/NightFall",

    author               = "Erki Suurjaak",
    author_email         = "erki@lap.ee",
    license              = "MIT",
    platforms            = ["any"],
    keywords             = "brightness color-temperature darkmode dark-mode desktop eye-strain"
                           "flux gamma-ramps night nightmode night-mode schedule screen-brightness",

    install_requires     = ["appdirs", "wxPython>=4.0"],
    entry_points         = {"gui_scripts": ["{0} = {0}.main:run".format(PACKAGE)]},

    package_dir          = {"": "src"},
    packages             = [PACKAGE],
    include_package_data = True, # Use MANIFEST.in for data files
    classifiers          = [
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: End Users/Desktop",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: Unix",
        "Operating System :: MacOS",
        "Topic :: Desktop Environment",
        "Topic :: Multimedia :: Graphics",
        "Topic :: Utilities",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
    ],

    long_description_content_type = "text/markdown",
    long_description = get_description(),
)
