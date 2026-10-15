"""The simulation harness: statuses, timing rule, mismatch reports, bounded logs, untrusted input."""
import os
import tempfile
import time
import unittest

from stc import sim
from stc.families import counter
from stc.models import counter as counter_model

P = {"W": 4, "enable": True}
IFACE = {"module": "dut", "ports": counter.ports(P), "clock": "clk"}
REF = counter.rtl(P)
ROWS = [{"rst": 1, "en": 0}, {"rst": 0, "en": 1}, {"rst": 0, "en": 1}, {"rst": 0, "en": 0}, {"rst": 0, "en": 1}]


def with_line(code):
    end = REF.rindex("endmodule")
    return REF[:end] + code + "\n" + REF[end:]


class Harness(unittest.TestCase):
    def test_timing_rule_row_shows_state_before_the_edge(self):
        r = sim.simulate(IFACE, REF, ROWS)
        self.assertEqual(r["status"], "pass")
        # row 0: before any edge q is unknown; row 1: reset applied at edge 0; then +1, +1, hold.
        self.assertEqual([o[0] for o in r["outputs"]], ["x", 0, 1, 2, 2])

    def test_reference_passes_against_model(self):
        r = sim.simulate(IFACE, REF, ROWS, counter_model(P, ROWS))
        self.assertEqual((r["status"], r["failing_rows"]), ("pass", 0))

    def test_functional_fail_reports_inputs_expected_actual(self):
        r = sim.simulate(IFACE, counter.rtl(P, "reset_to_one"), ROWS, counter_model(P, ROWS))
        self.assertEqual(r["status"], "fail")
        m = r["mismatches"][0]
        self.assertEqual(m["cycle"], 1)
        self.assertEqual(m["inputs"], {"rst": 0, "en": 1})
        self.assertEqual((m["expected"], m["actual"], m["signals"]), ({"q": 0}, {"q": 1}, ["q"]))

    def test_compiling_is_not_passing(self):
        const = "module dut(input wire clk, input wire rst, input wire en, output wire [3:0] q);\n" \
                "  assign q = 4'd0;\nendmodule\n"
        self.assertEqual(sim.simulate(IFACE, const, ROWS, counter_model(P, ROWS))["status"], "fail")

    def test_unknown_outputs_never_match(self):
        no_reset = REF.replace("if (rst)", "if (1'b0)")
        r = sim.simulate(IFACE, no_reset, ROWS, counter_model(P, ROWS))
        self.assertEqual(r["status"], "fail")
        self.assertEqual(r["mismatches"][0]["actual"], {"q": "x"})

    def test_compile_error(self):
        r = sim.simulate(IFACE, REF.replace("endmodule", "endmodul"), ROWS, counter_model(P, ROWS))
        self.assertEqual((r["status"], r["stage"]), ("compile_error", "compile"))
        self.assertIn("syntax error", r["log"])

    def test_interface_error_wrong_width(self):
        r = sim.simulate(IFACE, REF.replace("[3:0]", "[4:0]"), ROWS)
        self.assertEqual(r["status"], "interface_error")
        self.assertIn("port q is output[5], expected output[4]", r["problems"])

    def test_interface_error_wrong_module_name(self):
        r = sim.simulate(IFACE, REF.replace("module dut", "module counter"), ROWS)
        self.assertEqual((r["status"], r["problems"]), ("interface_error", ["missing module dut"]))

    def test_sim_error(self):
        r = sim.simulate(IFACE, with_line('initial #13 $fatal(1, "bad");'), ROWS)
        self.assertEqual(r["status"], "sim_error")
        self.assertIn("bad", r["log"])

    def test_timeout_is_enforced(self):
        t0 = time.time()
        r = sim.simulate(IFACE, with_line("initial begin : spin integer i; i = 0; while (1) i = i + 1; end"),
                         ROWS, timeout=2)
        self.assertEqual((r["status"], r["stage"]), ("timeout", "simulate"))
        self.assertLess(time.time() - t0, 8)

    def test_untrusted_input_is_never_run(self):
        marker = os.path.join(tempfile.mkdtemp(), "ran")
        r = sim.simulate(IFACE, with_line('initial $system("touch %s");' % marker), ROWS)
        self.assertEqual((r["status"], r["problems"]), ("rejected", ["system_task:$system"]))
        self.assertFalse(os.path.exists(marker))
        for code, why in [('initial $fopen("x.txt");', "system_task:$fopen"), ('`include "a.v"', "include_directive")]:
            self.assertEqual(sim.simulate(IFACE, with_line(code), ROWS)["problems"], [why])

    def test_logs_are_bounded(self):
        noisy = with_line('always @(posedge clk) repeat (500) $display("%0s", "0123456789012345678901234567890123456789");')
        r = sim.simulate(IFACE, noisy, ROWS * 20, counter_model(P, ROWS * 20))
        self.assertEqual(r["status"], "pass")
        self.assertLessEqual(len(r["log"].encode()), sim.LOG_LIMIT)

    def test_testbench_drives_inputs_in_port_order(self):
        tb = sim.testbench(IFACE, 3)
        self.assertIn("{rst, en} = stim[k];", tb)
        self.assertEqual(sim.pack(IFACE, {"rst": 1, "en": 0}), "2")


if __name__ == "__main__":
    unittest.main()
