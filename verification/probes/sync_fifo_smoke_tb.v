// sync_fifo_smoke_tb.v — raw vvp smoke test for hypha_sync_fifo (no cocotb).
// SPDX-License-Identifier: AGPL-3.0-or-later
// Pushes 64 items on a 10ns domain, pops on a 7ns domain, checks order.
`timescale 1ns/1ps
`default_nettype none

module sync_fifo_smoke_tb;
    reg         push_clk = 0, pop_clk = 0;
    reg         push_rst_n = 0, pop_rst_n = 0;
    reg         push = 0, pop = 0;
    reg  [31:0] push_data = 0;
    wire [31:0] pop_data;
    wire        full, empty;

    hypha_sync_fifo #(.WIDTH(32), .DEPTH(4), .PTR_BITS(3)) dut (
        .push_clk(push_clk), .push_rst_n(push_rst_n),
        .push(push), .push_data(push_data), .full(full),
        .pop_clk(pop_clk), .pop_rst_n(pop_rst_n),
        .pop(pop), .pop_data(pop_data), .empty(empty)
    );

    always #5 push_clk = ~push_clk;
    always #3.5 pop_clk = ~pop_clk;

    integer sent = 0, got = 0;
    integer next_expected = 0;

    // producer
    always @(negedge push_clk) begin
        if (push_rst_n && sent < 64 && !full) begin
            push <= 1;
            push_data <= sent;
            sent <= sent + 1;
        end else begin
            push <= 0;
        end
    end

    // consumer
    always @(negedge pop_clk) begin
        if (pop_rst_n && !empty) begin
            pop <= 1;
            if (pop_data !== next_expected) begin
                $display("ORDER-ERROR got=%0d expected=%0d t=%0t", pop_data, next_expected, $time);
                $finish;
            end
            next_expected <= next_expected + 1;
            got <= got + 1;
        end else begin
            pop <= 0;
        end
    end

    initial begin
        $dumpfile("/tmp/cdc_smoke.vcd");
        $dumpvars(0, sync_fifo_smoke_tb);
        repeat (4) @(negedge push_clk);
        push_rst_n = 1;
        pop_rst_n = 1;
        #20000;
        $display("TIMEOUT sent=%0d got=%0d", sent, got);
        $finish;
    end

    always @(posedge push_clk) begin
        if (got == 64) begin
            $display("CDC-SMOKE-PASS sent=%0d got=%0d", sent, got);
            $finish;
        end
    end
endmodule

`default_nettype wire
