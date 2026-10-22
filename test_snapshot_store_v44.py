import tempfile
import unittest
from pathlib import Path
from snapshot_store import save_snapshot, load_snapshot

class SnapshotTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            save_snapshot('2026-10-22', [{'Home':'MIN','Away':'LAK'}], [{'Player':'Test'}], root=Path(d))
            result=load_snapshot('2026-10-22', root=Path(d))
            self.assertEqual(result['rankings'][0]['Player'],'Test')
            self.assertIsNone(load_snapshot('2026-10-23', root=Path(d)))
    def test_reject_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'2026-10-22.json';p.write_text('{broken')
            self.assertIsNone(load_snapshot('2026-10-22', root=Path(d)))
if __name__=='__main__': unittest.main()
