.PHONY: run migrate seed test lint

run:
	python manage.py runserver

migrate:
	python manage.py makemigrations
	python manage.py migrate

seed:
	python manage.py seed --clear

superuser:
	python manage.py createsuperuser

schema:
	python manage.py spectacular --file schema.yaml

test:
	pytest --cov=apps --cov-report=term-missing

lint:
	black apps/ k_conference/
	isort apps/ k_conference/
	flake8 apps/ k_conference/

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt
