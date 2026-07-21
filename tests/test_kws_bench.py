import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "kws_bench" / "kws_bench.py"
SPEC = importlib.util.spec_from_file_location("kws_bench", MODULE_PATH)
kws_bench = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = kws_bench
SPEC.loader.exec_module(kws_bench)


class KwsBenchTest(unittest.TestCase):
    def test_broad_grid_covers_safe_kws_parameters(self) -> None:
        grid = kws_bench.parameter_grid(kws_bench.default_params("broad"), "cpu")

        self.assertEqual(len(grid), 120)
        self.assertEqual({params.max_active_paths for params in grid}, {4, 8})
        self.assertEqual({params.num_trailing_blanks for params in grid}, {0, 1, 2})

    def test_record_defaults_to_emeet_and_has_no_style_option(self) -> None:
        parser = kws_bench.build_parser()

        defaults = parser.parse_args(["record"])
        overridden = parser.parse_args(["record", "--device", "Other Microphone"])

        self.assertEqual(defaults.device, "eMeet Adapter A300")
        self.assertEqual(overridden.device, "Other Microphone")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["record", "--styles", "natural"])

    def test_missed_wake_samples_excludes_hits_and_negative_samples(self) -> None:
        results = [
            kws_bench.SampleResult("wake-hit", "wake", "wake/hit.wav", True, 300.0, 4.0, 2000.0),
            kws_bench.SampleResult("wake-miss", "wake", "wake/miss.wav", False, None, 4.0, 2000.0),
            kws_bench.SampleResult("negative", "negative", "negative/talk.wav", False, None, 4.0, 2000.0),
        ]

        self.assertEqual(
            kws_bench.missed_wake_samples(results),
            [{"id": "wake-miss", "path": "wake/miss.wav"}],
        )

    def test_summary_and_ranking_prioritize_recall_then_latency(self) -> None:
        params = kws_bench.KwsParams(1.0, 0.02, 1, 8, 1, "cpu")
        faster = kws_bench.summarize(
            params,
            [
                kws_bench.SampleResult("a", "wake", "wake/a.wav", True, 300.0, 4.0, 2000.0),
                kws_bench.SampleResult("b", "wake", "wake/b.wav", True, 400.0, 4.0, 2000.0),
            ],
        )
        slower = dict(faster)
        slower["latency_ms_median"] = 600.0
        lower_recall = dict(faster)
        lower_recall["wake_recall"] = 0.5

        ranked = sorted([lower_recall, slower, faster], key=kws_bench.ranking_key)

        self.assertEqual(ranked[0], faster)
        self.assertEqual(ranked[-1], lower_recall)


if __name__ == "__main__":
    unittest.main()
