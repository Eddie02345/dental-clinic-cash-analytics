.PHONY: setup data app test export clean

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

data:
	.venv/bin/python -m src.pipeline --force

app:
	.venv/bin/streamlit run src/app/app.py

test:
	.venv/bin/python -m pytest tests -q

export:
	.venv/bin/python -m src.export

clean:
	rm -rf data/processed reports models data/clinic.db
