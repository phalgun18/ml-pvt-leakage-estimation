* ============================================================
* 32nm LP - CMOS INVERTER
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

.param A    = vdd
* A    : Logic input
*        Allowed: 0 or VDD

* ============================================================
* POWER SUPPLY
* ============================================================

VDD_SRC VDD 0 {VDD}

* ============================================================
* INPUT
* ============================================================

VA A 0 {A}

* ============================================================
* CMOS INVERTER
* ============================================================

* PMOS
* Drain = Y
* Gate  = A
* Source = VDD
* Body   = VDD

MP1 Y A VDD VDD pmos W={WP} L=32n

* NMOS
* Drain = Y
* Gate  = A
* Source = GND
* Body   = GND

MN1 Y A 0 0 nmos W={WN} L=32n

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

echo ===== NODE VOLTAGES =====
print v(vdd) v(a) v(y)

echo ===== PMOS DRAIN CURRENT =====
print @mp1[id]

echo ===== NMOS DRAIN CURRENT =====
print @mn1[id]

echo ===== SUPPLY CURRENT =====
print i(vdd_src)

.endc