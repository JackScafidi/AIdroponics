# MIT License
#
# Copyright (c) 2026 Claudroponics
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Deficiency and disease classification aggregator.

Maps per-plant YOLO health class labels to structured deficiency/severity
data, and aggregates across a full channel to produce summary statistics
compatible with the ChannelHealthSummary ROS 2 message.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Class-label mappings
# ---------------------------------------------------------------------------

#: Maps health_class labels that represent nutrient deficiencies to their
#: canonical short name used in ROS messages and downstream logic.
DEFICIENCY_TYPES: dict[str, str] = {
    "nitrogen_deficiency": "nitrogen",
    "phosphorus_deficiency": "phosphorus",
    "potassium_deficiency": "potassium",
    "iron_deficiency": "iron",
}

#: Maps health_class labels that represent disease conditions to the
#: canonical short name "disease" used in ChannelHealthSummary.
DISEASE_TYPES: dict[str, str] = {
    "disease_fungal": "disease",
    "disease_bacterial": "disease",
}

#: Severity assignment per health class.  "healthy" is kept for completeness
#: but is not returned by classify_single when the plant is healthy.
_SEVERITY_MAP: dict[str, str] = {
    "healthy": "none",
    "nitrogen_deficiency": "moderate",
    "phosphorus_deficiency": "moderate",
    "potassium_deficiency": "moderate",
    "iron_deficiency": "moderate",
    "disease_fungal": "severe",
    "disease_bacterial": "severe",
}


# ---------------------------------------------------------------------------
# Channel aggregate result
# ---------------------------------------------------------------------------

@dataclass
class ChannelAggregate:
    """Intermediate data class holding channel-level health counts.

    This mirrors the fields required to populate a
    ``hydroponics_msgs/ChannelHealthSummary`` message.  avg_canopy_area_cm2
    is filled in by the calling node after measurement.
    """

    healthy_count: int = 0
    deficient_count: int = 0
    diseased_count: int = 0
    primary_deficiency: str = "none"
    deficiency_prevalence: float = 0.0
    avg_canopy_area_cm2: float = 0.0
    deficiency_trends: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DeficiencyClassifier
# ---------------------------------------------------------------------------

class DeficiencyClassifier:
    """Classifies individual plant health states and aggregates across channels.

    All methods are stateless; the class acts as a namespace with optional
    future configuration (e.g. severity thresholds).
    """

    # ------------------------------------------------------------------
    # Single-plant classification
    # ------------------------------------------------------------------

    @staticmethod
    def classify_single(health_class: str) -> tuple[str, str]:
        """Map a YOLO health class label to (deficiency_type, severity).

        Args:
            health_class: One of the known health class label strings
                (e.g. ``"nitrogen_deficiency"``, ``"disease_fungal"``,
                ``"healthy"``).

        Returns:
            A two-tuple ``(deficiency_type, severity)`` where:

            * ``deficiency_type`` is a short name such as ``"nitrogen"``,
              ``"disease"``, or ``"none"`` for a healthy plant.
            * ``severity`` is one of ``"none"``, ``"moderate"``,
              or ``"severe"``.

        Notes:
            Unknown labels are logged as a warning and treated as
            ``("unknown", "unknown")`` so callers can handle them
            gracefully.
        """
        if health_class == "healthy":
            return ("none", "none")

        if health_class in DEFICIENCY_TYPES:
            return (DEFICIENCY_TYPES[health_class], _SEVERITY_MAP[health_class])

        if health_class in DISEASE_TYPES:
            return (DISEASE_TYPES[health_class], _SEVERITY_MAP[health_class])

        logger.warning(
            "DeficiencyClassifier: unknown health_class '%s'; "
            "returning ('unknown', 'unknown')",
            health_class,
        )
        return ("unknown", "unknown")

    # ------------------------------------------------------------------
    # Channel-level aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def aggregate_channel(plant_states: list[str]) -> ChannelAggregate:
        """Aggregate health class labels for all plants in a channel.

        Args:
            plant_states: List of ``health_class`` strings, one per plant
                position (may include ``"healthy"`` entries).

        Returns:
            A :class:`ChannelAggregate` with counts, the most prevalent
            deficiency (or ``"none"``), and a ``deficiency_prevalence``
            fraction in the range ``[0.0, 1.0]``.
        """
        result = ChannelAggregate()
        total: int = len(plant_states)

        if total == 0:
            logger.warning("aggregate_channel called with empty plant_states list")
            return result

        deficiency_counter: Counter[str] = Counter()

        for health_class in plant_states:
            if health_class == "healthy":
                result.healthy_count += 1
            elif DeficiencyClassifier.is_disease(health_class):
                result.diseased_count += 1
            elif health_class in DEFICIENCY_TYPES:
                result.deficient_count += 1
                deficiency_counter[DEFICIENCY_TYPES[health_class]] += 1
            else:
                # Unknown / unclassified — count as healthy to avoid false
                # alarms, but log for diagnostics.
                logger.warning(
                    "aggregate_channel: unrecognised health_class '%s'; "
                    "counted as healthy",
                    health_class,
                )
                result.healthy_count += 1

        # Primary deficiency: most common deficiency label, or "none".
        if deficiency_counter:
            result.primary_deficiency = deficiency_counter.most_common(1)[0][0]
            # Prevalence = fraction of all plants with *any* deficiency or disease.
            affected: int = result.deficient_count + result.diseased_count
            result.deficiency_prevalence = affected / total

            # Deficiency trends: nutrient names present in >50% of plants.
            threshold: float = 0.5
            result.deficiency_trends = [
                nutrient
                for nutrient, count in deficiency_counter.items()
                if count / total > threshold
            ]
        else:
            result.primary_deficiency = "none"
            if result.diseased_count > 0:
                result.deficiency_prevalence = result.diseased_count / total
            else:
                result.deficiency_prevalence = 0.0
            result.deficiency_trends = []

        logger.debug(
            "aggregate_channel: total=%d  healthy=%d  deficient=%d  "
            "diseased=%d  primary='%s'  prevalence=%.2f",
            total,
            result.healthy_count,
            result.deficient_count,
            result.diseased_count,
            result.primary_deficiency,
            result.deficiency_prevalence,
        )
        return result

    # ------------------------------------------------------------------
    # Predicate helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_disease(health_class: str) -> bool:
        """Return True if the health class represents a disease condition.

        Args:
            health_class: A YOLO health class label string.

        Returns:
            ``True`` for ``"disease_fungal"`` or ``"disease_bacterial"``,
            ``False`` for all other labels including deficiencies.
        """
        return health_class in DISEASE_TYPES
