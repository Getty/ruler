import os
import tempfile
import threading
import unittest

import helper  # noqa: F401
from ruler import log


class LogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_log_is_empty(self):
        self.assertEqual(log.read(self.data, "abc"), [])

    def test_append_and_read(self):
        log.append(self.data, "abc", {"event": "loaded", "file_path": "/a"})
        log.append(self.data, "abc", {"event": "compact"})
        self.assertEqual(
            log.read(self.data, "abc"),
            [{"event": "loaded", "file_path": "/a"}, {"event": "compact"}],
        )

    def test_sessions_are_separate(self):
        log.append(self.data, "abc", {"event": "compact"})
        self.assertEqual(log.read(self.data, "def"), [])

    def test_broken_lines_are_skipped(self):
        log.append(self.data, "abc", {"event": "compact"})
        with open(log.log_path(self.data, "abc"), "a") as fh:
            fh.write('{"event": "loa\n[1]\n')
        log.append(self.data, "abc", {"event": "loaded", "file_path": "/a"})
        self.assertEqual(len(log.read(self.data, "abc")), 2)

    def test_unreadable_log_raises(self):
        os.makedirs(log.log_path(self.data, "abc"))
        with self.assertRaises(OSError):
            log.read(self.data, "abc")

    def test_concurrent_appends_keep_every_line(self):
        def write(number):
            for index in range(50):
                log.append(self.data, "abc", {"event": "loaded", "file_path": "/%d/%d" % (number, index)})

        threads = [threading.Thread(target=write, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len({e["file_path"] for e in log.read(self.data, "abc")}), 400)

    def test_pending(self):
        self.assertIsNone(log.get_pending(self.data, "abc"))
        log.set_pending(self.data, "abc", 0)
        self.assertEqual(log.get_pending(self.data, "abc"), 0)
        log.set_pending(self.data, "abc", 1)
        self.assertEqual(log.get_pending(self.data, "abc"), 1)
        self.assertEqual(os.listdir(os.path.join(self.data, "pending")), ["abc"])
        log.clear_pending(self.data, "abc")
        self.assertIsNone(log.get_pending(self.data, "abc"))
        log.clear_pending(self.data, "abc")

    def test_cleanup_removes_log_and_pending(self):
        log.append(self.data, "abc", {"event": "compact"})
        log.set_pending(self.data, "abc", 0)
        log.cleanup(self.data, "abc")
        self.assertFalse(os.path.exists(log.log_path(self.data, "abc")))
        self.assertFalse(os.path.exists(log.pending_path(self.data, "abc")))
        log.cleanup(self.data, "abc")

    def test_prune_removes_only_old_files(self):
        for name in ("old", "new"):
            log.append(self.data, name, {"event": "compact"})
            log.set_pending(self.data, name, 0)
        week = 7 * 24 * 3600
        for path in (log.log_path(self.data, "old"), log.pending_path(self.data, "old")):
            stamp = os.stat(path).st_mtime - week - 60
            os.utime(path, (stamp, stamp))
        log.prune(self.data)
        self.assertEqual(os.listdir(os.path.join(self.data, "sessions")), ["new.jsonl"])
        self.assertEqual(os.listdir(os.path.join(self.data, "pending")), ["new"])

    def test_prune_without_directories(self):
        log.prune(os.path.join(self.data, "nothing"))

    def test_valid_id(self):
        self.assertTrue(log.valid_id("22222222-2222-4222-8222-222222222222"))
        for bad in ("", "../x", "a/b", "a.b", None, 7, "x" * 129):
            self.assertFalse(log.valid_id(bad))


if __name__ == "__main__":
    unittest.main()
