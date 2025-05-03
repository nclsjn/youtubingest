from setuptools import setup, find_packages
import os
import re

# Function to extract version from __init__.py
def get_version(package):
    """Return package version as listed in `__version__` in `init.py`."""
    # Assumes __init__.py is at the root relative to setup.py
    init_py_path = os.path.join(os.path.dirname(__file__), package, '__init__.py')
    if not os.path.exists(init_py_path):
         # If setup.py is inside the package, adjust path
         init_py_path = os.path.join(os.path.dirname(__file__), '__init__.py')
         if not os.path.exists(init_py_path):
              raise RuntimeError(f"Unable to find __init__.py in {package} or parent dir.")

    with open(init_py_path, 'r', encoding='utf-8') as f:
         init_py = f.read()

    match = re.search("__version__ = ['\"]([^'\"]+)['\"]", init_py)
    if match:
        return match.group(1)
    else:
         raise RuntimeError(f"Unable to find __version__ string in {init_py_path}")

version = get_version('.')

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = f.read().splitlines()

setup(
    name="youtubingest",
    version=version,
    author="nclsjn",
    author_email="nclsjn@users.noreply.github.com",
    description="A tool to extract and process YouTube content for LLMs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nclsjn/youtubingest",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "youtubingest=server:main",
        ],
    },
)