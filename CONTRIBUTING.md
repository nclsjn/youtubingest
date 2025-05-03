# Contributing to Youtubingest

First off, thank you for considering contributing to Youtubingest! We welcome any help, whether it's reporting a bug, proposing a new feature, improving documentation, or writing code.

This document provides guidelines to help you contribute effectively.

## Important Note About This Project

This project was developed by someone without formal programming experience, with significant assistance from AI tools. While the application is functional, the codebase may not adhere to all industry best practices and could benefit from improvements by experienced developers.

If you're an experienced developer, your expertise in refactoring, optimizing, and improving the code quality would be especially valuable. If you're a beginner, this project might be a good learning opportunity, as it demonstrates what can be achieved with AI assistance.

## Code of Conduct

While we don't have a formal Code of Conduct document yet, we expect all contributors to be respectful and considerate of others. Please engage in discussions constructively and help create a positive environment.

## How Can I Contribute?

There are several ways you can contribute:

### Reporting Bugs

* If you find a bug, please check the [GitHub Issues](https://github.com/nclsjn/youtubingest/issues) first to see if it has already been reported.
* If not, open a new issue. Be sure to include:
    * A clear and descriptive title.
    * Steps to reproduce the bug.
    * What you expected to happen.
    * What actually happened (including any error messages or logs if possible).
    * Your environment details (OS, Python version, etc.).

### Suggesting Enhancements

* If you have an idea for a new feature or an improvement to an existing one, check the [GitHub Issues](https://github.com/nclsjn/youtubingest/issues) to see if it's already been suggested.
* If not, open a new issue describing your enhancement:
    * Use a clear and descriptive title.
    * Provide a step-by-step description of the suggested enhancement in as many details as possible.
    * Explain why this enhancement would be useful.

### Pull Requests (Code Contributions)

We welcome pull requests! Here's the general workflow:

1.  **Fork the repository** to your own GitHub account.
2.  **Clone your fork** locally: `git clone https://github.com/YOUR_USERNAME/youtubingest.git`
3.  **Create a new branch** for your changes: `git checkout -b feature/your-feature-name` or `fix/issue-number`. Please use descriptive branch names.
4.  **Set up your development environment:** Follow the instructions in the [README.md](README.md#installation) file (create a virtual environment, install dependencies, set up `.env`).
5.  **Make your code changes.** Ensure you adhere to the [Code Style](#code-style) guidelines.
6.  **Add tests** for your changes if applicable (see [Testing](#testing)).
7.  **Run tests** locally to ensure they pass. (Instructions on how to run tests should be added here once a test runner is set up, e.g., `pytest`).
8.  **Commit your changes** with clear and concise commit messages. Reference any related issue number (e.g., `git commit -m 'feat: Add support for XYZ (closes #123)'`).
9.  **Push your branch** to your fork: `git push origin feature/your-feature-name`
10. **Open a Pull Request (PR)** against the `main` branch of the `nclsjn/youtubingest` repository.
    * Provide a clear title and description for your PR. Explain the "what" and "why" of your changes.
    * Link to any relevant issues.
    * Ensure any applicable documentation (`README.md`, docstrings) is updated.

## Pull Request Checklist

Before submitting your PR, please ensure:

* [ ] Your code adheres to the [Code Style](#code-style) guidelines.
* [ ] You have added tests for new features or bug fixes.
* [ ] All existing and new tests pass locally.
* [ ] You have updated the documentation (`README.md`, docstrings) if necessary.
* [ ] Your commit messages are clear and descriptive.
* [ ] The PR description clearly explains the changes and links to related issues.

## Code Style

* Please follow **PEP 8** guidelines for Python code. We recommend using linters/formatters like `flake8` and `black`.
* Use clear and descriptive variable and function names.
* Add **docstrings** to new functions, classes, and methods, explaining their purpose, arguments, and return values.
* Keep code modular and focused on specific responsibilities.

## Testing

* Contributions should ideally include tests.
* If you're fixing a bug, add a test that demonstrates the bug and verifies the fix.
* If you're adding a feature, add tests that cover the new functionality.
* Ensure all tests pass before submitting a PR. (Add command to run tests here when available).

## License

By contributing to Youtubingest, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).

Thank you for contributing!
