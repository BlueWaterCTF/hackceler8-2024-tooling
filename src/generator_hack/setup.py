from setuptools import setup, Extension

backup = Extension('generator_hack', sources=['generator_hack.c'])

setup(
    name='generator_hack',
    version='0.1',
    description='Generator hacks',
    author='SuperFashi',
    author_email='admin@superfashi.com',
    url='https://github.com/superfashi/generator_hack',
    ext_modules=[backup],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.11',
    ],
)