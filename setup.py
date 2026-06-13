"""LocalPulse AI - Business Intelligence Agent for Local Services."""
from setuptools import find_packages, setup

setup(
    name="localpulse-ai",
    version="0.1.0",
    description="Business Intelligence Agent for local service companies",
    packages=find_packages(),
    install_requires=[
        "jsonschema>=4.20.0",
        "requests>=2.31.0",
        "beautifulsoup4>=4.12.0",
        "lxml>=5.0.0",
        "textblob>=0.17.0",
        "click>=8.1.0",
    ],
    python_requires=">=3.10",
)
