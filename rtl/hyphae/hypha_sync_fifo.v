// hypha_sync_fifo.v — the ONLY authorized clock-domain-crossing cell in
// SPDX-License-Identifier: Apache-2.0
// CeliumNeUR (Invariant I3). No signal anywhere else in the RTL tree may
// cross a clock boundary; lint/forbidden-pattern checks enforce this.
//
// Classic dual-clock FIFO after Cummings (SNUG 2002, fifo1 style): memory
// written in the push domain, read in the pop domain, pointers exchanged as
// Gray codes through 2-flop synchronizers. Address and payload never travel
// outside this cell, which kills by construction the ODIN-class bug
// (AERIN_REQ synchronized but AERIN_ADDR consumed raw, controller.v:127-131).
//
// Flags are REGISTERED (fifo1 convention): full/empty are computed from the
// *next* pointer value but held in flip-flops. A combinational full creates
// a zero-delay evaluation loop (full → next-pointer → next-gray → full) that
// throttles event-driven simulators and is impossible to reason about in
// formal mode; the registered form is the canonical Cummings structure.

`default_nettype none

module hypha_sync_fifo #(
    parameter WIDTH = 32,
    parameter DEPTH = 4,                 // power of two
    parameter PTR_BITS = 3               // clog2(DEPTH) + 1 (extra wrap bit)
) (
    input  wire             push_clk,
    input  wire             push_rst_n,
    input  wire             push,
    input  wire [WIDTH-1:0] push_data,
    output reg              full,

    input  wire             pop_clk,
    input  wire             pop_rst_n,
    input  wire             pop,
    output wire [WIDTH-1:0] pop_data,
    output reg              empty
);

    reg  [WIDTH-1:0]    mem [0:DEPTH-1];
    reg  [PTR_BITS-1:0] wr_ptr_bin, wr_ptr_gray;
    reg  [PTR_BITS-1:0] rd_ptr_bin, rd_ptr_gray;
    // Synchronizer chains (domain-crossing happens strictly here).
    reg  [PTR_BITS-1:0] rd_gray_w1, rd_gray_w2;   // rd ptr -> push domain
    reg  [PTR_BITS-1:0] wr_gray_r1, wr_gray_r2;   // wr ptr -> pop domain

    // Next-state pointers advance only on a legal strobe; the strobes gate
    // on the registered flags, so nothing here loops combinationally.
    wire push_legal = push & ~full;
    wire pop_legal  = pop  & ~empty;

    wire [PTR_BITS-1:0] wr_bin_next  = wr_ptr_bin + push_legal;
    wire [PTR_BITS-1:0] wr_gray_next = (wr_bin_next >> 1) ^ wr_bin_next;
    wire [PTR_BITS-1:0] rd_bin_next  = rd_ptr_bin + pop_legal;
    wire [PTR_BITS-1:0] rd_gray_next = (rd_bin_next >> 1) ^ rd_bin_next;

    // Full when the *next* write pointer catches the synced read pointer
    // with both upper bits complemented (wrap sign); flag registered.
    wire full_next = (wr_gray_next == {~rd_gray_w2[PTR_BITS-1:PTR_BITS-2],
                                       rd_gray_w2[PTR_BITS-3:0]});
    wire empty_next = (rd_gray_next == wr_gray_r2);

    assign pop_data = mem[rd_ptr_bin[PTR_BITS-2:0]];

    always @(posedge push_clk or negedge push_rst_n) begin
        if (!push_rst_n) begin
            wr_ptr_bin  <= {PTR_BITS{1'b0}};
            wr_ptr_gray <= {PTR_BITS{1'b0}};
            rd_gray_w1  <= {PTR_BITS{1'b0}};
            rd_gray_w2  <= {PTR_BITS{1'b0}};
            full        <= 1'b0;
        end else begin
            if (push_legal) mem[wr_ptr_bin[PTR_BITS-2:0]] <= push_data;
            wr_ptr_bin  <= wr_bin_next;
            wr_ptr_gray <= wr_gray_next;
            rd_gray_w1  <= rd_ptr_gray;
            rd_gray_w2  <= rd_gray_w1;
            full        <= full_next;
        end
    end

    always @(posedge pop_clk or negedge pop_rst_n) begin
        if (!pop_rst_n) begin
            rd_ptr_bin  <= {PTR_BITS{1'b0}};
            rd_ptr_gray <= {PTR_BITS{1'b0}};
            wr_gray_r1  <= {PTR_BITS{1'b0}};
            wr_gray_r2  <= {PTR_BITS{1'b0}};
            empty       <= 1'b1;
        end else begin
            rd_ptr_bin  <= rd_bin_next;
            rd_ptr_gray <= rd_gray_next;
            wr_gray_r1  <= wr_ptr_gray;
            wr_gray_r2  <= wr_gray_r1;
            empty       <= empty_next;
        end
    end

endmodule

`default_nettype wire
