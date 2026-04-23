.PHONY: help venv install test parse validate promote clean all

PYTHON := .venv/bin/python
PIP := .venv/bin/pip

help:
	@echo "Targets: install test parse validate promote clean all"

venv:
	python3 -m venv .venv

install: venv
	$(PIP) install -r requirements.txt

test:
	$(PYTHON) -m pytest -v

parse:
	$(PYTHON) parse.py

validate:
	$(PYTHON) validate.py

promote:
	$(PYTHON) promote.py

clean:
	rm -rf staging/
	find . -name __pycache__ -exec rm -rf {} +

all: parse validate
