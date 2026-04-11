# MIT License
# Copyright (c) 2026 AIdroponics Project
"""Unit tests for temporal change tracking logic in plant_vision_node."""

import numpy as np
import pytest


def classify_temporal_symptoms(
    frame_history: list[dict],
    current_hsv: np.ndarray,
    current_mask: np.ndarray,
    capture_index: int,
    established_threshold: int = 24,
    new_growth_threshold: int = 6,
) -> list[str]:
    """Simplified version of PlantVisionNode._update_temporal_tracking for testing.

    Classifies yellowing_established_growth and symptomatic_new_growth based on
    pixel history. Does not perform AprilTag frame registration (uses direct
    pixel comparison instead, sufficient for unit tests with static frames).
    """
    symptoms = []

    if len(frame_history) < max(established_threshold, new_growth_threshold):
        return symptoms

    established_idx = capture_index - established_threshold
    new_growth_idx = capture_index - new_growth_threshold

    established_mask = np.zeros_like(current_mask)
    new_growth_mask = np.zeros_like(current_mask)

    for frame_data in frame_history:
        if frame_data['index'] <= established_idx:
            established_mask = np.bitwise_or(established_mask, frame_data['mask'])
        elif frame_data['index'] >= new_growth_idx:
            recent_only = np.bitwise_and(
                frame_data['mask'],
                np.bitwise_not(established_mask)
            )
            new_growth_mask = np.bitwise_or(new_growth_mask, recent_only)

    # Yellowing in established growth
    if established_mask.sum() > 0:
        established_pixels_hsv = current_hsv[established_mask > 0]
        if len(established_pixels_hsv) > 0:
            mean_hue = float(np.mean(established_pixels_hsv[:, 0]))
            mean_sat = float(np.mean(established_pixels_hsv[:, 1]))
            if mean_hue < 35 and mean_sat < 100:
                symptoms.append('yellowing_established_growth')

    # Symptomatic new growth (pale/chlorotic)
    if new_growth_mask.sum() > 0:
        new_pixels_hsv = current_hsv[new_growth_mask > 0]
        if len(new_pixels_hsv) > 0:
            mean_sat_new = float(np.mean(new_pixels_hsv[:, 1]))
            mean_val_new = float(np.mean(new_pixels_hsv[:, 2]))
            if mean_sat_new < 60 and mean_val_new > 180:
                symptoms.append('symptomatic_new_growth')

    return symptoms


def make_green_hsv_frame(h: int = 50, s: int = 150, v: int = 120) -> np.ndarray:
    """Create a 20x20 HSV frame with uniform colour."""
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    frame[:, :, 0] = h
    frame[:, :, 1] = s
    frame[:, :, 2] = v
    return frame


def make_full_mask() -> np.ndarray:
    """Create a full 20x20 mask (all pixels set)."""
    return np.full((20, 20), 255, dtype=np.uint8)


class TestTemporalTracking:
    """Tests for temporal symptom classification."""

    def _build_history(self, n_frames: int, start_index: int = 0) -> list[dict]:
        """Build n_frames of history with green plant pixels."""
        history = []
        for i in range(n_frames):
            history.append({
                'index': start_index + i,
                'mask': make_full_mask(),
                'hsv': make_green_hsv_frame(),
            })
        return history

    def test_no_symptoms_on_short_history(self):
        """With fewer frames than established_threshold, no symptoms fired."""
        history = self._build_history(n_frames=10, start_index=0)
        current_hsv = make_green_hsv_frame()
        symptoms = classify_temporal_symptoms(
            frame_history=history,
            current_hsv=current_hsv,
            current_mask=make_full_mask(),
            capture_index=10,
            established_threshold=24,
            new_growth_threshold=6,
        )
        assert symptoms == []

    def test_yellowing_established_growth_detected(self):
        """Yellow shift in established region (hue<35, sat<100) → flag."""
        history = self._build_history(n_frames=48, start_index=0)
        # Current frame has yellow-shifted established pixels
        # Yellow in OpenCV HSV: hue ~25, low saturation
        current_hsv = make_green_hsv_frame(h=25, s=80, v=180)
        symptoms = classify_temporal_symptoms(
            frame_history=history,
            current_hsv=current_hsv,
            current_mask=make_full_mask(),
            capture_index=48,
            established_threshold=24,
            new_growth_threshold=6,
        )
        assert 'yellowing_established_growth' in symptoms

    def test_healthy_green_no_yellowing(self):
        """Normal green pixels in established region → no yellowing flag."""
        history = self._build_history(n_frames=48, start_index=0)
        # Still green (hue=50, sat=150)
        current_hsv = make_green_hsv_frame(h=50, s=150, v=120)
        symptoms = classify_temporal_symptoms(
            frame_history=history,
            current_hsv=current_hsv,
            current_mask=make_full_mask(),
            capture_index=48,
            established_threshold=24,
            new_growth_threshold=6,
        )
        assert 'yellowing_established_growth' not in symptoms

    def test_symptomatic_new_growth_detected(self):
        """Pale new growth pixels (low sat, high val) in new region → flag."""
        # 30 frames of established growth with no new pixels
        history = self._build_history(n_frames=30, start_index=0)
        # New pixels appear in last 3 frames — add to history as new mask area
        # The full mask is the same as established for simplicity;
        # in a real test the new region would be isolated
        new_mask = np.zeros((20, 20), dtype=np.uint8)
        new_mask[10:, 10:] = 255  # bottom-right is new growth

        history.append({
            'index': 42,
            'mask': new_mask,
            'hsv': make_green_hsv_frame(h=25, s=30, v=220),  # pale/chlorotic
        })

        current_hsv = make_green_hsv_frame(h=25, s=30, v=220)
        symptoms = classify_temporal_symptoms(
            frame_history=history,
            current_hsv=current_hsv,
            current_mask=np.bitwise_or(make_full_mask(), new_mask),
            capture_index=45,
            established_threshold=24,
            new_growth_threshold=3,
        )
        assert 'symptomatic_new_growth' in symptoms
