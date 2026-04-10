.PHONY: setup scrape scrape-quick analyze report dashboard test clean all sample sample-all consolidate

# ============================================================
# Rappi Competitive Intelligence System — Makefile
# ============================================================

# Setup: install dependencies and playwright browsers
setup:
	pip install -r requirements.txt
	playwright install chromium
	@echo "✅ Setup complete"

# Scraping
scrape:
	python run_scraper.py --locations all --platforms all
	@echo "✅ Full scrape complete"

scrape-quick:
	python run_scraper.py --mode quick
	@echo "✅ Quick scrape complete (5 locations)"

scrape-rappi:
	python run_scraper.py --platforms rappi --locations all
	@echo "✅ Rappi scrape complete"

scrape-ubereats:
	python run_scraper.py --platforms ubereats --locations all
	@echo "✅ Uber Eats scrape complete"

# Generate synthetic sample data (no browser required)
sample:
	python -m scripts.generate_sample_data
	python -m scripts.consolidate_data
	@echo "✅ Sample data generated (quick locations)"

sample-all:
	python -m scripts.generate_sample_data --all
	python -m scripts.consolidate_data
	@echo "✅ Full sample data generated (25 locations)"

# Consolidate raw JSONs to CSV
consolidate:
	python -m scripts.consolidate_data
	@echo "✅ Data consolidated to data/processed/competitive_data.csv"

# Analysis
analyze: consolidate
	python -m analysis.comparative
	python -m analysis.insights
	python -m analysis.visualizations
	@echo "✅ Analysis complete — check data/processed/ and reports/"

# Report generation
report:
	python generate_report.py
	@echo "✅ Report generated — check reports/"

# Dashboard
dashboard:
	streamlit run dashboard/app.py --server.port 8501

# Testing
test:
	pytest tests/ -v

# Clean generated data (keeps raw scrape data)
clean:
	rm -rf data/processed/*
	rm -rf reports/*.pdf
	@echo "✅ Cleaned processed data and reports"

# Clean everything including raw data
clean-all:
	rm -rf data/raw/*
	rm -rf data/processed/*
	rm -rf data/screenshots/*
	rm -rf reports/*
	@echo "✅ Cleaned all data"

# Full pipeline
all: setup scrape analyze report
	@echo "🚀 Full pipeline complete"

# Quick pipeline (for demo — no browser required)
demo: setup sample analyze report
	@echo "Demo pipeline complete"
