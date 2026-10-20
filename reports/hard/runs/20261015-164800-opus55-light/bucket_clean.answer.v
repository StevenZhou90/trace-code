module dut(input clk, input rst, input req, output reg grant);
  reg [2:0] credits;
  reg [2:0] tick;
  wire refill = (tick == 3'd6);
  wire g = req && (credits != 3'd0);
  wire [3:0] nxt = {1'b0, credits} - {3'b0, g} + {3'b0, refill};
  always @(posedge clk) begin
    if (rst) begin
      credits <= 3'd3;
      tick    <= 3'd0;
      grant   <= 1'b0;
    end else begin
      tick    <= refill ? 3'd0 : tick + 3'd1;
      grant   <= g;
      credits <= (nxt > 4'd5) ? 3'd5 : nxt[2:0];
    end
  end
endmodule
