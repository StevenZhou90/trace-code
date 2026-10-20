module dut (
    input  wire       clk,
    input  wire       rst,
    input  wire [7:0] instr,
    input  wire       valid,
    output reg  [7:0] out,
    output reg        out_valid,
    output reg        z
);
    reg [7:0] r [0:3];

    wire [3:0] op = instr[7:4];
    wire [1:0] rd = instr[3:2];
    wire [1:0] rs = instr[1:0];
    wire [7:0] a  = r[rd];
    wire [7:0] b  = r[rs];

    reg [7:0] res;
    reg       wr;
    reg       setz;

    always @(*) begin
        res  = 8'd0;
        wr   = 1'b0;
        setz = 1'b0;
        case (op)
            4'h1: begin res = b;                    wr = 1'b1;              end
            4'h2: begin res = a + b;                wr = 1'b1; setz = 1'b1; end
            4'h3: begin res = a - b;                wr = 1'b1; setz = 1'b1; end
            4'h4: begin res = a & b;                wr = 1'b1; setz = 1'b1; end
            4'h5: begin res = a ^ b;                wr = 1'b1; setz = 1'b1; end
            4'h6: begin res = a << ({1'b0, rs} + 3'd1); wr = 1'b1; setz = 1'b1; end
            4'hc: begin res = a + 8'd1;             wr = 1'b1; setz = 1'b1; end
            4'hd: begin res = a - 8'd1;             wr = 1'b1; setz = 1'b1; end
            4'he: begin res = a - b;                           setz = 1'b1; end
            4'hf: begin res = ~a;                   wr = 1'b1; setz = 1'b1; end
            default: ;
        endcase
    end

    always @(posedge clk) begin
        if (rst) begin
            r[0] <= 8'd0; r[1] <= 8'd0; r[2] <= 8'd0; r[3] <= 8'd0;
            out <= 8'd0;
            out_valid <= 1'b0;
            z <= 1'b0;
        end else begin
            out_valid <= 1'b0;
            if (valid) begin
                if (instr[7:6] == 2'b10) begin
                    r[instr[5:4]] <= {r[instr[5:4]][3:0], instr[3:0]};
                end else if (op == 4'h7) begin
                    out <= b;
                    out_valid <= 1'b1;
                end else begin
                    if (wr)   r[rd] <= res;
                    if (setz) z <= (res == 8'd0);
                end
            end
        end
    end
endmodule
