"""Text-level Verilog helpers: port parsing and the safety scan."""
import os
import unittest

from stc import verilog
from stc.families import FAMILIES
from tests.helpers import read

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "ingest")


class Ports(unittest.TestCase):
    def test_every_family_reference_header_parses_back_to_its_ports(self):
        for fam in FAMILIES.values():
            for p in fam.GROUPS:
                (name, body), = verilog.modules(fam.rtl(p))
                self.assertEqual(name, "dut")
                self.assertEqual(verilog.ports(body), fam.ports(p), (fam.NAME, p))

    def test_non_ansi_ports_with_parameter_width(self):
        (name, body), = verilog.modules(read(os.path.join(FIXTURES, "gray3.v")))
        self.assertEqual(name, "gray3")
        self.assertEqual([(p["name"], p["dir"], p["width"]) for p in verilog.ports(body)],
                         [("clk", "input", 1), ("rst", "input", 1), ("en", "input", 1), ("g", "output", 3)])

    def test_signed_and_unresolved_widths(self):
        (_, body), = verilog.modules("module m(input signed [7:0] a, input [K-1:0] b, output y); endmodule")
        a, b, y = verilog.ports(body)
        self.assertEqual((a["signed"], a["width"]), (True, 8))
        self.assertIsNone(b["width"])
        self.assertEqual(y["width"], 1)


class Safety(unittest.TestCase):
    def test_file_and_shell_tasks_are_rejected(self):
        self.assertEqual(verilog.unsafe_constructs('initial $system("ls"); initial $readmemh("f", m);'),
                         ["system_task:$readmemh", "system_task:$system"])

    def test_plain_display_and_comments_are_allowed(self):
        self.assertEqual(verilog.unsafe_constructs('// $fopen in a comment\ninitial $display("hi");'), [])


if __name__ == "__main__":
    unittest.main()
