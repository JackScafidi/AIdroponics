# MIT License
# Copyright (c) 2026 Autoponics Project
"""Unit tests for NDVI computation logic in plant_vision_node."""

import numpy as np
import pytest


def compute_ndvi(ndvi_frame: np.ndarray) -> np.ndarray:
    """Replicate the NDVI formula from plant_vision_node._compute_ndvi.

    With NoIR camera + blue gel filter:
      Red channel  = NIR
      Blue channel = visible blue
      NDVI = (NIR - visible) / (NIR + visible)
    """
    blue_ch = ndvi_frame[:, :, 0].astype(np.float32)
    red_ch = ndvi_frame[:, :, 2].astype(np.float32)
    nir = red_ch
    visible = blue_ch
    denominator = nir + visible
    denominator = np.where(denominator == 0, 1e-6, denominator)
    ndvi_array = (nir - visible) / denominator
    return np.clip(ndvi_array, -1.0, 1.0)


def make_frame(nir_value: int, visible_value: int) -> np.ndarray:
    """Create a synthetic 10x10 NoIR frame with uniform channel values.

    Args:
        nir_value: Value for red channel (NIR proxy).
        visible_value: Value for blue channel (visible blue proxy).
    """
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    frame[:, :, 2] = nir_value    # red channel = NIR
    frame[:, :, 0] = visible_value  # blue channel = visible
    return frame


class TestNDVIComputation:
    """Tests for NDVI computation correctness."""

    def test_healthy_plant(self):
        """Healthy plant: high NIR, moderate visible → NDVI ~0.6-0.8."""
        frame = make_frame(nir_value=200, visible_value=50)
        ndvi = compute_ndvi(frame)
        mean_ndvi = float(np.mean(ndvi))
        expected = (200 - 50) / (200 + 50)  # = 0.6
        assert abs(mean_ndvi - expected) < 0.01

    def test_stressed_plant(self):
        """Stressed plant: reduced NIR reflection → NDVI ~0.2."""
        frame = make_frame(nir_value=120, visible_value=80)
        ndvi = compute_ndvi(frame)
        mean_ndvi = float(np.mean(ndvi))
        expected = (120 - 80) / (120 + 80)  # = 0.2
        assert abs(mean_ndvi - expected) < 0.01

    def test_dead_bare_soil(self):
        """Dead plant / bare soil: NIR ≈ visible → NDVI ~0."""
        frame = make_frame(nir_value=100, visible_value=100)
        ndvi = compute_ndvi(frame)
        mean_ndvi = float(np.mean(ndvi))
        assert abs(mean_ndvi) < 0.01

    def test_non_plant_negative_ndvi(self):
        """Water/non-plant: visible > NIR → NDVI < 0."""
        frame = make_frame(nir_value=50, visible_value=150)
        ndvi = compute_ndvi(frame)
        mean_ndvi = float(np.mean(ndvi))
        expected = (50 - 150) / (50 + 150)  # = -0.5
        assert mean_ndvi < 0
        assert abs(mean_ndvi - expected) < 0.01

    def test_clamped_to_minus_one(self):
        """Result is clamped to [-1, 1] even with extreme values."""
        frame = make_frame(nir_value=0, visible_value=255)
        ndvi = compute_ndvi(frame)
        assert np.all(ndvi >= -1.0)
        assert np.all(ndvi <= 1.0)

    def test_zero_denominator_no_crash(self):
        """Zero NIR and visible should not cause division by zero."""
        frame = make_frame(nir_value=0, visible_value=0)
        ndvi = compute_ndvi(frame)  # Should not raise
        assert ndvi.shape == (10, 10)

    def test_ndvi_range_always_valid(self):
        """NDVI values must always be in [-1, 1] regardless of input."""
        for nir in [0, 50, 128, 200, 255]:
            for vis in [0, 50, 128, 200, 255]:
                frame = make_frame(nir_value=nir, visible_value=vis)
                ndvi = compute_ndvi(frame)
                assert np.all(ndvi >= -1.0), f'NDVI below -1 for NIR={nir}, vis={vis}'
                assert np.all(ndvi <= 1.0), f'NDVI above 1 for NIR={nir}, vis={vis}'
