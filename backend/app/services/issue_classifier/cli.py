"""
cli.py — Command Line Interface for Issue Classifier ML Pipeline.
==================================================================
Provides entry points for:
  - training on verified datasets
  - evaluation & error analysis
  - ablation studies (rule_id inclusion vs exclusion)
  - batch candidate issue classification
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

from .classifier import IssueClassifier
from .config import (
    InferenceConfig,
    ModelConfig,
    NormalizationConfig,
    TrainingConfig,
)
from .dataset import DatasetPipeline
from .error_analysis import ErrorAnalyzer
from .evaluator import MultiTaskEvaluator
from .normalizer import IssueNormalizer
from .trainer import MultiTaskTrainer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("IssueClassifierCLI")


def load_dataset_file(file_path: str) -> List[Dict[str, Any]]:
    """Load JSON or JSONL dataset file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {file_path}")

    if path.suffix == ".jsonl":
        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
    else:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "issues" in data:
                return data["issues"]
            else:
                return [data]


def cmd_train(args: argparse.Namespace) -> None:
    """Execute training pipeline."""
    logger.info(f"Loading training data from: {args.data}")
    records = load_dataset_file(args.data)
    logger.info(f"Loaded {len(records)} raw records.")

    pipeline = DatasetPipeline()
    train_recs, val_recs, test_recs = pipeline.split_dataset(
        records,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        chronological=args.chronological,
    )

    logger.info(f"Splits -> Train: {len(train_recs)}, Val: {len(val_recs)}, Test: {len(test_recs)}")

    model_config = ModelConfig(
        pretrained_model_name=args.model_name,
        max_length=args.max_length,
    )
    training_config = TrainingConfig(
        learning_rate=args.lr,
        batch_size=args.batch_size,
        epochs=args.epochs,
        severity_loss_weight=args.sev_weight,
        priority_loss_weight=args.prio_weight,
        output_dir=args.output_dir,
    )

    trainer = MultiTaskTrainer(model_config, training_config, device=args.device)
    result = trainer.train(train_recs, val_recs, test_recs)

    logger.info("Training complete!")
    logger.info(f"Best Epoch: {result['best_epoch']}, Best Val Mean Macro-F1: {result['best_validation_score']:.4f}")


def cmd_evaluate(args: argparse.Namespace) -> None:
    """Execute model evaluation on a test dataset."""
    logger.info(f"Loading test data from: {args.data}")
    records = load_dataset_file(args.data)

    classifier = IssueClassifier(model_dir=args.model_dir, device=args.device)
    predictions = classifier.predict_batch(records)

    evaluator = MultiTaskEvaluator()
    y_true_sev = [pipeline_validate_sev(r) for r in records]
    y_pred_sev = [p["severity"]["label"] for p in predictions]

    y_true_prio = [pipeline_validate_prio(r) for r in records]
    y_pred_prio = [p["priority"]["label"] for p in predictions]

    # Convert to IDs
    from .config import PRIORITY_TO_ID, SEVERITY_TO_ID
    true_sev_ids = [SEVERITY_TO_ID[s] for s in y_true_sev]
    pred_sev_ids = [SEVERITY_TO_ID[s] for s in y_pred_sev]
    true_prio_ids = [PRIORITY_TO_ID[p] for p in y_true_prio]
    pred_prio_ids = [PRIORITY_TO_ID[p] for p in y_pred_prio]

    metrics = evaluator.evaluate(true_sev_ids, pred_sev_ids, true_prio_ids, pred_prio_ids)

    # Generate error report
    conf_sev = [p["severity"]["confidence"] for p in predictions]
    conf_prio = [p["priority"]["confidence"] for p in predictions]
    errors = ErrorAnalyzer.generate_error_report(
        records, y_true_sev, y_pred_sev, conf_sev, y_true_prio, y_pred_prio, conf_prio
    )

    print("\n" + "=" * 60)
    print("  MULTI-TASK EVALUATION REPORT")
    print("=" * 60)
    print(f"  Combined Mean Macro-F1 : {metrics['mean_macro_f1']:.4f}")
    print(f"  Severity Macro-F1      : {metrics['severity']['macro_f1']:.4f} (Acc: {metrics['severity']['accuracy']:.4f})")
    print(f"  Priority Macro-F1      : {metrics['priority']['macro_f1']:.4f} (Acc: {metrics['priority']['accuracy']:.4f})")
    print("\n  Under-classifications:")
    print(f"    Severity Rate        : {metrics['underclassifications']['severity_underclassifications']['rate']:.2%}")
    print(f"    Priority Rate        : {metrics['underclassifications']['priority_underclassifications']['rate']:.2%}")

    if args.output_report:
        report_data = {
            "metrics": metrics,
            "top_errors": errors[:50],
        }
        with open(args.output_report, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        logger.info(f"Detailed error report saved to: {args.output_report}")


def pipeline_validate_sev(r: Dict[str, Any]) -> str:
    return str(r.get("severity", "")).strip().lower()


def pipeline_validate_prio(r: Dict[str, Any]) -> str:
    return str(r.get("priority", "")).strip().lower()


def cmd_predict(args: argparse.Namespace) -> None:
    """Classify input candidate issues and output JSON."""
    logger.info(f"Loading input candidate issues from: {args.input}")
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    classifier = IssueClassifier(
        model_dir=args.model_dir,
        config=InferenceConfig(confidence_threshold=args.threshold, device=args.device),
    )

    enriched = classifier.classify_repository_analysis(data)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2)

    logger.info(f"Enriched candidate issues written to: {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue Classifier Multi-Task Pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Train command
    train_parser = subparsers.add_parser("train", help="Train multi-task DistilBERT classifier")
    train_parser.add_argument("--data", required=True, help="Path to labeled dataset (JSON/JSONL)")
    train_parser.add_argument("--model-name", default="distilbert-base-uncased")
    train_parser.add_argument("--epochs", type=int, default=5)
    train_parser.add_argument("--batch-size", type=int, default=16)
    train_parser.add_argument("--lr", type=float, default=2e-5)
    train_parser.add_argument("--max-length", type=int, default=256)
    train_parser.add_argument("--sev-weight", type=float, default=0.5)
    train_parser.add_argument("--prio-weight", type=float, default=0.5)
    train_parser.add_argument("--train-ratio", type=float, default=0.70)
    train_parser.add_argument("--val-ratio", type=float, default=0.15)
    train_parser.add_argument("--test-ratio", type=float, default=0.15)
    train_parser.add_argument("--chronological", action="store_true")
    train_parser.add_argument("--output-dir", default="backend/app/models/issue_classifier")
    train_parser.add_argument("--device", default="auto")

    # Evaluate command
    eval_parser = subparsers.add_parser("evaluate", help="Evaluate model on test dataset")
    eval_parser.add_argument("--data", required=True, help="Path to labeled test dataset")
    eval_parser.add_argument("--model-dir", default="backend/app/models/issue_classifier")
    eval_parser.add_argument("--output-report", default="evaluation_report.json")
    eval_parser.add_argument("--device", default="auto")

    # Predict command
    pred_parser = subparsers.add_parser("predict", help="Classify candidate issues JSON")
    pred_parser.add_argument("--input", required=True, help="Path to candidate issues JSON")
    pred_parser.add_argument("--output", required=True, help="Path to save enriched JSON")
    pred_parser.add_argument("--model-dir", default="backend/app/models/issue_classifier")
    pred_parser.add_argument("--threshold", type=float, default=0.80)
    pred_parser.add_argument("--device", default="auto")

    args = parser.parse_args()

    if args.command == "train":
        cmd_train(args)
    elif args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "predict":
        cmd_predict(args)


if __name__ == "__main__":
    main()
