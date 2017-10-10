from setuptools import setup

setup(
    name='labelord',
    version='0.1',
    py_modules=['labelord'],
    install_requires=[
        'click',
        'requests',
        ],
    entry_points='''
        [console_scripts]
        labelord=labelord:cli
        ''',
    )
