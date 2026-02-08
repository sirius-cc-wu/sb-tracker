from setuptools import setup, find_packages

setup(
    name="sb-tracker",
    version="0.1.2",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "sb=sb_tracker.cli:main",
        ],
    },
    author="Simple Beads Contributors",
    description="A minimal, standalone issue tracker for individuals",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/sirius-cc-wu/sb-tracker",
    license="MIT",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
