# pipeshell

**pipeshell** is a simple pipeline execution library allowing you to define and run pipelines of shell commands with dependencies, retries, and other features.

## Features

- Define steps with shell commands
- Set dependencies between steps
- Retry steps on failure
- Run steps in the background
- Capture and display step outputs
- Set environment variables for steps

## Installation

To install `pipeshell`, you can use `pip`:

```sh
pip install pipeshell
```

## Usage

Here's a quick example of how to define and run a pipeline with `pipeshell`:

```python
from pipeshell import pipeline, Step


# Define the steps
prepare_environment = Step(
    name="prepare_environment",
    command="echo 'Preparing environment...'"
)

fetch_data = Step(
    name="fetch_data",
    command="curl -o data.txt https://example.com/data.txt",
    depends_on=[prepare_environment]
)

process_data = Step(
    name="process_data",
    command="python process_data.py data.txt processed_data.txt",
    depends_on=[fetch_data]
)

analyze_data = Step(
    name="analyze_data",
    command="python analyze_data.py processed_data.txt results.txt",
    depends_on=[process_data]
)

cleanup = Step(
    name="cleanup",
    command="rm data.txt processed_data.txt",
    depends_on=[analyze_data],
    allow_failure=True  # Allow cleanup to fail without affecting pipeline
)

pipeline("example_pipeline", prepare_environment, fetch_data, process_data, analyze_data, cleanup)
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request on GitHub.

## License

This project is licensed under the MIT License.
