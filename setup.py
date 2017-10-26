from setuptools import setup, find_packages


with open('README.md') as f:
    long_description = ''.join(f.readlines())

setup(
    name='labelord_podszond',
    version='0.3',
    description='Labelord is tool for managing labels on GitHub.',
    long_description=long_description,
    author='Ondřej Podsztavek',
    author_email='ondrej.podsztavek@gmail.com',
    license='GNU General Public License v3.0',
    url='https://github.com/podondra/mi-pyt-labelord',
    packages=find_packages(),
    package_data={'labelord': ['templates/*.html']},
    keywords='github,labels',
    install_requires=['click>=6', 'requests>=2.18', 'Flask>=0.12'],
    # TODO dev requires
    # TODO test requires
    # http://click.pocoo.org/5/setuptools/
    entry_points={
        'console_scripts': [
            'labelord = labelord.cli:cli',
            ],
        },
    classifiers=[
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Framework :: Flask',
        'Environment :: Console',
        'Environment :: Web Environment'
        ],
    zip_safe=False,  # because of Flask's templates
    )
