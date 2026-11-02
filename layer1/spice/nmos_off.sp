* ============================================================
* 32nm LP - NMOS OFF
* ============================================================

.include "32nm_LP.pm"

* ============================================================
* INPUT PARAMETERS
* ============================================================

.param VDD  = 0.9
* VDD  : nominal VDD +/-10%
*        Range: 0.81 V to 0.99 V

.param TEMP = 27
* TEMP : Temperature
*        Range: -40 C to 125 C

.param W    = 32n
* W    : Transistor width
*        Range: 1x Lmin to 8x Lmin

.param VD   = 0.9
* VD   : Drain voltage
*        Range: 0 to VDD

.param VS   = 0
* VS   : Source voltage
*        Range: 0 to VDD

.param VG   = 0
* VG   : Gate voltage
*        NMOS ON  = VDD
*        NMOS OFF = 0
*        PMOS ON  = 0
*        PMOS OFF = VDD

.param VB   = 0
* VB   : Body voltage
*        NMOS ON/OFF = 0
*        PMOS ON/OFF = VDD
* ============================================================
* VOLTAGE SOURCES
* ============================================================

Vd D 0 {VD}
Vg G 0 {VG}
Vs S 0 {VS}
Vb B 0 {VB}

* ============================================================
* NMOS
* ============================================================

M1 D G S B nmos W={W} L=32n

* ============================================================
* SIMULATION OPTIONS
* ============================================================

.options gmin=1e-18
.options abstol=1e-18
.options reltol=1e-6
.options vntol=1e-9

.temp {TEMP}

* ============================================================
* OPERATING POINT
* ============================================================

.op

.control
op

echo "========================================"
echo "NMOS OFF - TERMINAL CURRENTS"
echo "========================================"

let ID = -i(Vd)
let IG = -i(Vg)
let IS = -i(Vs)
let IB = -i(Vb)

print ID
print IG
print IS
print IB

.endc

.end