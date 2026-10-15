// Rejected: does not compile (missing semicolon).
module broken_syntax (
    input  wire a,
    output wire y
);
    assign y = ~a
endmodule
