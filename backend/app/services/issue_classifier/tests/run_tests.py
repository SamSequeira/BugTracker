"""
run_tests.py — Test runner for the Issue Classifier module.
===========================================================
Executes all unit tests for normalizer, model, dataset pipeline,
evaluator, and classifier.
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.resolve()))

from app.services.issue_classifier.tests.test_normalizer import TestIssueNormalizer
from app.services.issue_classifier.tests.test_model import TestMultiTaskModel
from app.services.issue_classifier.tests.test_dataset import TestDatasetPipeline
from app.services.issue_classifier.tests.test_evaluator import TestMultiTaskEvaluator
from app.services.issue_classifier.tests.test_classifier import TestIssueClassifier


def run_all_tests() -> bool:
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()

    suite.addTests(loader.loadTestsFromTestCase(TestIssueNormalizer))
    suite.addTests(loader.loadTestsFromTestCase(TestMultiTaskModel))
    suite.addTests(loader.loadTestsFromTestCase(TestDatasetPipeline))
    suite.addTests(loader.loadTestsFromTestCase(TestMultiTaskEvaluator))
    suite.addTests(loader.loadTestsFromTestCase(TestIssueClassifier))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
