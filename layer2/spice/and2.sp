* ============================================================
* 32nm LP - 2-INPUT CMOS AND GATE
* AND = NAND + INVERTER
* ============================================================

.include "32nm_LP.pm"

* ============================================================
* INPUT PARAMETERS
* ============================================================

.param VDD  = 0.9
.param TEMP = 27

.param WN   = 32n
.param WP   = 32n

* ============================================================
* LOGIC INPUTS
* ============================================================

.param A = 0
.param B = VDD

* A, B can be:
* 0       = Logic 0
* VDD     = Logic 1

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
* NAND2 STAGE
* ============================================================

* PMOS pull-up network - PARALLEL

MP1 NandOut A VDD VDD pmos W={WP} L=32n
MP2 NandOut B VDD VDD pmos W={WP} L=32n

* NMOS pull-down network - SERIES

MN1 NandOut A N1 0 nmos W={WN} L=32n
MN2 N1 B 0 0 nmos W={WN} L=32n

* ============================================================
* INVERTER STAGE
* ============================================================

* PMOS
MP3 Y NandOut VDD VDD pmos W={WP} L=32n

* NMOS
MN3 Y NandOut 0 0 nmos W={WN} L=32n

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
echo "2-INPUT CMOS AND"
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
print V(NandOut)
print V(N1)
print V(Y)

echo "========================================"
echo "SUPPLY CURRENT"
echo "========================================"

print i(VDD_SRC)

.endc

.end