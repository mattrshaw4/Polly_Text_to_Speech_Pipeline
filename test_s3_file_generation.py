"""
Tests to verify that on_merge.yml and on_pull_request.yml will correctly
generate prod and beta files in S3 via synthesize.py.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, mock_open
import yaml


class TestSynthesizeScript(unittest.TestCase):
    """Verify synthesize.py generates example.mp3 from speech.txt."""

    def _run_synthesize(self, mock_audio_data=b"fake-mp3-bytes"):
        """Helper: run synthesize.py with a mocked boto3 Polly client."""
        mock_audio_stream = MagicMock()
        mock_audio_stream.read.return_value = mock_audio_data

        mock_response = {"AudioStream": mock_audio_stream}

        mock_polly = MagicMock()
        mock_polly.synthesize_speech.return_value = mock_response

        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_polly

        speech_text = "sample text. This should convert to audio."
        written_data = {}

        real_open = open

        def patched_open(path, mode="r", *args, **kwargs):
            if path == "speech.txt" and "r" in mode:
                return mock_open(read_data=speech_text)()
            if path == "example.mp3" and "wb" in mode:
                m = MagicMock()
                m.__enter__ = lambda s: s
                m.__exit__ = MagicMock(return_value=False)
                m.write = lambda data: written_data.update({"mp3": data})
                return m
            return real_open(path, mode, *args, **kwargs)

        with patch.dict(sys.modules, {"boto3": mock_boto3}):
            with patch("builtins.open", side_effect=patched_open):
                import importlib
                import types

                # Execute synthesize.py as a fresh module
                src_path = os.path.join(os.path.dirname(__file__), "synthesize.py")
                with real_open(src_path, "r") as f:
                    source = f.read()

                namespace = {"boto3": mock_boto3}
                with patch("builtins.open", side_effect=patched_open):
                    exec(compile(source, "synthesize.py", "exec"), namespace)

        return mock_polly, written_data

    def test_polly_called_with_correct_parameters(self):
        """synthesize.py must call Polly with the expected engine, voice, and format."""
        mock_polly, _ = self._run_synthesize()

        mock_polly.synthesize_speech.assert_called_once()
        call_kwargs = mock_polly.synthesize_speech.call_args[1]

        self.assertEqual(call_kwargs["Engine"], "generative")
        self.assertEqual(call_kwargs["OutputFormat"], "mp3")
        self.assertEqual(call_kwargs["VoiceId"], "Stephen")

    def test_example_mp3_written(self):
        """synthesize.py must write audio bytes to example.mp3."""
        mock_audio = b"fake-mp3-audio-content"
        _, written_data = self._run_synthesize(mock_audio_data=mock_audio)

        self.assertIn("mp3", written_data, "example.mp3 was never written")
        self.assertEqual(written_data["mp3"], mock_audio)

    def test_boto3_client_is_polly(self):
        """synthesize.py must create a boto3 client for 'polly'."""
        mock_audio_stream = MagicMock()
        mock_audio_stream.read.return_value = b"bytes"
        mock_polly = MagicMock()
        mock_polly.synthesize_speech.return_value = {"AudioStream": mock_audio_stream}
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_polly

        speech_text = "sample text."
        real_open = open

        def patched_open(path, mode="r", *args, **kwargs):
            if path == "speech.txt" and "r" in mode:
                return mock_open(read_data=speech_text)()
            if path == "example.mp3" and "wb" in mode:
                m = MagicMock()
                m.__enter__ = lambda s: s
                m.__exit__ = MagicMock(return_value=False)
                m.write = MagicMock()
                return m
            return real_open(path, mode, *args, **kwargs)

        src_path = os.path.join(os.path.dirname(__file__), "synthesize.py")
        with real_open(src_path, "r") as f:
            source = f.read()

        # patch sys.modules so the `import boto3` inside synthesize.py resolves
        # to our mock without needing the real package installed.
        with patch.dict(sys.modules, {"boto3": mock_boto3}):
            with patch("builtins.open", side_effect=patched_open):
                exec(compile(source, "synthesize.py", "exec"), {})

        mock_boto3.client.assert_called_once_with("polly")


class TestWorkflowS3Paths(unittest.TestCase):
    """Parse the GitHub Actions YAML files and verify S3 path configuration."""

    WORKFLOWS_DIR = os.path.join(os.path.dirname(__file__), ".github", "workflows")

    def _load_workflow(self, filename):
        path = os.path.join(self.WORKFLOWS_DIR, filename)
        with open(path, "r") as f:
            return yaml.safe_load(f)

    # ---------- on_merge.yml ----------

    def test_on_merge_triggers_on_push_to_main(self):
        wf = self._load_workflow("on_merge.yml")
        # PyYAML parses unquoted `on:` as boolean True (YAML 1.1 reserved word).
        trigger = wf.get("on") or wf.get(True)
        self.assertIn("main", trigger["push"]["branches"])

    def test_on_merge_s3_path_is_prod(self):
        wf = self._load_workflow("on_merge.yml")
        job = list(wf["jobs"].values())[0]
        self.assertEqual(job["env"]["S3_Path"], "prod",
                         "on_merge.yml must set S3_Path=prod")

    def test_on_merge_uploads_to_prod_prefix(self):
        wf = self._load_workflow("on_merge.yml")
        job = list(wf["jobs"].values())[0]
        run_steps = [s["run"] for s in job["steps"] if "run" in s]
        combined = "\n".join(run_steps)

        self.assertIn("$S3_Path/example.mp3", combined,
                      "on_merge.yml must upload example.mp3 under the prod prefix")

    def test_on_merge_uses_s3_bucket_secret(self):
        wf = self._load_workflow("on_merge.yml")
        job = list(wf["jobs"].values())[0]
        bucket_env = job["env"]["S3_BUCKET_NAME"]
        self.assertIn("S3_BUCKET_NAME", bucket_env,
                      "Bucket name must come from the S3_BUCKET_NAME secret")

    # ---------- on_pull_request.yml ----------

    def test_on_pull_request_triggers_on_pr_to_main(self):
        wf = self._load_workflow("on_pull_request.yml")
        self.assertIn("main", wf["on"]["pull_request"]["branches"])

    def test_on_pull_request_s3_path_is_beta(self):
        wf = self._load_workflow("on_pull_request.yml")
        job = list(wf["jobs"].values())[0]
        self.assertEqual(job["env"]["S3_Path"], "beta",
                         "on_pull_request.yml must set S3_Path=beta")

    def test_on_pull_request_uploads_to_beta_prefix(self):
        wf = self._load_workflow("on_pull_request.yml")
        job = list(wf["jobs"].values())[0]
        run_steps = [s["run"] for s in job["steps"] if "run" in s]
        combined = "\n".join(run_steps)

        self.assertIn("$S3_Path/example.mp3", combined,
                      "on_pull_request.yml must upload example.mp3 under the beta prefix")

    def test_on_pull_request_uses_s3_bucket_secret(self):
        wf = self._load_workflow("on_pull_request.yml")
        job = list(wf["jobs"].values())[0]
        bucket_env = job["env"]["S3_BUCKET_NAME"]
        self.assertIn("S3_BUCKET_NAME", bucket_env,
                      "Bucket name must come from the S3_BUCKET_NAME secret")

    # ---------- shared sanity checks ----------

    def test_prod_and_beta_paths_are_distinct(self):
        """Prod and beta must use different S3 prefixes."""
        merge_wf = self._load_workflow("on_merge.yml")
        pr_wf = self._load_workflow("on_pull_request.yml")

        prod_path = list(merge_wf["jobs"].values())[0]["env"]["S3_Path"]
        beta_path = list(pr_wf["jobs"].values())[0]["env"]["S3_Path"]

        self.assertNotEqual(prod_path, beta_path,
                            "Prod and beta S3 paths must be different")

    def test_both_workflows_run_synthesize_py(self):
        """Both workflows must invoke synthesize.py to generate the MP3."""
        for filename in ("on_merge.yml", "on_pull_request.yml"):
            with self.subTest(workflow=filename):
                wf = self._load_workflow(filename)
                job = list(wf["jobs"].values())[0]
                run_steps = [s["run"] for s in job["steps"] if "run" in s]
                combined = "\n".join(run_steps)
                self.assertIn("python synthesize.py", combined,
                              f"{filename} must run synthesize.py")

    def test_both_workflows_configure_aws_credentials(self):
        """Both workflows must configure AWS credentials before uploading."""
        for filename in ("on_merge.yml", "on_pull_request.yml"):
            with self.subTest(workflow=filename):
                wf = self._load_workflow(filename)
                job = list(wf["jobs"].values())[0]
                action_names = [s.get("uses", "") for s in job["steps"]]
                self.assertTrue(
                    any("configure-aws-credentials" in a for a in action_names),
                    f"{filename} must configure AWS credentials"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
