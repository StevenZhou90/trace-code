// Rejected: the clock is not named clk.
module other_clock (
    input  wire clock,
    input  wire d,
    output reg  q
);
    always @(posedge clock) q <= d;
endmodule
