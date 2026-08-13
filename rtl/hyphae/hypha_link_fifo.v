// hypha_link_fifo.v — single-clock FIFO for Hyphae link buffering inside one
// SPDX-License-Identifier: AGPL-3.0-or-later
// router. First-word-fall-through: `dout` presents the head whenever ~empty,
// so the router arbitration sees the head combinationally in the same cycle.
//
// There is deliberately no drop path (Invariant I1): push when full is a
// protocol violation, prevented upstream by the credit loop (the transmitter
// never owns a credit it was not given). The `overflow` flag exists only as
// a formal/simulation witness that the guard itself never breaks.

`default_nettype none

module hypha_link_fifo #(
    parameter WIDTH = 32,
    parameter DEPTH = 4,               // power of two
    parameter ADDR_BITS = 2,           // clog2(DEPTH)
    parameter COUNT_BITS = 3           // clog2(DEPTH)+1
) (
    input  wire             clk,
    input  wire             rst_n,
    input  wire             push,
    input  wire [WIDTH-1:0] din,
    input  wire             pop,
    output wire [WIDTH-1:0] dout,
    output wire             empty,
    output wire             full,
    output wire             overflow   // witness only; must never assert
);

    localparam [COUNT_BITS-1:0] DEPTH_COUNT = DEPTH;

    reg  [WIDTH-1:0]      mem [0:DEPTH-1];
    reg  [ADDR_BITS-1:0]  rd_ptr;
    reg  [ADDR_BITS-1:0]  wr_ptr;
    reg  [COUNT_BITS-1:0] count;

    assign empty = (count == 0);
    assign full  = (count == DEPTH_COUNT);
    assign dout  = mem[rd_ptr];

    reg overflow_r;
    assign overflow = overflow_r;

    wire do_push = push & ~full;
    wire do_pop  = pop  & ~empty;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_ptr     <= {ADDR_BITS{1'b0}};
            wr_ptr     <= {ADDR_BITS{1'b0}};
            count      <= {COUNT_BITS{1'b0}};
            overflow_r <= 1'b0;
        end else begin
            if (push & full) overflow_r <= 1'b1;   // witness: guard broken
            if (do_push) wr_ptr <= wr_ptr + 1'b1;
            if (do_pop)  rd_ptr <= rd_ptr + 1'b1;
            if (do_push) mem[wr_ptr] <= din;
            case ({do_push, do_pop})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end

endmodule

`default_nettype wire
