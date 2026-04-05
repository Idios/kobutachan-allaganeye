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

    def test_workers_none_is_valid(self):
        config = SplitConfig(workers=None)
        assert config.workers is None

    def test_workers_positive_is_valid(self):
        config = SplitConfig(workers=4)
        assert config.workers == 4

    def test_workers_zero_raises(self):
        with pytest.raises(ConfigValidationError, match="workers"):
            SplitConfig(workers=0)

    def test_workers_negative_raises(self):
        with pytest.raises(ConfigValidationError, match="workers"):
            SplitConfig(workers=-1)

    def test_exit_code_is_5(self):
        with pytest.raises(ConfigValidationError) as exc_info:
            SplitConfig(sample_interval=-1.0)
        assert exc_info.value.exit_code == 5
