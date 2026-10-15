// Rejected: inout port.
module bidir (
    input  wire oe,
    input  wire a,
    inout  wire pad
);
    assign pad = oe ? a : 1'bz;
endmodule
