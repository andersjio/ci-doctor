.PHONY: fmt lint test run

run:
	python -m ci_doctor.cli analyze $(URL)

fmt:
	python -m pip install ruff black
	ruff check --fix src
	black src tests

lint:
	ruff check src

test:
	pytest -q
