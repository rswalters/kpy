
import numpy as np
from scipy.interpolate import interp1d

# Palomar Extinction Data from Hayes & Latham 1975
# (Wavelength in Angstroms, Magnitudes per airmass)
palextinct = [
	(3200, 1.058),
	(3250, 0.911),
	(3300, 0.826),
	(3350, 0.757),
	(3390, 0.719),
	(3448, 0.663),
	(3509, 0.617),
	(3571, 0.575),
	(3636, 0.537),
	(3704, 0.500),
	(3862, 0.428),
	(4036, 0.364),
	(4167, 0.325),
	(4255, 0.302),
	(4464, 0.256),
	(4566, 0.238),
	(4785, 0.206),
	(5000, 0.183),
	(5263, 0.164),
	(5556, 0.151),
	(5840, 0.140),
	(6055, 0.133),
	(6435, 0.104),
	(6790, 0.084),
	(7100, 0.071),
	(7550, 0.061),
	(7780, 0.055),
	(8090, 0.051),
	(8370, 0.048),
	(8708, 0.044),
	(9832, 0.036),
	(10255, 0.034),
	(10610, 0.032),
	(10795, 0.032),
	(10870, 0.031)
]

palextinct = np.array(palextinct)
ext = interp1d(palextinct[:, 0], palextinct[:,1], kind='cubic', bounds_error=False)


