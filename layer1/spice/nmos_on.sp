* Example = sample_id 1 of nmos_on (process params in nmos_on_card.pm)
* NMOS_ON single-transistor netlist (32nm LP)
.include "nmos_on_card.pm"
* VDD = 0.900339753549 V (sets the VG/VB/VD/VS ranges)
Vd d 0 0.0453308754571
Vg g 0 0.900339753549
Vs s 0 0.763818541576
Vb b 0 0
M1 d g s b nmos W=1.44355566432e-07 L=3.2e-08
.options gmin=1e-18 abstol=1e-18 reltol=1e-6 vntol=1e-9
.temp 17.4446815112
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
