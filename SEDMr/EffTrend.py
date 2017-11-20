"""Plot efficiency trend for SEDM

"""
import glob
import os
import csv
from itertools import izip

import pylab as pl
import numpy as np
from astropy.time import Time

sdir = '/scr2/sedmdrp/redux'
fspec = os.path.join(sdir, '20??????')
dlist = sorted([d for d in glob.glob(fspec) if os.path.isdir(d)])[1:]

jd0 = 2457000.0
jd = []
pjd = []
ef1 = []
ef2 = []
ef3 = []
ef4 = []
ef5 = []
efs = []
for d in dlist:
    print(d)
    ddate = d.split('/')[-1]
    dtime = Time(ddate[0:4]+'-'+ddate[4:6]+'-'+ddate[6:])

    fspec = os.path.join(d, 'sp_STD*.npy')
    slist = glob.glob(fspec)

    for s in slist:
        ss = np.load(s)[0]
        if 'efficiency' not in ss:
            continue

        ef = ss['efficiency']*100.  # type: np.ndarray
        wl = ss['nm']

        # Check each 100 nm bin

        # 400 - 500 nm
        r1 = (wl > 400) * (wl < 500)
        if len(r1) < 1:
            continue
        e1 = np.nanmean(ef[r1])
        if e1 > 100 or e1 < 0:
            continue

        # 500 - 600 nm
        r2 = (wl > 500) * (wl < 600)
        if len(r2) < 1:
            continue
        e2 = np.nanmean(ef[r2])
        if e2 > 100 or e2 < 0:
            continue

        # 600 - 700 nm
        r3 = (wl > 600) * (wl < 700)
        if len(r3) < 1:
            continue
        e3 = np.nanmean(ef[r3])
        if e3 > 100 or e3 < 0:
            continue

        # 700 - 800 nm
        r4 = (wl > 700) * (wl < 800)
        if len(r4) < 1:
            continue
        e4 = np.nanmean(ef[r4])
        if e4 > 100 or e4 < 0:
            continue

        # 800 - 900 nm
        r5 = (wl > 800) * (wl < 900)
        if len(r5) < 1:
            continue
        e5 = np.nanmean(ef[r5])
        if e5 > 100 or e5 < 0:
            continue

        # Fill efficiency vectors
        ef1.append(e1)
        ef2.append(e2)
        ef3.append(e3)
        ef4.append(e4)
        ef5.append(e5)
        efs.append(s)

        jd.append(dtime.jd)
        pjd.append(dtime.jd - jd0)

pl.plot(pjd, ef1, '^', linestyle='None', markersize=2.0, label='400-500 nm')
pl.plot(pjd, ef2, 'v', linestyle='None', markersize=2.0, label='500-600 nm')
pl.plot(pjd, ef3, 'x', linestyle='None', markersize=2.0, label='600-700 nm')
pl.plot(pjd, ef4, 'D', linestyle='None', markersize=2.0, label='700-800 nm')
pl.plot(pjd, ef5, 'o', linestyle='None', markersize=2.0, label='800-900 nm')
pl.xlabel('JD - 2457000')
pl.ylabel('Efficiency(%)')
pl.title('Efficiency Trend')
pl.legend(loc=2)
pl.grid(True)
pl.ylim(-1, 15)
ofil = os.path.join(sdir, 'SEDM_eff_trend.pdf')
pl.savefig(ofil)
with open('SEDM_eff_trend.txt', 'wb') as dfil:
    dat_writer = csv.writer(dfil, delimiter=" ", quoting=csv.QUOTE_MINIMAL)
    dat_writer.writerows(izip(jd, ef1, ef2, ef3, ef4, ef5, efs))


