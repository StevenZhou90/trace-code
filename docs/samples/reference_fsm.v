module dut (
    input  wire        clk,
    input  wire        rst,
    input  wire        din,
    output wire        y
);
    // S<i>: the last i bits of din match the first i bits of 1011.
    localparam [2:0] S0 = 3'd0, S1 = 3'd1, S2 = 3'd2, S3 = 3'd3, S4 = 3'd4;
    reg [2:0] state, next;
    always @* begin
        case (state)
            S0: next = din ? S1 : S0;
            S1: next = din ? S1 : S2;
            S2: next = din ? S3 : S0;
            S3: next = din ? S4 : S2;
            S4: next = din ? S1 : S2;
            default: next = S0;
        endcase
    end
    always @(posedge clk) begin
        if (rst)
            state <= S0;
        else
            state <= next;
    end
    assign y = (state == S4);  // Moore: high the cycle after the last bit
endmodule
