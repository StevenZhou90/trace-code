// 4-bit serial-in shift register with synchronous reset.
module shift4 (
    input  wire       clk,
    input  wire       rst,
    input  wire       din,
    output reg  [3:0] q
);
    always @(posedge clk) begin
        if (rst)
            q <= 4'd0;
        else
            q <= {q[2:0], din};
    end
endmodule
