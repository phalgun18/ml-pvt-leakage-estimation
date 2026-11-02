* ============================================================
* 32nm LP - 2-INPUT CMOS NOR GATE
* ============================================================

.include "32nm_LP.pm"

* ============================================================
* INPUT PARAMETERS
* ============================================================

.param VDD  = 0.9
* VDD  : Supply voltage
*        Range: 0.81 V to 0.99 V

.param TEMP = 27
* TEMP : Temperature
*        Range: -40 C to 125 C

.param WN   = 32n
* WN   : NMOS width
*        Range: 1x Lmin to 8x Lmin

.param WP   = 32n
* WP   : PMOS width
*        Range: 1x Lmin to 8x Lmin

* ============================================================
* LOGIC INPUTS
* ============================================================

.param A = VDD
* A : Logic input
*     Allowed values: 0 or VDD

.param B = 0
* B : Logic input
*     Allowed values: 0 or VDD

* ============================================================
* POWER SUPPLY
* ============================================================

VDD_SRC VDD 0 {VDD}

* ============================================================
* INPUT SOURCES
* ============================================================

VA A 0 {A}
VB B 0 {B}

* ============================================================
* 2-INPUT CMOS NOR
* ============================================================

* ------------------------------------------------------------
* PMOS PULL-UP NETWORK
* PMOS transistors are in SERIES
* ------------------------------------------------------------

* PMOS controlled by A
MP1 Y A N2 VDD pmos W={WP} L=32n

* PMOS controlled by B
MP2 N2 B VDD VDD pmos W={WP} L=32n


* ------------------------------------------------------------
* NMOS PULL-DOWN NETWORK
* NMOS transistors are in PARALLEL
* ------------------------------------------------------------

* NMOS controlled by A
MN1 Y A 0 0 nmos W={WN} L=32n

* NMOS controlled by B
MN2 Y B 0 0 nmos W={WN} L=32n

* ============================================================
* SIMULATION OPTIONS
* ============================================================

.options gmin=1e-18
.options abstol=1e-18
.options reltol=1e-6
.options vntol=1e-9

.temp {TEMP}

* ============================================================
* DC OPERATING POINT
* ============================================================

.op

.control

op

echo "========================================"
echo "2-INPUT CMOS NOR"
echo "========================================"

echo "INPUTS"
print A
print B

echo "OUTPUT"
print V(Y)

echo "========================================"
echo "NODE VOLTAGES"
echo "========================================"

print V(VDD)
print V(A)
print V(B)
print V(Y)
print V(N2)

echo "========================================"
echo "SUPPLY CURRENT"
echo "========================================"

print i(VDD_SRC)

.endc

.end