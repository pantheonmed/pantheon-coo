"""Static fine-tuning configuration reference (Task 91)."""

FINE_TUNE_CONFIG = {
    "base_model": "claude-3-haiku-20240307",
    "learning_rate": 1e-5,
    "batch_size": 4,
    "epochs": 3,
    "max_seq_length": 4096,
    "training_data_path": "/tmp/pantheon_v2/ml/training/",
    "output_path": "/tmp/pantheon_v2/ml/models/",
}

EVALUATION_METRICS = [
    "plan_quality_score",
    "execution_success_rate",
    "eval_score_avg",
    "goal_type_accuracy",
]
