"""
splitter.py — Group-aware, Stratified, Leakage-Free Dataset Splitting.
=====================================================================
Partitions candidate issues into reproducible train, validation, and test sets.
Guarantees zero group overlap across splits to prevent data leakage.
"""
from __future__ import annotations

from collections import defaultdict
import logging
from typing import Any, Dict, List, Set, Tuple
import numpy as np

from .feature_builder import generate_group_id

logger = logging.getLogger(__name__)


class DatasetSplitter:
    """Performs group-aware and stratified dataset partitioning."""

    def __init__(
        self,
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        random_seed: int = 42,
        min_samples_per_class: int = 2,
    ) -> None:
        if abs(train_ratio + val_ratio + test_ratio - 1.0) > 1e-4:
            raise ValueError("Split ratios (train, validation, test) must sum to 1.0")

        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        self.random_seed = random_seed
        self.min_samples_per_class = min_samples_per_class

    def split(
        self, records: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """
        Split records into (train, val, test) guaranteeing zero group leakage.
        Returns:
          (train_records, val_records, test_records, split_metadata)
        """
        if not records:
            return [], [], [], {"strategy": "empty", "total_records": 0}

        # 1. Group records by group_id
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in records:
            gid = r.get("group_id") or generate_group_id(r)
            r["group_id"] = gid
            groups[gid].append(r)

        unique_group_ids = sorted(list(groups.keys()))
        n_groups = len(unique_group_ids)

        # 2. Determine dominant label per group for stratification
        group_combined_labels: Dict[str, str] = {}
        group_sev_labels: Dict[str, str] = {}

        for gid, grp_records in groups.items():
            sev_counts: Dict[str, int] = defaultdict(int)
            comb_counts: Dict[str, int] = defaultdict(int)
            for item in grp_records:
                sev = str(item.get("verified_severity") or item.get("severity") or "").lower()
                prio = str(item.get("verified_priority") or item.get("priority") or "").lower()
                sev_counts[sev] += 1
                comb_counts[f"{sev}__{prio}"] += 1

            dom_sev = max(sev_counts.items(), key=lambda x: x[1])[0]
            dom_comb = max(comb_counts.items(), key=lambda x: x[1])[0]
            group_sev_labels[gid] = dom_sev
            group_combined_labels[gid] = dom_comb

        # 3. Choose Stratification Strategy
        comb_class_counts = defaultdict(int)
        for c in group_combined_labels.values():
            comb_class_counts[c] += 1

        sev_class_counts = defaultdict(int)
        for s in group_sev_labels.values():
            sev_class_counts[s] += 1

        rng = np.random.RandomState(self.random_seed)

        # Strategy decision
        strategy_info: Dict[str, Any] = {}
        if n_groups >= 3 and min(comb_class_counts.values()) >= 3:
            strategy = "combined_severity_priority_stratified_group_split"
            target_group_labels = group_combined_labels
            strategy_info = {
                "requested": "combined_severity_priority",
                "actual": strategy,
                "fallback_reason": None,
            }
        elif n_groups >= 3 and min(sev_class_counts.values()) >= 3:
            strategy = "severity_stratified_group_split"
            target_group_labels = group_sev_labels
            strategy_info = {
                "requested": "combined_severity_priority",
                "actual": strategy,
                "fallback_reason": "Combined severity-priority classes have sparse groups (< 3 samples); fell back to severity stratification.",
            }
        else:
            strategy = "random_group_split"
            target_group_labels = None
            strategy_info = {
                "requested": "combined_severity_priority",
                "actual": strategy,
                "fallback_reason": "Single class groups have fewer than 3 samples; fell back to deterministic group-aware random split.",
            }

        # 4. Perform Partitioning
        train_group_ids: Set[str] = set()
        val_group_ids: Set[str] = set()
        test_group_ids: Set[str] = set()

        if target_group_labels is not None:
            # Stratified group split per class
            classes_to_groups = defaultdict(list)
            for gid in unique_group_ids:
                classes_to_groups[target_group_labels[gid]].append(gid)

            for class_name, cls_gids in sorted(classes_to_groups.items()):
                shuffled_cls_gids = cls_gids.copy()
                rng.shuffle(shuffled_cls_gids)

                n_cls = len(shuffled_cls_gids)
                n_train = max(1, int(round(n_cls * self.train_ratio)))
                n_val = max(1, int(round(n_cls * self.val_ratio))) if n_cls >= 3 else 0
                n_test = n_cls - n_train - n_val

                if n_test <= 0 and n_cls >= 3:
                    n_test = 1
                    if n_train > 1:
                        n_train -= 1

                for g in shuffled_cls_gids[:n_train]:
                    train_group_ids.add(g)
                for g in shuffled_cls_gids[n_train:n_train + n_val]:
                    val_group_ids.add(g)
                for g in shuffled_cls_gids[n_train + n_val:]:
                    test_group_ids.add(g)
        else:
            # Pure random group split
            shuffled_gids = unique_group_ids.copy()
            rng.shuffle(shuffled_gids)

            n_train = int(round(n_groups * self.train_ratio))
            n_val = int(round(n_groups * self.val_ratio))

            train_group_ids = set(shuffled_gids[:n_train])
            val_group_ids = set(shuffled_gids[n_train:n_train + n_val])
            test_group_ids = set(shuffled_gids[n_train + n_val:])

        # 5. Populate record splits
        train_records: List[Dict[str, Any]] = []
        val_records: List[Dict[str, Any]] = []
        test_records: List[Dict[str, Any]] = []

        for gid in unique_group_ids:
            grp_items = groups[gid]
            if gid in train_group_ids:
                train_records.extend(grp_items)
            elif gid in val_group_ids:
                val_records.extend(grp_items)
            elif gid in test_group_ids:
                test_records.extend(grp_items)
            else:
                # Fallback to train
                train_group_ids.add(gid)
                train_records.extend(grp_items)

        # 6. Leakage & Overlap Validation
        tv_overlap = len(train_group_ids & val_group_ids)
        tt_overlap = len(train_group_ids & test_group_ids)
        vt_overlap = len(val_group_ids & test_group_ids)
        cross_split_overlap = tv_overlap + tt_overlap + vt_overlap

        if cross_split_overlap > 0:
            raise RuntimeError(
                f"Data leakage detected! Group overlap across splits: "
                f"train-val={tv_overlap}, train-test={tt_overlap}, val-test={vt_overlap}"
            )

        metadata = {
            "strategy": strategy,
            "strategy_details": strategy_info,
            "random_seed": self.random_seed,
            "total_groups": n_groups,
            "train_groups": len(train_group_ids),
            "validation_groups": len(val_group_ids),
            "test_groups": len(test_group_ids),
            "train_records": len(train_records),
            "validation_records": len(val_records),
            "test_records": len(test_records),
            "cross_split_group_overlap": cross_split_overlap,
            "leakage_check_passed": cross_split_overlap == 0,
        }

        return train_records, val_records, test_records, metadata
