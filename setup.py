import sys
try:
    from setuptools import setup, Extension
except ImportError:
    from distutils.core import setup, Extension

import numpy as np

if sys.platform != 'win32':
    compile_args = ['-funroll-loops']
else:
    # XXX insert win32 flag to unroll loops here
    compile_args = []

setup(
    name='perlstim',
    version='0.1',
    description='Perlin noise stimuli for Python',
    long_description='Based on the "noise" package by Casey Duncan',
    author='Max Shinn',
    author_email='m.shinn@ucl.ac.uk',
    url='https://github.com/mwshinn/perlin_stimuli',
    classifiers = [
        'Development Status :: 4 - Beta',
        'Programming Language :: C',
        'Programming Language :: Python :: 3',
    ],

    packages=['perlstim'],
    ext_modules=[
        Extension('perlstim._perlin', ['perlstim/_perlin.c'],
            extra_compile_args=compile_args,
                  include_dirs=[np.get_include()],
        )
    ],
)
