// Reverse-engineered 8-bit command processor.
//   clock  : ch19 (rising edge)
//   reset  : ch11 (synchronous, active high)
//   valid  : ch17 (command accepted only when 1)
//   command byte bits: ch01 ch03 ch06 ch08 ch10 ch12 ch13 ch15
//   outputs: data[7:0] = {ch14,ch00,ch02,ch07,ch04,ch16,ch05,ch18}
//            ack = ch20 (one cycle after an OUT command), zero flag = ch09
module dut (
    output ch00,
    input  ch01,
    output ch02,
    input  ch03,
    output ch04,
    output ch05,
    input  ch06,
    output ch07,
    input  ch08,
    output ch09,
    input  ch10,
    input  ch11,
    input  ch12,
    input  ch13,
    output ch14,
    input  ch15,
    output ch16,
    input  ch17,
    output ch18,
    input  ch19,
    output ch20
);
    wire clk   = ch19;
    wire rst   = ch11;
    wire valid = ch17;

    reg [7:0] r0, r1, r2, r3;
    reg [7:0] dout;
    reg       ack;
    reg       zf;

    // decoded fields
    wire       is_ldn = (ch03 == 1'b0) && (ch06 == 1'b1);
    wire [1:0] ldn_rd = {ch01, ch13};
    wire [3:0] imm    = {ch12, ch15, ch10, ch08};
    wire [3:0] op     = {ch01, ch03, ch06, ch13};
    wire [1:0] rs     = {ch08, ch10};
    wire [1:0] rd     = {ch15, ch12};
    wire [1:0] shk    = {ch10, ch08};

    function [7:0] rsel;
        input [1:0] i;
        input [7:0] a, b, c, d;
        case (i)
            2'd0: rsel = a;
            2'd1: rsel = b;
            2'd2: rsel = c;
            default: rsel = d;
        endcase
    endfunction

    wire [7:0] vs  = rsel(rs, r0, r1, r2, r3);
    wire [7:0] vd  = rsel(rd, r0, r1, r2, r3);
    wire [7:0] vl  = rsel(ldn_rd, r0, r1, r2, r3);

    reg  [7:0] res;
    reg        wr;      // write result to rd
    reg        setz;    // update zero flag from zval
    reg  [7:0] zval;
    reg        isout;

    always @* begin
        res   = vd;
        wr    = 1'b0;
        setz  = 1'b0;
        zval  = 8'd0;
        isout = 1'b0;
        case (op)
            4'b0000: ;                                                      // NOP
            4'b0001: begin res = vd + vs;          wr = 1'b1; setz = 1'b1; zval = res; end // ADD
            4'b0100: begin res = vd & vs;          wr = 1'b1; setz = 1'b1; zval = res; end // AND
            4'b0101: begin res = vd << ({1'b0, shk} + 3'd1); wr = 1'b1; setz = 1'b1; zval = res; end // SHL
            4'b0110: begin res = vd + 8'd1;        wr = 1'b1; setz = 1'b1; zval = res; end // INC
            4'b0111: begin                                    setz = 1'b1; zval = vd - vs; end // CMP
            4'b1000: begin res = vs;               wr = 1'b1; end                  // MOV
            4'b1001: begin res = vd - vs;          wr = 1'b1; setz = 1'b1; zval = res; end // SUB
            4'b1100: begin res = vd ^ vs;          wr = 1'b1; setz = 1'b1; zval = res; end // XOR
            4'b1101: begin isout = 1'b1; end                                   // OUT
            4'b1110: begin res = vd - 8'd1;        wr = 1'b1; setz = 1'b1; zval = res; end // DEC
            4'b1111: begin res = ~vd;              wr = 1'b1; setz = 1'b1; zval = res; end // NOT
            default: ;
        endcase
    end

    always @(posedge clk) begin
        if (rst) begin
            r0 <= 8'd0; r1 <= 8'd0; r2 <= 8'd0; r3 <= 8'd0;
            dout <= 8'd0;
            ack  <= 1'b0;
            zf   <= 1'b0;
        end else begin
            ack <= 1'b0;
            if (valid) begin
                if (is_ldn) begin
                    case (ldn_rd)
                        2'd0: r0 <= {vl[3:0], imm};
                        2'd1: r1 <= {vl[3:0], imm};
                        2'd2: r2 <= {vl[3:0], imm};
                        default: r3 <= {vl[3:0], imm};
                    endcase
                end else begin
                    if (wr) begin
                        case (rd)
                            2'd0: r0 <= res;
                            2'd1: r1 <= res;
                            2'd2: r2 <= res;
                            default: r3 <= res;
                        endcase
                    end
                    if (setz) zf <= (zval == 8'd0);
                    if (isout) begin
                        dout <= vs;
                        ack  <= 1'b1;
                    end
                end
            end
        end
    end

    assign {ch14, ch00, ch02, ch07, ch04, ch16, ch05, ch18} = dout;
    assign ch20 = ack;
    assign ch09 = zf;
endmodule
