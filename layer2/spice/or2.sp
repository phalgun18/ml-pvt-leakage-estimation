* ============================================================
* 32nm LP - 2-INPUT CMOS OR GATE
* OR = NOR + INVERTER
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

.param A = vdd
.param B = 0

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
* NOR2 STAGE
* ============================================================

* PMOS pull-up network - SERIES

MP1 NorOut A N2 VDD pmos W={WP} L=32n
MP2 N2 B VDD VDD pmos W={WP} L=32n

* NMOS pull-down network - PARALLEL

MN1 NorOut A 0 0 nmos W={WN} L=32n
MN2 NorOut B 0 0 nmos W={WN} L=32n

* ============================================================
* INVERTER STAGE
* ============================================================

* PMOS
MP3 Y NorOut VDD VDD pmos W={WP} L=32n

* NMOS
MN3 Y NorOut 0 0 nmos W={WN} L=32n

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
echo "2-INPUT CMOS OR"
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
print V(NorOut)
print V(N2)
print V(Y)

echo "========================================"
echo "SUPPLY CURRENT"
echo "========================================"

print i(VDD_SRC)

.endc

.end