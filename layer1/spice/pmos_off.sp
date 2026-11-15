* Example = sample_id 1 of pmos_off (process params in pmos_off_card.pm)
* PMOS_OFF single-transistor netlist (32nm LP)
.include "pmos_off_card.pm"
* VDD = 0.874744288068 V (sets the VG/VB/VD/VS ranges)
Vd d 0 0.873124924987
Vg g 0 0.874744288068
Vs s 0 0.73135132601
Vb b 0 0.874744288068
M1 d g s b pmos W=2.18744776948e-07 L=3.2e-08
.options gmin=1e-18 abstol=1e-18 reltol=1e-6 vntol=1e-9
.temp 21.4604657204
.control
set numdgt=15
op
let id = -i(Vd)
let ig = -i(Vg)
let is = -i(Vs)
let ib = -i(Vb)
let x_id = @m1[id]
let x_isub = @m1[isub]
let x_igidl = @m1[igidl]
let x_igisl = @m1[igisl]
let x_igb = @m1[igb]
let x_igcs = @m1[igcs]
let x_igcd = @m1[igcd]
let x_ibd = @m1[ibd]
let x_ibs = @m1[ibs]
let x_vth = @m1[vth]
print id
print ig
print is
print ib
print x_id
print x_isub
print x_igidl
print x_igisl
print x_igb
print x_igcs
print x_igcd
print x_ibd
print x_ibs
print x_vth
.endc
.end
