.PHONY: help install test test-fast build up down logs seed-demo docs-check

help:
	@echo "SEO AUTOMATION LAB"
	@echo "  install     Install backend and frontend dependencies"
	@echo "  test        Run the full backend suite (includes 100k URL test)"
	@echo "  test-fast   Skip the 100k URL acceptance test"
	@echo "  build       Build frontend production bundle"
	@echo "  up          Start API, worker and frontend with Docker Compose"
	@echo "  down        Stop Docker Compose services"
	@echo "  logs        Tail Docker Compose logs"
	@echo "  seed-demo   Generate and populate the synthetic demo project"
	@echo "  docs-check  Verify required documentation files exist"

install:
	python -m pip install -r backend/requirements.txt
	cd frontend && npm install

test:
	cd backend && python -m pytest -q --disable-warnings

test-fast:
	cd backend && python -m pytest -q --disable-warnings -m "not slow"

build:
	cd frontend && npm run build

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

seed-demo:
	cd backend && python scripts/seed_demo.py --size 1000

docs-check:
	bash -c 'for f in README.md docs/{INSTALLATION,ARCHITECTURE,DATABASE_SCHEMA,API_DOCUMENTATION,CRAWLER_METHODOLOGY,ORPHAN_DETECTION_METHODOLOGY,KEYWORD_MAPPING_METHODOLOGY,PRIORITY_SCORING_METHODOLOGY,INTEGRATIONS,SECURITY,TESTING,DEPLOYMENT,DEMO_GUIDE,INTERVIEW_DEMONSTRATIONS,ROADMAP,CHANGELOG}.md; do test -s "$$f" || { echo "Missing: $$f"; exit 1; }; done; echo "All required docs present."'
