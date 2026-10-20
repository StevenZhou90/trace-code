module dut(
    input  wire       clk,
    input  wire       rst,
    input  wire       req,
    input  wire       flush,
    input  wire [7:0] addr,
    output reg        hit
);
    // 8 sets x 4 ways, 2-byte lines, tree pseudo-LRU, set index = {a[5],a[2],a[1]}
    reg [6:0] tags  [0:31];
    reg       valid [0:31];
    reg [2:0] plru  [0:7];   // [0]: 1=victim on right; [1]: left victim (w1 if 1); [2]: right victim (w3 if 1)

    wire [6:0] tag = addr[7:1];
    wire [2:0] set = {addr[5], addr[2], addr[1]};

    wire h0 = valid[{set,2'd0}] && tags[{set,2'd0}] == tag;
    wire h1 = valid[{set,2'd1}] && tags[{set,2'd1}] == tag;
    wire h2 = valid[{set,2'd2}] && tags[{set,2'd2}] == tag;
    wire h3 = valid[{set,2'd3}] && tags[{set,2'd3}] == tag;
    wire any_hit = h0 | h1 | h2 | h3;
    wire [1:0] hway = h0 ? 2'd0 : h1 ? 2'd1 : h2 ? 2'd2 : 2'd3;

    wire [2:0] pb = plru[set];
    wire [1:0] pvict = pb[0] ? {1'b1, pb[2]} : {1'b0, pb[1]};
    wire [1:0] fway = !valid[{set,2'd0}] ? 2'd0 :
                      !valid[{set,2'd1}] ? 2'd1 :
                      !valid[{set,2'd2}] ? 2'd2 :
                      !valid[{set,2'd3}] ? 2'd3 : pvict;
    wire [1:0] way = any_hit ? hway : fway;

    reg [2:0] nb;
    always @(*) begin
        nb = pb;
        nb[0] = ~way[1];
        if (way[1]) nb[2] = ~way[0];
        else        nb[1] = ~way[0];
    end

    integer i;
    always @(posedge clk) begin
        if (rst || flush) begin
            for (i = 0; i < 32; i = i + 1) begin
                valid[i] <= 1'b0;
                tags[i]  <= 7'd0;
            end
            for (i = 0; i < 8; i = i + 1)
                plru[i] <= 3'd0;
            hit <= 1'b0;
        end else begin
            hit <= req & any_hit;
            if (req) begin
                valid[{set,way}] <= 1'b1;
                tags[{set,way}]  <= tag;
                plru[set]        <= nb;
            end
        end
    end
endmodule
