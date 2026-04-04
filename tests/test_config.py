"""Tests for configuration validation."""

import pytest

from allaganeye.config import SplitConfig
from allaganeye.exceptions import ConfigValidationError


class TestSplitConfigValidation:
    def test_valid_defaults(self):
        config = SplitConfig()
        assert config.sample_interval == 1.0
        assert config.blackout_threshold == 15.0
        assert config.min_match_duration == 300.0

    def test_valid_custom_values(self):
        config = SplitConfig(
            sample_interval=0.5,
            blackout_threshold=0.0,
            min_match_duration=60.0,
        )
        assert config.sample_interval == 0.5
        assert config.blackout_threshold == 0.0
        assert config.min_match_duration == 60.0

    def test_blackout_threshold_boundary_255(self):
        config = SplitConfig(blackout_threshold=255.0)
        assert config.blackout_threshold == 255.0

    def test_sample_interval_zero_raises(self):
        with pytest.raises(ConfigValidationError, match="sample-interval"):
            SplitConfig(sample_interval=0.0)

    def test_sample_interval_negative_raises(self):
        with pytest.raises(ConfigValidationError, match="sample-interval"):
            SplitConfig(sample_interval=-1.0)

    def test_blackout_threshold_negative_raises(self):
        with pytest.raises(ConfigValidationError, match="blackout-threshold"):
            SplitConfig(blackout_threshold=-1.0)

    def test_blackout_threshold_over_255_raises(self):
        with pytest.raises(ConfigValidationError, match="blackout-threshold"):
            SplitConfig(blackout_threshold=256.0)

    def test_min_match_duration_zero_raises(self):
        with pytest.raises(ConfigValidationError, match="min-match-duration"):
            SplitConfig(min_match_duration=0.0)

    def test_min_match_duration_negative_raises(self):
        with pytest.raises(ConfigValidationError, match="min-match-duration"):
            SplitConfig(min_match_duration=-100.0)
