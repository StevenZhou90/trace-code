// 3-bit Gray-code counter, non-ANSI port style.
module gray3 (clk, rst, en, g);
    parameter W = 3;
    input clk;
    input rst;
    input en;
    output [W-1:0] g;
    reg [W-1:0] bin;
    always @(posedge clk) begin
        if (rst)
            bin <= 0;
        else if (en)
            bin <= bin + 1'b1;
    end
    assign g = bin ^ (bin >> 1);
endmodule
