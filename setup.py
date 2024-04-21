#!/usr/bin/env python
# -*- coding: utf-8 -*-
import io
import re
from collections import OrderedDict

from setuptools import setup

with io.open('README.md', 'rt', encoding='utf8') as f:
    readme = f.read()

with io.open('mymoneyvisualizer/__init__.py', 'rt', encoding='utf8') as f:
    version = re.search(r'__version__ = \'(.*?)\'', f.read()).group(1)

setup(
    name='MyMoneyVisualizer',
    version=version,
    license='MIT',
    author='Thomas Nikodem',
    description='A simple tool to visualize your income and expenses',
    long_description=readme,
    packages=['mymoneyvisualizer'],
    include_package_data=True,
    zip_safe=False,
    platforms='any',
    python_requires='>=3.10',
    install_requires=[
        'numpy==1.26.*',
        'pandas==2.2.*',
        'pyyaml==6.0.*',
        'pyqt6==6.6.*',
        'pyqtgraph==0.13.*',
        'pyqt6-multiselect-combobox==1.1.*',
    ],
    extras_require={
        'dev': [
            'pytest==8.1.*',
            'pytest-qt==4.4.*',
            'pytest-cov==5.0.*',
        ]
    },
    entry_points={
        'console_scripts': [
            'mmv = mymoneyvisualizer.cli:main',
        ],
    },
)


