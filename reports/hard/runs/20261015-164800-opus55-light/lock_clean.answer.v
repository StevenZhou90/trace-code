module dut (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [3:0] key,
    input  wire       key_valid,
    output wire       unlocked,
    output wire       alarm
);
    reg [2:0] pos;
    reg [1:0] wrong;
    reg [4:0] atimer;
    reg [2:0] utimer;

    reg [3:0] exp_key;
    always @(*) begin
        case (pos)
            3'd0: exp_key = 4'd7;
            3'd1: exp_key = 4'd2;
            3'd2: exp_key = 4'd14;
            3'd3: exp_key = 4'd2;
            default: exp_key = 4'd9;
        endcase
    end

    assign unlocked = (utimer != 3'd0);
    assign alarm    = (atimer != 5'd0);

    always @(posedge clk) begin
        if (!rst_n) begin
            pos <= 3'd0; wrong <= 2'd0; atimer <= 5'd0; utimer <= 3'd0;
        end else if (atimer != 5'd0) begin
            atimer <= atimer - 5'd1;
        end else if (utimer != 3'd0) begin
            utimer <= utimer - 3'd1;
        end else if (key_valid) begin
            if (key == exp_key) begin
                if (pos == 3'd4) begin
                    pos <= 3'd0; wrong <= 2'd0; utimer <= 3'd6;
                end else
                    pos <= pos + 3'd1;
            end else begin
                pos <= (key == 4'd7) ? 3'd1 : 3'd0;
                if (wrong == 2'd2) begin
                    wrong <= 2'd0; atimer <= 5'd20;
                end else
                    wrong <= wrong + 2'd1;
            end
        end
    end
endmodule
