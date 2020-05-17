from setuptools import setup, find_packages

setup(
    name='postgresql_utils',
    version='0.0.1',
    url='https://github.com/eugenyProchan',
    author='Prochan Eugeny',
    author_email='prochanev@gmail.com',
    description='Utils for work with postgres db with psycopg2 driver',
    packages=find_packages(exclude='tests'),
    install_requires=['psycopg2>=2.8.5'],
)
