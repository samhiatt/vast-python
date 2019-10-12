from setuptools import setup, find_packages

with open("README.md") as f:
  long_description = f.read()

setup(
    name = "vastai",
    version = "0.1",
    packages = find_packages('src'),
    package_dir={
        '': 'src',
        'test': 'test',
    },
    scripts = ['vast.py'],
    #entry_points = {
    #    'console_scripts':['foobar=vastai.foobar:main'],
    #},
    #source_dir = 'src/vastai',
    install_requires = [ 'paramiko' ],
    tests_require = [ 'pytest', 'requests-mock', 'pyfakefs' ],
    extras_require = {
        'docs': ['pdoc3'],
    },
    setup_requires = [ 'pytest-runner>=2.0,<3dev' ],
    author = "Sam Hiatt",
    author_email = "samhiatt@gmail.com",
    license = "LICENSE.txt",
    description = "An object-oriented python interface to the vast.ai REST API.",
    long_description = long_description,
    keywords = "vast vast.ai python api machine-learning",
    url = "http://github.com/samhiatt/vast-python",  
    project_urls = {
        'Source': 'http://github.com/samhiatt/vast-python',
        'Original Source': 'http://github.com/vast-ai/vast-python',
    },
    classifiers = [
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.6',
        'Development Status :: 3 - Alpha',
    ],

)




