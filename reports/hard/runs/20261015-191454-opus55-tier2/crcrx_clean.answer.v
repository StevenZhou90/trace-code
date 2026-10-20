module dut (
    input  wire       clk,
    input  wire       rst,
    input  wire       rx,
    output reg  [7:0] data,
    output reg        data_valid,
    output reg        frame_ok,
    output reg        frame_bad
);
    localparam S_IDLE = 2'd0, S_LEN = 2'd1, S_DATA = 2'd2, S_CHK = 2'd3;

    reg [1:0] st;
    reg [2:0] ones;
    reg [7:0] sh;
    reg [2:0] nbit;
    reg [3:0] len;
    reg [3:0] cnt;
    reg [7:0] crc;

    wire [7:0] byte_in = {rx, sh[7:1]};

    function [7:0] crc8;
        input [7:0] c;
        input [7:0] b;
        integer i;
        reg [7:0] r;
        begin
            r = c ^ b;
            for (i = 0; i < 8; i = i + 1)
                r = r[7] ? ((r << 1) ^ 8'h07) : (r << 1);
            crc8 = r;
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            st <= S_IDLE; ones <= 3'd0; sh <= 8'd0; nbit <= 3'd0;
            len <= 4'd0; cnt <= 4'd0; crc <= 8'd0;
            data <= 8'd0; data_valid <= 1'b0; frame_ok <= 1'b0; frame_bad <= 1'b0;
        end else begin
            data_valid <= 1'b0;
            frame_ok   <= 1'b0;
            frame_bad  <= 1'b0;
            if (st == S_IDLE) begin
                if (!rx) begin
                    st <= S_LEN; ones <= 3'd0; nbit <= 3'd0; sh <= 8'd0;
                    crc <= 8'd0; cnt <= 4'd0;
                end
            end else if (ones == 3'd5) begin
                ones <= 3'd0;
                if (rx) begin
                    frame_bad <= 1'b1;
                    st <= S_IDLE;
                end
            end else begin
                ones <= rx ? ones + 3'd1 : 3'd0;
                sh   <= byte_in;
                nbit <= nbit + 3'd1;
                if (nbit == 3'd7) begin
                    case (st)
                        S_LEN: begin
                            if (byte_in == 8'd0 || byte_in > 8'd15) begin
                                frame_bad <= 1'b1;
                                st <= S_IDLE;
                            end else begin
                                len <= byte_in[3:0];
                                crc <= crc8(8'd0, byte_in);
                                st  <= S_DATA;
                            end
                        end
                        S_DATA: begin
                            data <= byte_in;
                            data_valid <= 1'b1;
                            crc <= crc8(crc, byte_in);
                            cnt <= cnt + 4'd1;
                            if (cnt + 4'd1 == len) st <= S_CHK;
                        end
                        default: begin // S_CHK
                            if (byte_in == crc) frame_ok <= 1'b1;
                            else frame_bad <= 1'b1;
                            st <= S_IDLE;
                        end
                    endcase
                end
            end
        end
    end
endmodule
