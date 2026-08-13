`timescale 1ns/1ps
// SPDX-License-Identifier: AGPL-3.0-or-later
module clock_sanity_tb;
    reg c1 = 0;
    reg c2 = 0;
    always #5 c1 = ~c1;
    always #3.5 c2 = ~c2;
    initial begin
        #100;
        $display("CLOCKS-ALIVE t=%0t", $time);
        $finish;
    end
endmodule
