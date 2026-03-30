# ML / fine-tuning pipeline

1. **Collect** — `TrainingDataCollector.collect_successful_tasks()` reads high-scoring tasks from SQLite.
2. **Export** — `export_jsonl()` writes JSONL with `messages` pairs for planning / reasoning.
3. **Submit** — Upload the JSONL to your Anthropic fine-tuning / custom model workflow (see current Anthropic docs).
4. **Evaluate** — Track `EVALUATION_METRICS` in `training_config.py` against a held-out validation set.

Expected improvements: better plan JSON adherence and domain-specific tone when trained on your organization’s successful runs.
