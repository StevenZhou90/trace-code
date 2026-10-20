// Bit-stuffed serial packet receiver.
// Line idles high; a 0 is the start bit. Then (LSB-first, with a 0 stuffed
// after every five consecutive 1s): length byte (1..12), <length> data bytes,
// CRC-8 byte (poly 0x07, init 0, over length+data). Six consecutive 1s inside
// a packet, a bad length, or a CRC mismatch -> error pulse.
module dut (
    output ch00, input ch01, input ch02, output ch03, output ch04,
    output ch05, output ch06, input ch07, output ch08, output ch09,
    output ch10, output ch11, output ch12, output ch13
);
    wire clk = ch01;
    wire din = ch02;
    wire rst = ch07;

    localparam IDLE = 2'd0, LEN = 2'd1, DATA = 2'd2, CHK = 2'd3;

    reg [1:0] st;
    reg [2:0] ones;
    reg [2:0] cnt;
    reg [7:0] sr;
    reg [3:0] len, n;
    reg [7:0] crc;
    reg [7:0] data;
    reg v, err, ok;

    wire [7:0] byte_w = {din, sr[7:1]};

    function [7:0] crc8;
        input [7:0] c;
        input [7:0] b;
        integer i;
        reg [7:0] x;
        begin
            x = c ^ b;
            for (i = 0; i < 8; i = i + 1)
                x = x[7] ? ((x << 1) ^ 8'h07) : (x << 1);
            crc8 = x;
        end
    endfunction

    wire [7:0] crc_n = crc8(crc, byte_w);

    always @(posedge clk) begin
        v <= 1'b0; err <= 1'b0; ok <= 1'b0;
        if (rst) begin
            st <= IDLE; ones <= 3'd0; cnt <= 3'd0; sr <= 8'd0;
            len <= 4'd0; n <= 4'd0; crc <= 8'd0; data <= 8'd0;
        end else if (st == IDLE) begin
            ones <= 3'd0;
            if (!din) begin
                st <= LEN; cnt <= 3'd0; sr <= 8'd0; crc <= 8'd0;
            end
        end else if (ones == 3'd5) begin
            ones <= 3'd0;
            if (din) begin
                err <= 1'b1;
                st <= IDLE;
            end
        end else begin
            ones <= din ? ones + 3'd1 : 3'd0;
            sr <= byte_w;
            cnt <= cnt + 3'd1;
            if (cnt == 3'd7) begin
                crc <= crc_n;
                case (st)
                    LEN: begin
                        if (byte_w == 8'd0 || byte_w > 8'd12) begin
                            err <= 1'b1;
                            st <= IDLE;
                        end else begin
                            len <= byte_w[3:0];
                            n <= 4'd0;
                            st <= DATA;
                        end
                    end
                    DATA: begin
                        v <= 1'b1;
                        data <= byte_w;
                        n <= n + 4'd1;
                        if (n + 4'd1 == len) st <= CHK;
                    end
                    default: begin
                        if (crc_n == 8'd0) ok <= 1'b1;
                        else err <= 1'b1;
                        st <= IDLE;
                    end
                endcase
            end
        end
    end

    assign ch11 = data[0];
    assign ch12 = data[1];
    assign ch05 = data[2];
    assign ch03 = data[3];
    assign ch00 = data[4];
    assign ch09 = data[5];
    assign ch13 = data[6];
    assign ch10 = data[7];
    assign ch04 = v;
    assign ch06 = err;
    assign ch08 = ok;
endmodule
