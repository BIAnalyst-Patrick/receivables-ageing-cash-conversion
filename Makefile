.PHONY: run test charts clean

run:
	python3 scripts/run_all.py

test:
	python3 -m unittest discover -s tests -v

charts:
	python3 -c "from recv import pipeline, charts; from pathlib import Path; r=pipeline.analyse(pipeline.generate()); [print(p) for p in charts.render_all(r, Path(\"outputs/charts\"))]"

clean:
	rm -rf outputs/charts/*.png outputs/tables/*.csv outputs/answer_key.* outputs/validation_report.md data/ledger.json
