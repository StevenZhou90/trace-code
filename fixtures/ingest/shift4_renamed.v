// Same behavior as shift4.v with different signal names. Normalized hashing does not catch this.
module shreg (
    input  wire       clk,
    input  wire       rst,
    input  wire       serial_in,
    output reg  [3:0] taps
);
    always @(posedge clk) begin
        if (rst)
            taps <= 4'd0;
        else
            taps <= {taps[2:0], serial_in};
    end
endmodule
