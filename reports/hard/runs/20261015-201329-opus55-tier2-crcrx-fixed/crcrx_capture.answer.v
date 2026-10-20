// Serial frame receiver.
// Clock: ch01 (rising edge). Synchronous active-high reset: ch07. Serial data: ch02.
// Line idles high; a 0 bit starts a frame. Frame body is HDLC bit-stuffed
// (a 0 following five 1s is dropped; six 1s in a row aborts the frame).
// Body bytes are LSB first: length (1..15), <length> data bytes, CRC-8
// (poly 0x07, init 0x00) over length + data.
// Outputs:
//   data byte {ch10,ch13,ch09,ch00,ch03,ch05,ch12,ch11} (bit7..bit0), updated per data byte
//   ch04: data byte strobe, ch08: frame CRC ok, ch06: error (abort / bad length / bad CRC)
module dut (
    output ch00,
    input  ch01,
    input  ch02,
    output ch03,
    output ch04,
    output ch05,
    output ch06,
    input  ch07,
    output ch08,
    output ch09,
    output ch10,
    output ch11,
    output ch12,
    output ch13
);
    wire clk = ch01;
    wire din = ch02;
    wire rst = ch07;

    localparam S_IDLE = 2'd0, S_LEN = 2'd1, S_DATA = 2'd2, S_CHK = 2'd3;

    reg [1:0] state;
    reg [2:0] ones;      // consecutive 1s count (0..5)
    reg [2:0] bitcnt;
    reg [7:0] sh;        // bits shifted in LSB first
    reg [3:0] remain;    // data bytes still expected
    reg [7:0] crc;
    reg [7:0] dout;
    reg       strobe, ok, err;

    wire [7:0] byte_now = {din, sh[7:1]};

    function [7:0] crc8;
        input [7:0] c;
        input [7:0] d;
        integer i;
        reg [7:0] r;
        begin
            r = c ^ d;
            for (i = 0; i < 8; i = i + 1)
                r = r[7] ? ((r << 1) ^ 8'h07) : (r << 1);
            crc8 = r;
        end
    endfunction

    wire [7:0] crc_next = crc8(crc, byte_now);

    always @(posedge clk) begin
        if (rst) begin
            state  <= S_IDLE;
            ones   <= 3'd0;
            bitcnt <= 3'd0;
            sh     <= 8'd0;
            remain <= 4'd0;
            crc    <= 8'd0;
            dout   <= 8'd0;
            strobe <= 1'b0;
            ok     <= 1'b0;
            err    <= 1'b0;
        end else begin
            strobe <= 1'b0;
            ok     <= 1'b0;
            err    <= 1'b0;
            if (state == S_IDLE) begin
                if (!din) begin
                    state  <= S_LEN;
                    ones   <= 3'd0;
                    bitcnt <= 3'd0;
                    crc    <= 8'd0;
                end
            end else if (din && ones == 3'd5) begin
                // sixth consecutive 1: abort
                err   <= 1'b1;
                state <= S_IDLE;
                ones  <= 3'd0;
            end else if (!din && ones == 3'd5) begin
                // stuffed zero: drop
                ones <= 3'd0;
            end else begin
                ones   <= din ? ones + 3'd1 : 3'd0;
                sh     <= byte_now;
                bitcnt <= bitcnt + 3'd1;
                if (bitcnt == 3'd7) begin
                    crc <= crc_next;
                    case (state)
                        S_LEN: begin
                            if (byte_now == 8'd0 || byte_now > 8'd15) begin
                                err   <= 1'b1;
                                state <= S_IDLE;
                            end else begin
                                remain <= byte_now[3:0];
                                state  <= S_DATA;
                            end
                        end
                        S_DATA: begin
                            dout   <= byte_now;
                            strobe <= 1'b1;
                            remain <= remain - 4'd1;
                            if (remain == 4'd1) state <= S_CHK;
                        end
                        default: begin // S_CHK
                            if (crc == byte_now) ok <= 1'b1;
                            else err <= 1'b1;
                            state <= S_IDLE;
                        end
                    endcase
                end
            end
        end
    end

    assign ch11 = dout[0];
    assign ch12 = dout[1];
    assign ch05 = dout[2];
    assign ch03 = dout[3];
    assign ch00 = dout[4];
    assign ch09 = dout[5];
    assign ch13 = dout[6];
    assign ch10 = dout[7];
    assign ch04 = strobe;
    assign ch08 = ok;
    assign ch06 = err;
endmodule
