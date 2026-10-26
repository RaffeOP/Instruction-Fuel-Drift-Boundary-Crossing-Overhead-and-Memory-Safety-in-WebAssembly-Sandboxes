"""Unit tests for the statistics, fitting, classification, and instrumentation code.

The tests run without the timing hardware. They check the functions whose outputs the paper
reports, so a change that moves a reported number fails here before it reaches the text.
Run with: python3 -m unittest discover -s tests
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import dynamic_opcode_counter as counter  # noqa: E402
import host_call_benchmarker as host  # noqa: E402
import loop_weighted_calibration as calibration  # noqa: E402
import opcode_profile  # noqa: E402
import parametric_stats_engine as stats_engine  # noqa: E402
import recycling_auditor  # noqa: E402

REPORTED_CONFORMANCE_LOWER_BOUND = 0.9954


class ClopperPearsonTest(unittest.TestCase):
    def test_all_successes_reports_paper_lower_bound(self):
        _, lower, upper = stats_engine.clopper_pearson_ci(800, 800)
        self.assertAlmostEqual(lower, REPORTED_CONFORMANCE_LOWER_BOUND, places=4)
        self.assertEqual(upper, 1.0)

    def test_no_successes_has_zero_lower_bound(self):
        point, lower, upper = stats_engine.clopper_pearson_ci(0, 10)
        self.assertEqual((point, lower), (0.0, 0.0))
        self.assertGreater(upper, 0.0)


class AffineFitTest(unittest.TestCase):
    def test_recovers_intercept_and_slope_from_noiseless_line(self):
        sizes = np.array([64.0, 1024.0, 16384.0, 262144.0])
        per_call = 5.0 + 2.0 * sizes
        fit = host.affine_fit(sizes, per_call)
        self.assertAlmostEqual(fit["alpha_ns"], 5.0, places=6)
        self.assertAlmostEqual(fit["beta_ns_per_byte"], 2.0, places=9)
        self.assertAlmostEqual(fit["r_squared"], 1.0, places=9)


class RecyclingFitTest(unittest.TestCase):
    def test_ols_slope_is_exact_on_linear_growth(self):
        x = np.arange(10, dtype=float)
        slope, lower, upper, p_value = recycling_auditor.ols_slope(x, 9.0 * x + 3.0)
        self.assertAlmostEqual(slope, 9.0, places=9)
        self.assertAlmostEqual(lower, 9.0, places=9)
        self.assertAlmostEqual(upper, 9.0, places=9)
        self.assertEqual(p_value, 0.0)


class ClassifierTest(unittest.TestCase):
    def test_known_mnemonics_map_to_their_classes(self):
        expected = {
            "i32.add": "int_arith",
            "f64.mul": "float_arith",
            "i64.lt_s": "compare",
            "i32.load": "memory_load",
            "f32.store": "memory_store",
            "br_if": "branch",
            "local.get": "local_global",
            "i64.const": "const",
        }
        for mnemonic, name in expected.items():
            self.assertEqual(opcode_profile.classify(mnemonic), name, mnemonic)

    def test_unknown_mnemonic_falls_into_other(self):
        self.assertEqual(opcode_profile.classify("nop"), "other")


class RidgeTest(unittest.TestCase):
    def test_weak_penalty_recovers_nonnegative_least_squares(self):
        design = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        target = np.array([2.0, 3.0, 5.0])
        weights = calibration.ridge_nonnegative(design, target, lam=1e-9)
        np.testing.assert_allclose(weights, [2.0, 3.0], atol=1e-4)


class InstrumentationTest(unittest.TestCase):
    WAT = """(module
  (func (export "run") (param i32) (result i64)
    local.get 0
    i64.extend_i32_u
  )
)
"""

    def test_instrumented_module_assembles_and_keeps_its_result(self):
        instrumented = counter.instrument(self.WAT)
        with tempfile.TemporaryDirectory() as scratch:
            source = Path(scratch) / "m.wat"
            target = Path(scratch) / "m.wasm"
            source.write_text(instrumented)
            subprocess.run([opcode_profile.WASM2WAT.replace("wasm2wat", "wat2wasm"), str(source), "-o", str(target)],
                           check=True, capture_output=True)
            self.assertTrue(target.exists())
        for name in ("local_global", "conversion"):
            self.assertIn(f"global.get $cnt_{name}", instrumented)
        for name, _ in opcode_profile.OPCODE_CLASSES:
            self.assertIn(f'(export "cnt_{name}"', instrumented)

    def test_each_instruction_gets_one_stack_neutral_increment(self):
        instrumented = counter.instrument(self.WAT)
        self.assertEqual(instrumented.count("global.set $cnt_"), 2)


if __name__ == "__main__":
    unittest.main()
