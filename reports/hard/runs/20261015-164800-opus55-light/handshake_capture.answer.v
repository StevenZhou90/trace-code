// 2-entry shift-register FIFO (valid/ready handshake on both sides).
//   clock: ch19, sync active-high reset: ch10
//   input side : ch14 = in_valid, ch07 = in_ready (out)
//                data in  {ch15,ch17,ch00,ch02,ch03,ch09,ch16,ch21}
//   output side: ch12 = out_valid (out), ch06 = out_ready
//                data out {ch01,ch04,ch05,ch08,ch11,ch13,ch18,ch20}
// Data out is always slot0; on pop slot1 shifts into slot0. Data registers are not reset.
module dut (
    input  ch00, output ch01, input  ch02, input  ch03, output ch04, output ch05,
    input  ch06, output ch07, output ch08, input  ch09, input  ch10, output ch11,
    output ch12, output ch13, input  ch14, input  ch15, input  ch16, input  ch17,
    output ch18, input  ch19, output ch20, input  ch21
);
    wire       clk = ch19;
    wire       rst = ch10;
    wire       in_valid  = ch14;
    wire       out_ready = ch06;
    wire [7:0] din = {ch15, ch17, ch00, ch02, ch03, ch09, ch16, ch21};

    reg [1:0] cnt   = 2'd0;
    reg [7:0] slot0 = 8'd0;
    reg [7:0] slot1 = 8'd0;

    wire push = in_valid && (cnt != 2'd2);
    wire pop  = out_ready && (cnt != 2'd0);

    always @(posedge clk) begin
        if (rst) begin
            cnt <= 2'd0;
        end else begin
            if (pop) begin
                if (push && cnt == 2'd1) slot0 <= din;
                else                     slot0 <= slot1;
            end else if (push) begin
                if (cnt == 2'd0) slot0 <= din;
                else             slot1 <= din;
            end
            cnt <= cnt + {1'b0, push} - {1'b0, pop};
        end
    end

    assign ch07 = (cnt != 2'd2);
    assign ch12 = (cnt != 2'd0);
    assign {ch01, ch04, ch05, ch08, ch11, ch13, ch18, ch20} = slot0;
endmodule
