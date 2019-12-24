# -*- coding: utf-8 -*-

from setuptools import setup, find_packages


with open('README.md') as f:
    readme = f.read()

setup(
    name='multisieve_coreference',
    version='0.1.2',
    description='Basic coreference resolution module, based on multi-sieve',
    long_description=readme,
    long_description_content_type="text/markdown",
    author='Antske Fokkens',
    author_email='antske.fokkens@vu.nl',
    url='https://github.com/antske/coref_draft/',
    packages=find_packages(exclude=('tests', 'docs')),
    package_data={'multisieve_coreference': ['resources/*/*']},
    install_requires=[
        "KafNafParserPy>=1.88",
    ],
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: Dutch',
        'Programming Language :: Python :: 3',
        'Topic :: Text Processing :: Linguistic',
    ]
)
