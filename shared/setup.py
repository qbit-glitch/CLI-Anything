from setuptools import setup, find_packages

setup(
    name="motion-math",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[],
    extras_require={
        "numpy": ["numpy>=1.24"],
        "dev": ["pytest>=7", "numpy>=1.24"],
    },
)
