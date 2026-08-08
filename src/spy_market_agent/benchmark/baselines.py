from __future__ import annotations

from collections.abc import Sequence

from spy_market_agent.benchmark.locks import ClassificationMetricSet
from spy_market_agent.benchmark.metrics import classification_metric_set


def classification_baseline_metrics(
    *,
    benchmark_id: str,
    dataset_id: str,
    training_targets: Sequence[int],
    evaluation_targets: Sequence[int],
    partition_name: str,
) -> dict[str, ClassificationMetricSet]:
    training_values = [int(value) for value in training_targets]
    evaluation_values = [int(value) for value in evaluation_targets]
    positive_training_count = sum(training_values)
    negative_training_count = len(training_values) - positive_training_count
    majority_class = 1 if positive_training_count > negative_training_count else 0
    training_prevalence = positive_training_count / len(training_values)
    definitions = {
        "majority_class": (
            float(majority_class),
            [majority_class for _ in evaluation_values],
        ),
        "always_positive": (1.0, [1 for _ in evaluation_values]),
        "always_negative": (0.0, [0 for _ in evaluation_values]),
        "training_prevalence": (
            float(training_prevalence),
            [1 if training_prevalence >= 0.5 else 0 for _ in evaluation_values],
        ),
    }
    return {
        name: classification_metric_set(
            benchmark_id=benchmark_id,
            dataset_id=dataset_id,
            model_name=name,
            partition_name=partition_name,
            targets=evaluation_values,
            probabilities=[probability for _ in evaluation_values],
            predictions=predictions,
        )
        for name, (probability, predictions) in definitions.items()
    }
