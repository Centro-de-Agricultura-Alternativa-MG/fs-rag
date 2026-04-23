"""Setup configuration for FS-RAG package."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="fs-rag",
    version="0.1.0",
    author="Your Name",
    description="Filesystem Indexing and RAG-Powered Q&A for OpenWebUI/OpenClaw",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/fs-rag",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "fs-rag=fs_rag.cli.main:cli",
        ],
    },
)
