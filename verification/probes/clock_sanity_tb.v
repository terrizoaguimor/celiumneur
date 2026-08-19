`timescale 1ns/1ps
// SPDX-License-Identifier: Apache-2.0
module clock_sanity_tb;
    reg c1 = 0;
    reg c2 = 0;
    integer c1_edges = 0;
    integer c2_edges = 0;
    always #5 c1 = ~c1;
    always #3.5 c2 = ~c2;
    always @(posedge c1) c1_edges = c1_edges + 1;
    always @(posedge c2) c2_edges = c2_edges + 1;
    initial begin
        #100;
        if (c1_edges != 10 || c2_edges != 14) begin
            $display("CLOCK-SANITY-FAIL c1=%0d c2=%0d", c1_edges, c2_edges);
            $finish_and_return(1);
        end
        $display("CLOCK-SANITY-PASS c1=%0d c2=%0d", c1_edges, c2_edges);
        $finish;
    end
endmodule
