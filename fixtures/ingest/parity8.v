// Even parity of an 8-bit word (combinational).
module parity8 (
    input  wire [7:0] data,
    output wire       odd
);
    assign odd = ^data;
endmodule
