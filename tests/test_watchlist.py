import unittest
from pathlib import Path

class WatchlistTests(unittest.TestCase):
    def test_watchlist_valid_and_unique(self):
        root=Path(__file__).resolve().parents[1]
        tickers=[s.strip() for s in (root/"watchlist.txt").read_text().splitlines()
                 if s.strip() and not s.lstrip().startswith("#")]
        self.assertGreaterEqual(len(tickers),1)
        self.assertLessEqual(len(tickers),40)
        self.assertEqual(len(tickers),len(set(tickers)))
        for symbol in tickers:
            self.assertRegex(symbol,r"^[A-Z][A-Z0-9.-]{0,9}$")

if __name__=="__main__":
    unittest.main()
