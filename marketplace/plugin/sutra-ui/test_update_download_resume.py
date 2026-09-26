"""test_update_download_resume.py -- a download that drops is resumed, and never mis-blamed.

The failure this pins actually happened, to the owner, on 2026-09-21. He pressed
the update button on a 421MB release and was told

    Could not check. checksum mismatch: published 1e553c0ebfc2bb0b,
    downloaded 9dbb56a024306d02

which says, in the only words the app had, "the file GitHub published is not the
file you got, and there is nothing you can do about it". The release was fine. I
verified the published checksum against the workflow that made it, and the DMG
against the checksum. His connection had dropped part-way through, twice, and so
did two of mine from the same network -- one through `gh`, which died at
263,630,848 bytes of 420,889,852, and one through curl.

The defect was that `download_and_verify` read the body with a single
`copyfileobj` and never once asked how many bytes it should have got. A socket
that closes early IS end-of-file to copyfileobj, so a half file lands on disk
looking perfectly well-formed, and the checksum -- the next thing to run -- is
the first gate to notice. It then blames the only thing it knows about, which is
the release.

Three things are pinned here:

  1. A dropped connection is RESUMED, with a Range header, so a 421MB download
     that dies at 400MB costs the last 21MB and not another 421.
  2. A download that stays short is named as short, in bytes, and says it is a
     network problem. The word "checksum" must not appear -- that was the lie.
  3. A complete file whose checksum is wrong is DELETED. Staging keeps the image
     between attempts so it can be resumed; a full-length wrong file left there
     would make every later attempt ask for nothing and fail identically for
     ever.

Run: .venv/bin/python -m pytest -q test_update_download_resume.py
"""
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import updates  # noqa: E402


WHOLE = b"".join(bytes([i % 251]) for i in range(20000))   # stands in for the DMG


class _Body(io.BytesIO):
    """A response body that can be made to stop early, the way a dropped TCP
    connection does: readable, well-formed, and short."""

    def __init__(self, data, cut_at=None):
        io.BytesIO.__init__(self, data if cut_at is None else data[:cut_at])


class _Resp:
    """The bits of an HTTPResponse that the downloader touches."""

    def __init__(self, body, status=200, content_length=None):
        self._body = body
        self.status = status
        self.headers = {} if content_length is None else {
            "Content-Length": str(content_length)}
        self.headers = _Headers(self.headers)

    def read(self, n=-1):
        return self._body.read(n)

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Headers(dict):
    def get(self, k, default=None):
        for key, v in self.items():
            if key.lower() == k.lower():
                return v
        return default


class DownloadResume(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="sutra-dl-test-"))
        self.dmg = self.dir / "Sutra-arm64.dmg"
        # no real sleeping between attempts: the retry gap is not what is under test
        p = mock.patch.object(updates.time, "sleep", lambda *_: None)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    # 1 -- the drop is picked up where it left off ------------------------------

    def test_a_dropped_connection_is_resumed_not_restarted(self):
        cut = 12000
        seen = []

        def fake_urlopen(req, timeout=None):
            seen.append(req.headers.get("Range") or req.headers.get("range"))
            start = 0
            rng = req.headers.get("Range") or req.headers.get("range")
            if rng:
                start = int(str(rng).split("=")[1].split("-")[0])
                return _Resp(_Body(WHOLE[start:]), status=206,
                             content_length=len(WHOLE) - start)
            return _Resp(_Body(WHOLE, cut_at=cut), status=200,
                         content_length=len(WHOLE))

        with mock.patch.object(updates.urllib.request, "urlopen", fake_urlopen):
            updates._fetch_dmg("https://example.invalid/Sutra-arm64.dmg",
                               self.dmg, len(WHOLE))

        self.assertEqual(self.dmg.read_bytes(), WHOLE,
                         "the resumed download did not reassemble the whole file")
        self.assertEqual(seen[0], None, "the first attempt should not ask for a range")
        self.assertEqual(seen[1], "bytes=%d-" % cut,
                         "the second attempt must resume at the byte it stopped on, "
                         "not start the whole download again")

    # 2 -- a short download is named as short, and blamed on the network --------

    def test_a_download_that_stays_short_says_so_and_never_says_checksum(self):
        def always_short(req, timeout=None):
            return _Resp(_Body(WHOLE, cut_at=9000), status=200,
                         content_length=len(WHOLE))

        with mock.patch.object(updates.urllib.request, "urlopen", always_short):
            with self.assertRaises(RuntimeError) as caught:
                updates._fetch_dmg("https://example.invalid/Sutra-arm64.dmg",
                                   self.dmg, len(WHOLE))

        said = str(caught.exception)
        self.assertIn("cut short", said, "the real cause must be named")
        self.assertIn("9,000", said, "how far it got must be said, in bytes")
        self.assertIn("20,000", said, "how far it should have got must be said too")
        self.assertIn("network problem", said,
                      "the person must be told it is their link, not the release")
        self.assertNotIn("checksum", said.lower(),
                         "blaming the checksum for a truncated download is the "
                         "exact defect this file exists to stop")
        self.assertFalse(self.dmg.exists(),
                         "a short file must not be left behind to be found later")

    # 3 -- a full-length wrong file is deleted, not kept and re-blessed ---------

    def test_a_complete_but_wrong_file_is_deleted_so_a_retry_can_work(self):
        latest = {"error": None, "download_url": "https://example.invalid/d.dmg",
                  "asset": "Sutra-arm64.dmg", "size": len(WHOLE),
                  "sha256_url": "https://example.invalid/d.dmg.sha256",
                  "version": "9.9.9"}

        def fake_urlopen(req, timeout=None):
            if str(req.full_url).endswith(".sha256"):
                return _Resp(_Body(b"%s  Sutra-arm64.dmg\n" % (b"f" * 64)))
            return _Resp(_Body(WHOLE), status=200, content_length=len(WHOLE))

        with mock.patch.object(updates, "_latest_desktop", lambda: latest), \
             mock.patch.object(updates.urllib.request, "urlopen", fake_urlopen):
            with self.assertRaises(RuntimeError) as caught:
                updates.download_and_verify(dest_dir=str(self.dir))

        said = str(caught.exception)
        self.assertIn("does not match the one published", said)
        self.assertIn("try the update again", said,
                      "the person must be told the retry is worth taking")
        self.assertFalse(self.dmg.exists(),
                         "a wrong image left on disk makes every later attempt "
                         "resume into it and fail the same way for ever")


class DownloadProgress(unittest.TestCase):
    """The update card shows MB, speed and time left (founder 2026-09-26). The
    download is the only thing that knows those numbers, so it writes them to a
    small file the panel reads."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="sutra-dl-prog-"))
        self.dmg = self.dir / "Sutra-arm64.dmg"
        self.pfile = self.dir / "download-progress.json"
        for p in (mock.patch.object(updates.time, "sleep", lambda *_: None),
                  mock.patch.object(updates, "_progress_path", lambda: self.pfile)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_nothing_downloading_reads_as_none(self):
        self.assertIsNone(updates.download_progress())

    def test_a_download_leaves_done_equal_to_total(self):
        with mock.patch.object(updates.urllib.request, "urlopen",
                               lambda req, timeout=None: _Resp(_Body(WHOLE), content_length=len(WHOLE))):
            updates._fetch_dmg("https://example.invalid/x.dmg", self.dmg, len(WHOLE))
        p = updates.download_progress()
        self.assertIsNotNone(p, "a finished download wrote no progress")
        self.assertEqual(p["done"], len(WHOLE))
        self.assertEqual(p["total"], len(WHOLE))
        self.assertEqual(p["phase"], "verifying")

    def test_progress_moves_during_the_download(self):
        seen = []
        real = updates._progress_write
        with mock.patch.object(updates, "_progress_write",
                               lambda **kw: (seen.append(kw.get("done")), real(**kw))), \
             mock.patch.object(updates, "PROGRESS_EVERY_S", 0), \
             mock.patch.object(updates.urllib.request, "urlopen",
                               lambda req, timeout=None: _Resp(_Body(WHOLE), content_length=len(WHOLE))):
            updates._fetch_dmg("https://example.invalid/x.dmg", self.dmg, len(WHOLE))
        self.assertGreater(len(set(seen)), 2, "progress was not reported as bytes arrived")
        self.assertEqual(seen, sorted(seen), "progress went backwards")

    def test_a_stale_download_is_not_reported_as_live(self):
        import json
        updates._progress_write(phase="downloading", done=10, total=100, start_done=0)
        d = json.loads(self.pfile.read_text())
        d["ts"] = d["ts"] - 600
        self.pfile.write_text(json.dumps(d))
        self.assertIsNone(updates.download_progress(),
                          "a download that stopped reporting ten minutes ago is shown as live")

    def test_clear_removes_it(self):
        updates._progress_write(phase="downloading", done=1, total=2, start_done=0)
        updates.progress_clear()
        self.assertIsNone(updates.download_progress())


if __name__ == "__main__":
    unittest.main(verbosity=2)
