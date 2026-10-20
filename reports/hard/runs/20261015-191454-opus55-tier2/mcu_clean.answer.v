module dut (
    input  wire       clk,
    input  wire       rst,
    input  wire       we,
    input  wire [3:0] waddr,
    input  wire [7:0] wdata,
    input  wire       start,
    input  wire [7:0] in_data,
    output reg  [7:0] out,
    output reg        out_valid,
    output reg        busy
);
    // 16 x 8 program/data memory. Instruction = op[7:5], imm5[4:0] / addr[3:0]
    //   000 LDI  acc = imm5 (zero-extended)
    //   001 ADDI acc += sign-extended imm5
    //   010 LD   acc = mem[addr]
    //   011 IN   acc = in_data
    //   100 OUT  out = acc, out_valid pulse
    //   101 JNZ  if (acc != 0) pc = addr (taken jump costs one extra cycle)
    //   110 XOR  acc ^= mem[addr]
    //   111 HALT
    reg [7:0] mem [0:15];
    reg [7:0] acc;
    reg [3:0] pc;
    reg       bub;
    integer   i;

    wire [7:0] ins  = mem[pc];
    wire [2:0] op   = ins[7:5];
    wire [3:0] a    = ins[3:0];
    wire [7:0] simm = {{3{ins[4]}}, ins[4:0]};

    always @(posedge clk) begin
        if (rst) begin
            acc       <= 8'd0;
            pc        <= 4'd0;
            bub       <= 1'b0;
            busy      <= 1'b0;
            out       <= 8'd0;
            out_valid <= 1'b0;
            for (i = 0; i < 16; i = i + 1) mem[i] <= 8'd0;
        end else begin
            out_valid <= 1'b0;
            if (!busy) begin
                if (we) mem[waddr] <= wdata;
                if (start) begin
                    busy <= 1'b1;
                    pc   <= 4'd0;
                    bub  <= 1'b0;
                    acc  <= 8'd0;
                end
            end else if (bub) begin
                bub <= 1'b0;
            end else begin
                pc <= pc + 4'd1;
                case (op)
                    3'd0: acc <= {3'b000, ins[4:0]};
                    3'd1: acc <= acc + simm;
                    3'd2: acc <= mem[a];
                    3'd3: acc <= in_data;
                    3'd4: begin out <= acc; out_valid <= 1'b1; end
                    3'd5: if (acc != 8'd0) begin pc <= a; bub <= 1'b1; end
                    3'd6: acc <= acc ^ mem[a];
                    3'd7: busy <= 1'b0;
                endcase
            end
        end
    end
endmodule
