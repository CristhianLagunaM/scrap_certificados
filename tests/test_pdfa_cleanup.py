import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app as module


class PdfaCleanupTests(unittest.TestCase):
    def test_completed_job_keeps_only_download(self):
        with tempfile.TemporaryDirectory() as root:
            uploaded = Path(root) / "entrada.zip"
            uploaded.touch()
            work = Path(root) / "job"
            for name in ("input", "tmp_convertidos", "resultado"):
                directory = work / name
                directory.mkdir(parents=True)
                (directory / "documento.pdf").touch()
            output = work / "salida.zip"
            output.write_bytes(b"resultado")

            module.cleanup_pdfa_job(uploaded, work, keep_result=True)

            self.assertFalse(uploaded.exists())
            self.assertEqual(list(work.iterdir()), [output])
            self.assertEqual(output.read_bytes(), b"resultado")

    def test_failed_job_removes_partial_download_and_upload(self):
        with tempfile.TemporaryDirectory() as root:
            uploaded = Path(root) / "entrada.zip"
            uploaded.touch()
            work = Path(root) / "job"
            work.mkdir()
            (work / "parcial.zip").touch()

            module.cleanup_pdfa_job(uploaded, work, keep_result=False)
            module.cleanup_pdfa_job(uploaded, work, keep_result=False)

            self.assertFalse(uploaded.exists())
            self.assertFalse(work.exists())

    def test_upload_removal_failure_does_not_skip_work_cleanup(self):
        with tempfile.TemporaryDirectory() as root:
            uploaded = Path(root) / "entrada.zip"
            uploaded.touch()
            work = Path(root) / "job"
            work.mkdir()
            logger = SimpleNamespace(logger=logging.getLogger("pdfa-cleanup-test"))
            with patch.object(module, "app", logger), patch.object(
                Path, "unlink", side_effect=PermissionError("denegado")
            ), self.assertLogs("pdfa-cleanup-test", level="ERROR"):
                module.cleanup_pdfa_job(uploaded, work, keep_result=False)

            self.assertFalse(work.exists())
