// Rejected: a port wider than 32 bits.
module wide64 (
    input  wire [63:0] a,
    output wire [63:0] y
);
    assign y = ~a;
endmodule
