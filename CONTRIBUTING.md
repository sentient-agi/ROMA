# Contributing to ROMA

Thank you for your interest in contributing to ROMA (Recursive Open Meta-Agents)! We welcome contributions from the community to help make this framework better.

## getting Started

1.  **Fork the repository** on GitHub.
2.  **Clone your fork** locally:
    ```bash
    git clone https://github.com/your-username/ROMA.git
    cd ROMA
    ```
3.  **Set up your environment**. We recommend using `uv` for fast dependency management:
    ```bash
    pip install uv
    uv pip install -e ".[dev]"
    ```

## Development Workflow

1.  Create a new branch for your feature or fix:
    ```bash
    git checkout -b feature/my-new-feature
    ```
2.  Make your changes.
3.  Run tests to ensure everything is working:
    ```bash
    pytest
    ```
4.  Format your code (if applicable):
    ```bash
    ruff format .
    ```

## Pull Request Process

1.  Push your changes to your fork:
    ```bash
    git push origin feature/my-new-feature
    ```
2.  Open a Pull Request against the `main` branch of the upstream repository.
3.  Provide a clear description of your changes and why they are necessary.

## Code of Conduct

Please note that this project is released with a Contributor Code of Conduct. By participating in this project you agree to abide by its terms.

## Questions?

If you have any questions, feel free to open an issue or reach out to the maintainers.

Happy coding!
