"""Tests for GPU vendor probe (#546)."""

from unittest.mock import patch


class TestProbeGpuVendors:
    """probe_gpu_vendors() vendor detection across platforms."""

    @patch("allaganeye.system_info._run_text")
    def test_nvidia_only_via_nvidia_smi(self, mock_run):
        """nvidia-smi success + wmic no other GPU -> ["nvidia"]."""

        def side_effect(cmd, **_kwargs):
            if cmd[0] == "nvidia-smi":
                return "NVIDIA GeForce RTX 5090, 32768\n"
            if cmd[0] == "wmic":
                return "Name\nNVIDIA GeForce RTX 5090\n"
            return None

        mock_run.side_effect = side_effect

        with patch("allaganeye.system_info.platform.system", return_value="Windows"):
            from allaganeye.system_info import probe_gpu_vendors

            assert probe_gpu_vendors() == ["nvidia"]

    @patch("allaganeye.system_info._run_text")
    def test_windows_dual_nvidia_and_amd(self, mock_run):
        """NVIDIA dGPU + AMD iGPU (現環境と同じ構成) -> ["nvidia", "amd"]."""

        def side_effect(cmd, **_kwargs):
            if cmd[0] == "nvidia-smi":
                return "NVIDIA GeForce RTX 5090, 32768\n"
            if cmd[0] == "wmic":
                return "Name\nNVIDIA GeForce RTX 5090\nAMD Radeon(TM) Graphics\n"
            return None

        mock_run.side_effect = side_effect

        with patch("allaganeye.system_info.platform.system", return_value="Windows"):
            from allaganeye.system_info import probe_gpu_vendors

            assert probe_gpu_vendors() == ["nvidia", "amd"]

    @patch("allaganeye.system_info._run_text")
    def test_windows_amd_only_igpu(self, mock_run):
        """AMD iGPU のみ (NVIDIA 無し) -> ["amd"]."""

        def side_effect(cmd, **_kwargs):
            if cmd[0] == "nvidia-smi":
                return None  # nvidia-smi not found / fail
            if cmd[0] == "wmic":
                return "Name\nAMD Radeon(TM) Graphics\n"
            return None

        mock_run.side_effect = side_effect

        with patch("allaganeye.system_info.platform.system", return_value="Windows"):
            from allaganeye.system_info import probe_gpu_vendors

            assert probe_gpu_vendors() == ["amd"]

    @patch("allaganeye.system_info._run_text")
    def test_windows_intel_only_igpu(self, mock_run):
        """Intel iGPU のみ -> ["intel"] (option は受け入れるが実装は別 issue #550)."""

        def side_effect(cmd, **_kwargs):
            if cmd[0] == "nvidia-smi":
                return None
            if cmd[0] == "wmic":
                return "Name\nIntel(R) UHD Graphics 770\n"
            return None

        mock_run.side_effect = side_effect

        with patch("allaganeye.system_info.platform.system", return_value="Windows"):
            from allaganeye.system_info import probe_gpu_vendors

            assert probe_gpu_vendors() == ["intel"]

    @patch("allaganeye.system_info._run_text")
    def test_linux_lspci_nvidia_intel(self, mock_run):
        """Linux lspci で NVIDIA dGPU + Intel iGPU を検出."""

        def side_effect(cmd, **_kwargs):
            if cmd[0] == "nvidia-smi":
                return "NVIDIA GeForce GTX 1080, 8192\n"
            if cmd[0] == "lspci":
                return (
                    "00:02.0 VGA compatible controller: "
                    "Intel Corporation AlderLake-S GT1 [UHD Graphics 770]\n"
                    "01:00.0 VGA compatible controller: "
                    "NVIDIA Corporation GA102 [GeForce GTX 1080]\n"
                )
            return None

        mock_run.side_effect = side_effect

        with patch("allaganeye.system_info.platform.system", return_value="Linux"):
            from allaganeye.system_info import probe_gpu_vendors

            vendors = probe_gpu_vendors()
            # NVIDIA first (nvidia-smi), then intel from lspci
            assert "nvidia" in vendors
            assert "intel" in vendors

    @patch("allaganeye.system_info._run_text")
    def test_empty_when_all_probes_fail(self, mock_run):
        """全 probe 失敗時は空 list (CPU mode fallback)."""
        mock_run.return_value = None

        with patch("allaganeye.system_info.platform.system", return_value="Windows"):
            from allaganeye.system_info import probe_gpu_vendors

            assert probe_gpu_vendors() == []

    @patch("allaganeye.system_info._run_text")
    def test_no_duplicates_when_nvidia_also_in_wmic(self, mock_run):
        """nvidia-smi + wmic 両方で NVIDIA を検出しても結果に重複なし."""

        def side_effect(cmd, **_kwargs):
            if cmd[0] == "nvidia-smi":
                return "NVIDIA GeForce RTX 5090, 32768\n"
            if cmd[0] == "wmic":
                return "Name\nNVIDIA GeForce RTX 5090\nAMD Radeon(TM) Graphics\n"
            return None

        mock_run.side_effect = side_effect

        with patch("allaganeye.system_info.platform.system", return_value="Windows"):
            from allaganeye.system_info import probe_gpu_vendors

            vendors = probe_gpu_vendors()
            assert vendors.count("nvidia") == 1
            assert vendors == ["nvidia", "amd"]
