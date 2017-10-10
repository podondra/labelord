from setuptools import setup

setup(
    name='labelord',
    # TODO advance to 0.1 when finished
    version='0.0',
    py_modules=['labelord'],
    install_requires=[
        'click>=6.7',
        'requests>=2.18.4',
        ],
    entry_points='''
        [console_scripts]
        labelord=labelord:cli
        ''',
    author='Ondřej Podsztavek',
    author_email='ondrej.podsztavek@gmail.com',
    )
