// Rejected: uses a file system task.
module logger (
    input  wire clk,
    input  wire d,
    output reg  q
);
    integer fd;
    initial fd = $fopen("log.txt", "w");
    always @(posedge clk) q <= d;
endmodule
