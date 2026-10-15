// Rejected: same style as parity8.v but listed without a license.
module parity8 (
    input  wire [7:0] data,
    output wire       odd
);
    assign odd = ~^data;
endmodule
