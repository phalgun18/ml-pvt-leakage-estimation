* AND2 inputs=01 corner=1
.include "and2_card.pm"
Vdd_src vdd 0 0.899944079315
Vss vss 0 0
Va a 0 0
Vb b 0 0.899944079315
mpa nand_out a vdd vdd pmos W=1.0114670026e-07 L=3.2e-08
mpb nand_out b vdd vdd pmos W=1.0114670026e-07 L=3.2e-08
mna nand_out a x vss nmos W=1.02810110254e-07 L=3.2e-08
mnb x b vss vss nmos W=1.02810110254e-07 L=3.2e-08
mpi y nand_out vdd vdd pmos W=1.0114670026e-07 L=3.2e-08
mni y nand_out vss vss nmos W=1.02810110254e-07 L=3.2e-08
.options gmin=1e-18 abstol=1e-18 reltol=1e-6 vntol=1e-9
.options itl1=1000 itl6=1000 pivrel=0.5
.temp 85.6367547063
.nodeset v(y)=0 v(nand_out)=0.899944079315
.control
set numdgt=15
op
let i_vdd = -i(Vdd_src)
let i_gnd = i(Vss)
let i_in_a = -i(Va)
let i_in_b = -i(Vb)
let v_y = v(y)
let v_x = v(x)
let v_nand_out = v(nand_out)
let d_mpa_id = @mpa[id]
let d_mpa_igcs = @mpa[igcs]
let d_mpa_igcd = @mpa[igcd]
let d_mpa_igb = @mpa[igb]
let d_mpa_isub = @mpa[isub]
let d_mpa_ibd = @mpa[ibd]
let d_mpa_ibs = @mpa[ibs]
let d_mpb_id = @mpb[id]
let d_mpb_igcs = @mpb[igcs]
let d_mpb_igcd = @mpb[igcd]
let d_mpb_igb = @mpb[igb]
let d_mpb_isub = @mpb[isub]
let d_mpb_ibd = @mpb[ibd]
let d_mpb_ibs = @mpb[ibs]
let d_mna_id = @mna[id]
let d_mna_igcs = @mna[igcs]
let d_mna_igcd = @mna[igcd]
let d_mna_igb = @mna[igb]
let d_mna_isub = @mna[isub]
let d_mna_ibd = @mna[ibd]
let d_mna_ibs = @mna[ibs]
let d_mnb_id = @mnb[id]
let d_mnb_igcs = @mnb[igcs]
let d_mnb_igcd = @mnb[igcd]
let d_mnb_igb = @mnb[igb]
let d_mnb_isub = @mnb[isub]
let d_mnb_ibd = @mnb[ibd]
let d_mnb_ibs = @mnb[ibs]
let d_mpi_id = @mpi[id]
let d_mpi_igcs = @mpi[igcs]
let d_mpi_igcd = @mpi[igcd]
let d_mpi_igb = @mpi[igb]
let d_mpi_isub = @mpi[isub]
let d_mpi_ibd = @mpi[ibd]
let d_mpi_ibs = @mpi[ibs]
let d_mni_id = @mni[id]
let d_mni_igcs = @mni[igcs]
let d_mni_igcd = @mni[igcd]
let d_mni_igb = @mni[igb]
let d_mni_isub = @mni[isub]
let d_mni_ibd = @mni[ibd]
let d_mni_ibs = @mni[ibs]
print i_vdd
print i_gnd
print i_in_a
print i_in_b
print v_y
print v_x
print v_nand_out
print d_mpa_id
print d_mpa_igcs
print d_mpa_igcd
print d_mpa_igb
print d_mpa_isub
print d_mpa_ibd
print d_mpa_ibs
print d_mpb_id
print d_mpb_igcs
print d_mpb_igcd
print d_mpb_igb
print d_mpb_isub
print d_mpb_ibd
print d_mpb_ibs
print d_mna_id
print d_mna_igcs
print d_mna_igcd
print d_mna_igb
print d_mna_isub
print d_mna_ibd
print d_mna_ibs
print d_mnb_id
print d_mnb_igcs
print d_mnb_igcd
print d_mnb_igb
print d_mnb_isub
print d_mnb_ibd
print d_mnb_ibs
print d_mpi_id
print d_mpi_igcs
print d_mpi_igcd
print d_mpi_igb
print d_mpi_isub
print d_mpi_ibd
print d_mpi_ibs
print d_mni_id
print d_mni_igcs
print d_mni_igcd
print d_mni_igb
print d_mni_isub
print d_mni_ibd
print d_mni_ibs
.endc
.end
