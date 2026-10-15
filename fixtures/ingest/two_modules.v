// Rejected: more than one module in a file.
module inv (input wire a, output wire y);
    assign y = ~a;
endmodule
module buf2 (input wire a, output wire y);
    wire t;
    inv u0 (.a(a), .y(t));
    inv u1 (.a(t), .y(y));
endmodule
