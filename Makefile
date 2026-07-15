.PHONY: up api dashboard test

up:
	python scripts/dev_up.py

api:
	.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8402

dashboard:
	cd dashboard && pnpm dev

test:
	.venv/Scripts/python.exe -m pytest -v
	cd dashboard && pnpm vitest run