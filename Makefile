.PHONY: all test lint type-check clean

all: clean test lint type-check

# Run tests
test:
	@echo "Running tests..."
	@poetry run pytest

# Run type checks
type-check:
	@echo "Running type checks..."
	# @poetry run mypy 
	@poetry run mypy --install-types pipeshell tests

# Run linting and formatting
lint:
	@echo "Running linters and formatters..."
	@poetry run autoflake .
	@poetry run black .
	@poetry run isort .

# Clean up
clean:
	@rm -rf __pycache__
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -exec rm -r {} +
	@find . -type d -name ".mypy_cache" -exec rm -r {} +
	@find . -type d -name ".pytest_cache" -exec rm -r {} +
