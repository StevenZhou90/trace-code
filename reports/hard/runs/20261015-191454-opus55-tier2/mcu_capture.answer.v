// Reverse-engineered 8-bit accumulator machine with a 16-word program memory.
//
//   clock      : ch09 (rising edge)
//   reset      : ch26 (synchronous, active high) - clears everything incl. memory
//   load       : ch11 - while halted, mem[addr] <= low byte of the data bus
//   start/run  : ch16 - while halted, start at pc 0 with acc = 0
//   addr[3:0]  : {ch29, ch24, ch05, ch12}
//   instr[7:0] : {ch22, ch20, ch14, ch02, ch23, ch19, ch30, ch03}  = {op[2:0], x[4:0]}
//   in port    : {ch15, ch10, ch07, ch06, ch17, ch21, ch33, ch01}
//   out[7:0]   : {ch18, ch13, ch04, ch27, ch28, ch32, ch00, ch08}
//   strobe     : ch25 (one cycle after OUT)
//   running    : ch31
//
// op: 0 LDI  acc <= zext(x)
//     1 ADDI acc <= acc + sext(x)
//     2 LDM  acc <= mem[x[3:0]]
//     3 IN   acc <= in port
//     4 OUT  out <= acc, strobe
//     5 JNZ  if (acc != 0) pc <= x[3:0] (+1 dead cycle)
//     6 XORM acc <= acc ^ mem[x[3:0]]
//     7 HALT
module dut(
  output ch00, input ch01, input ch02, input ch03, output ch04, input ch05,
  input ch06, input ch07, output ch08, input ch09, input ch10, input ch11,
  input ch12, output ch13, input ch14, input ch15, input ch16, input ch17,
  output ch18, input ch19, input ch20, input ch21, input ch22, input ch23,
  input ch24, output ch25, input ch26, output ch27, output ch28, input ch29,
  input ch30, output ch31, output ch32, input ch33
);
  wire clk = ch09;
  wire rst = ch26;
  wire ld  = ch11;
  wire go  = ch16;

  wire [3:0] addr  = {ch29, ch24, ch05, ch12};
  wire [7:0] wdata = {ch22, ch20, ch14, ch02, ch23, ch19, ch30, ch03};
  wire [7:0] port  = {ch15, ch10, ch07, ch06, ch17, ch21, ch33, ch01};

  reg [7:0] mem [0:15];
  reg [3:0] pc;
  reg [7:0] acc;
  reg [7:0] outr;
  reg       strobe;
  reg       running;
  reg       bubble;

  wire [7:0] ir = mem[pc];
  wire [2:0] op = ir[7:5];
  wire [4:0] x  = ir[4:0];
  wire [7:0] m  = mem[x[3:0]];

  integer i;
  always @(posedge clk) begin
    if (rst) begin
      pc      <= 4'd0;
      acc     <= 8'd0;
      outr    <= 8'd0;
      strobe  <= 1'b0;
      running <= 1'b0;
      bubble  <= 1'b0;
      for (i = 0; i < 16; i = i + 1) mem[i] <= 8'd0;
    end else begin
      strobe <= 1'b0;
      if (!running) begin
        if (ld) mem[addr] <= wdata;
        if (go) begin
          running <= 1'b1;
          pc      <= 4'd0;
          acc     <= 8'd0;
          bubble  <= 1'b0;
        end
      end else if (bubble) begin
        bubble <= 1'b0;
      end else begin
        pc <= pc + 4'd1;
        case (op)
          3'd0: acc <= {3'b000, x};
          3'd1: acc <= acc + {{3{x[4]}}, x};
          3'd2: acc <= m;
          3'd3: acc <= port;
          3'd4: begin outr <= acc; strobe <= 1'b1; end
          3'd5: if (acc != 8'd0) begin pc <= x[3:0]; bubble <= 1'b1; end
          3'd6: acc <= acc ^ m;
          3'd7: running <= 1'b0;
        endcase
      end
    end
  end

  assign {ch18, ch13, ch04, ch27, ch28, ch32, ch00, ch08} = outr;
  assign ch25 = strobe;
  assign ch31 = running;
endmodule
