// Deliberately broken candidate for task tef5d471775 (seed 0): loses the incoming word when a push
// and a pop happen in the same cycle. Expected status: fail.
module dut (
    input  wire        clk,
    input  wire        rst,
    input  wire        in_valid,
    input  wire [7:0]  in_data,
    input  wire        out_ready,
    output wire        in_ready,
    output wire        out_valid,
    output wire [7:0]  out_data
);
    // Two-entry queue: mem0 is always the oldest word, mem1 the next one.
    reg [7:0] mem0, mem1;
    reg [1:0] count;
    wire push = in_valid && in_ready;   // a word enters at this rising edge
    wire pop  = out_valid && out_ready; // the oldest word leaves at this rising edge
    assign in_ready  = (count != 2'd2);
    assign out_valid = (count != 2'd0);
    assign out_data  = mem0;
    always @(posedge clk) begin
        if (rst)
            count <= 2'd0;
        else begin
            case ({push, pop})
                2'b10: begin
                    if (count == 2'd0) mem0 <= in_data; else mem1 <= in_data;
                    count <= count + 2'd1;
                end
                2'b01: begin
                    mem0 <= mem1;
                    count <= count - 2'd1;
                end
                2'b11: count <= 2'd0;  // (bug) the incoming word is lost  // only possible with count 1
                default: ;
            endcase
        end
    end
endmodule
