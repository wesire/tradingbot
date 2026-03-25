"""
Model performance monitor.

Tracks prediction outcomes over time, computes rolling metrics, stores
them in a JSON log, and alerts when accuracy drops below a threshold.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ModelMonitor:
    """
    Logs prediction outcomes and reports performance statistics.

    Parameters
    ----------
    log_path:
        Path to the JSON-lines log file.  Created automatically if absent.
    accuracy_threshold:
        If rolling accuracy drops below this value a warning is logged.
    window:
        Number of recent predictions to use for rolling metrics.
    """

    def __init__(
        self,
        log_path: str = "models/model_monitor.jsonl",
        accuracy_threshold: float = 0.50,
        window: int = 100,
    ) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.accuracy_threshold = accuracy_threshold
        self.window = window

        # In-memory cache of recent entries for fast metric computation
        self._recent: List[Dict[str, Any]] = []
        self._load_recent()

    # ------------------------------------------------------------------
    # Core logging method
    # ------------------------------------------------------------------

    def log_prediction(
        self,
        prediction: str,
        actual_outcome: str,
        confidence: float,
        timestamp: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record a single prediction/outcome pair.

        Parameters
        ----------
        prediction:
            The signal emitted by the model (``"long"``, ``"short"``,
            ``"neutral"``).
        actual_outcome:
            The true observed outcome (same domain as ``prediction``).
        confidence:
            Model's reported confidence (0–1).
        timestamp:
            ISO-8601 timestamp; defaults to now (UTC).
        metadata:
            Any extra key/value pairs to store alongside the entry.
        """
        entry: Dict[str, Any] = {
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "prediction": prediction,
            "actual": actual_outcome,
            "confidence": confidence,
            "correct": prediction == actual_outcome,
        }
        if metadata:
            entry["metadata"] = metadata

        # Append to log file
        with open(self.log_path, "a") as fh:
            fh.write(json.dumps(entry) + "\n")

        # Update in-memory cache
        self._recent.append(entry)
        if len(self._recent) > self.window:
            self._recent = self._recent[-self.window:]

        # Check for degradation
        self._check_degradation()

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_performance_report(self) -> Dict[str, Any]:
        """
        Return a summary dict of recent model performance.

        Returns
        -------
        dict with keys:
            ``n_predictions``, ``accuracy``, ``precision_long``,
            ``precision_short``, ``recall_long``, ``recall_short``,
            ``prediction_distribution``, ``confidence_calibration``,
            ``window``.
        """
        if not self._recent:
            return {
                "n_predictions": 0,
                "accuracy": None,
                "window": self.window,
            }

        entries = self._recent
        n = len(entries)
        correct = sum(1 for e in entries if e["correct"])
        accuracy = correct / n

        # Prediction distribution
        from collections import Counter
        pred_counts = Counter(e["prediction"] for e in entries)
        total = sum(pred_counts.values())
        distribution = {k: v / total for k, v in pred_counts.items()}

        # Per-class precision & recall
        def _precision(cls: str) -> Optional[float]:
            predicted = [e for e in entries if e["prediction"] == cls]
            if not predicted:
                return None
            tp = sum(1 for e in predicted if e["actual"] == cls)
            return tp / len(predicted)

        def _recall(cls: str) -> Optional[float]:
            actual = [e for e in entries if e["actual"] == cls]
            if not actual:
                return None
            tp = sum(1 for e in actual if e["prediction"] == cls)
            return tp / len(actual)

        # Confidence calibration: bucket by 0.1 intervals
        calibration = self._compute_calibration(entries)

        return {
            "n_predictions": n,
            "accuracy": round(accuracy, 4),
            "precision_long": _precision("long"),
            "precision_short": _precision("short"),
            "recall_long": _recall("long"),
            "recall_short": _recall("short"),
            "prediction_distribution": distribution,
            "confidence_calibration": calibration,
            "window": self.window,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_degradation(self) -> None:
        """Log a warning if rolling accuracy falls below the threshold."""
        if len(self._recent) < 20:
            return  # Not enough data yet
        correct = sum(1 for e in self._recent if e["correct"])
        acc = correct / len(self._recent)
        if acc < self.accuracy_threshold:
            logger.warning(
                "ModelMonitor: accuracy %.3f is below threshold %.3f over "
                "last %d predictions",
                acc,
                self.accuracy_threshold,
                len(self._recent),
            )

    @staticmethod
    def _compute_calibration(
        entries: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """
        Group predictions by 10-point confidence buckets and return
        average accuracy per bucket.
        """
        buckets: Dict[str, List[bool]] = {}
        for e in entries:
            conf = e.get("confidence", 0.5)
            bucket = f"{int(conf * 10) * 10}-{int(conf * 10) * 10 + 10}%"
            buckets.setdefault(bucket, []).append(e["correct"])

        return {
            bucket: round(sum(vals) / len(vals), 4)
            for bucket, vals in sorted(buckets.items())
        }

    def _load_recent(self) -> None:
        """Populate ``_recent`` from the last ``window`` lines of the log."""
        if not self.log_path.exists():
            return
        lines: List[str] = []
        try:
            with open(self.log_path) as fh:
                lines = fh.readlines()
        except OSError as exc:
            logger.warning("ModelMonitor: could not read log: %s", exc)
            return

        for line in lines[-self.window:]:
            line = line.strip()
            if line:
                try:
                    self._recent.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
