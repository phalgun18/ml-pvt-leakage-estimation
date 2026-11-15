* INV inputs=0 corner=1
.include "inv_card.pm"
Vdd_src vdd 0 0.899944079315
Vss vss 0 0
Va a 0 0
mp y a vdd vdd pmos W=1.0114670026e-07 L=3.2e-08
mn y a vss vss nmos W=1.02810110254e-07 L=3.2e-08
.options gmin=1e-18 abstol=1e-18 reltol=1e-6 vntol=1e-9
.options itl1=1000 itl6=1000 pivrel=0.5
.temp 85.6367547063
.nodeset v(y)=0.899944079315
.control
set numdgt=15
op
let i_vdd = -i(Vdd_src)
let i_gnd = i(Vss)
let i_in_a = -i(Va)
let v_y = v(y)
let d_mp_id = @mp[id]
let d_mp_igcs = @mp[igcs]
let d_mp_igcd = @mp[igcd]
let d_mp_igb = @mp[igb]
let d_mp_isub = @mp[isub]
let d_mp_ibd = @mp[ibd]
let d_mp_ibs = @mp[ibs]
let d_mn_id = @mn[id]
let d_mn_igcs = @mn[igcs]
let d_mn_igcd = @mn[igcd]
let d_mn_igb = @mn[igb]
let d_mn_isub = @mn[isub]
let d_mn_ibd = @mn[ibd]
let d_mn_ibs = @mn[ibs]
print i_vdd
print i_gnd
print i_in_a
print v_y
print d_mp_id
print d_mp_igcs
print d_mp_igcd
print d_mp_igb
print d_mp_isub
print d_mp_ibd
print d_mp_ibs
print d_mn_id
print d_mn_igcs
print d_mn_igcd
print d_mn_igb
print d_mn_isub
print d_mn_ibd
print d_mn_ibs
.endc
.end
