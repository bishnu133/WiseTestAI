from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="aitestrunner",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="AI-powered scriptless test automation framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/aitestrunner",
    packages=find_packages(exclude=["tests", "tests.*", "examples", "examples.*", "docs"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Testing",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "playwright>=1.40.0",
        "pyyaml>=6.0.1",
        "click>=8.1.7",
        "pytest>=7.4.3",
        "Pillow>=10.1.0",
        "opencv-python-headless>=4.8.1.78",
        "numpy>=1.24.4",
        "requests>=2.31.0",
        "jinja2>=3.1.2",
        "colorama>=0.4.6",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "ai": ["ultralytics>=8.0.200"],
        "nlp": ["spacy>=3.7.2"],
        "dev": [
            "pytest-cov>=4.1.0",
            "black>=23.10.0",
            "flake8>=6.1.0",
            "pre-commit>=3.5.0",
        ],
        "all": [
            "ultralytics>=8.0.200",
            "spacy>=3.7.2",
            "pytest-cov>=4.1.0",
            "black>=23.10.0",
            "flake8>=6.1.0",
            "pre-commit>=3.5.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "aitestrunner=run:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.yaml", "*.yml", "*.json", "*.feature"],
    },
    project_urls={
        "Bug Reports": "https://github.com/yourusername/aitestrunner/issues",
        "Source": "https://github.com/yourusername/aitestrunner",
        "Documentation": "https://github.com/yourusername/aitestrunner/docs",
    },
    keywords="automation testing ai selenium playwright bdd gherkin scriptless",
    license="MIT",
)  # This closing parenthesis was missing