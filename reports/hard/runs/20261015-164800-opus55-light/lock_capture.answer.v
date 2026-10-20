// Keypad code lock (reverse-engineered from capture)
//   ch06 : clock (rising edge)
//   ch02 : synchronous reset, active low
//   ch08 : key valid (every cycle with ch08=1 is a key event)
//   {ch01,ch03,ch04,ch07} : key code
//   ch00 : unlock pulse (6 cycles after the correct 5-key sequence)
//   ch05 : lockout (20 cycles after 3 wrong keys; keys ignored meanwhile)
// Code sequence: 1101, 0100, 0111, 0100, 1010.
// A wrong key restarts matching (position 1 if it equals the first code key,
// else 0) and counts a strike. The match position survives lockout.
module dut (
    output wire ch00,
    input  wire ch01,
    input  wire ch02,
    input  wire ch03,
    input  wire ch04,
    output wire ch05,
    input  wire ch06,
    input  wire ch07,
    input  wire ch08
);
    localparam M_ENTRY = 2'd0, M_OPEN = 2'd1, M_LOCK = 2'd2;

    wire       clk   = ch06;
    wire       rst_n = ch02;
    wire       kv    = ch08;
    wire [3:0] key   = {ch01, ch03, ch04, ch07};

    reg [1:0] mode = M_ENTRY;
    reg [2:0] pos  = 3'd0;
    reg [1:0] wrong = 2'd0;
    reg [4:0] tmr  = 5'd0;

    wire [3:0] exp_key = (pos == 3'd0) ? 4'b1101 :
                         (pos == 3'd1) ? 4'b0100 :
                         (pos == 3'd2) ? 4'b0111 :
                         (pos == 3'd3) ? 4'b0100 : 4'b1010;

    always @(posedge clk) begin
        if (!rst_n) begin
            mode  <= M_ENTRY;
            pos   <= 3'd0;
            wrong <= 2'd0;
            tmr   <= 5'd0;
        end else begin
            case (mode)
                M_OPEN: begin
                    if (tmr == 5'd5) begin
                        mode  <= M_ENTRY;
                        tmr   <= 5'd0;
                        pos   <= 3'd0;
                        wrong <= 2'd0;
                    end else
                        tmr <= tmr + 5'd1;
                end
                M_LOCK: begin
                    if (tmr == 5'd19) begin
                        mode  <= M_ENTRY;
                        tmr   <= 5'd0;
                        wrong <= 2'd0;
                    end else
                        tmr <= tmr + 5'd1;
                end
                default: begin
                    if (kv) begin
                        if (key == exp_key) begin
                            if (pos == 3'd4) begin
                                mode  <= M_OPEN;
                                tmr   <= 5'd0;
                                pos   <= 3'd0;
                                wrong <= 2'd0;
                            end else
                                pos <= pos + 3'd1;
                        end else begin
                            pos <= (key == 4'b1101) ? 3'd1 : 3'd0;
                            if (wrong == 2'd2) begin
                                mode  <= M_LOCK;
                                tmr   <= 5'd0;
                                wrong <= 2'd0;
                            end else
                                wrong <= wrong + 2'd1;
                        end
                    end
                end
            endcase
        end
    end

    assign ch00 = (mode == M_OPEN);
    assign ch05 = (mode == M_LOCK);
endmodule
