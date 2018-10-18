#! /usr/bin/env python
#
from g2ana.version import version
import os

srcdir = os.path.dirname(__file__)

try:
    from setuptools import setup

except ImportError:
    from distutils.core import setup

setup(
    name = "g2ana",
    version = version,
    author = "Software Division, Subaru Telescope, NAOJ",
    author_email = "ocs@naoj.org",
    description = ("Analysis menu for Subaru on-site data analysis."),
    license = "BSD",
    keywords = "subaru, telescope, observation, data, analysis",
    url = "http://naojsoft.github.com/g2ana",
    packages = ['g2ana',
                'g2ana.icons',
                ],
    package_data = {'g2ana.icons':['*.png']},
    scripts = ['scripts/anamenu', 'scripts/datasink', 'scripts/cleanup_fits'],
    classifiers = [
        "License :: OSI Approved :: BSD License",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX",
        "Topic :: Scientific/Engineering :: Astronomy",
    ],
)
