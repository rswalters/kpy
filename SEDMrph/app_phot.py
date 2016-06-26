# -*- coding: utf-8 -*-
"""
Created on Sat May 23 18:23:02 2015

@author: nadiablago
"""

import numpy as np
import matplotlib
matplotlib.use("Agg", warn=False)
from matplotlib import pylab as plt

try:
    from pyraf import iraf 
except:
    print "Not loading iraf"
import os, sys, math
import pyfits as pf
import zscale
import time
import fitsutils
import glob
import argparse
import coordinates_conversor as cc
import pywcs
import matplotlib.lines as mlines

ref_stars_file = "/Users/nadiablago/Documents/Projects/M101/cats/ref_stars_ps1.csv"
ref_stars_file_sdss = "/Users/nadiablago/Documents/Projects/M101/cats/ref_stars_sdss.csv"
ref_stars_file_2mass = "/Users/nadiablago/Documents/Projects/M101/cats/ref_stars_2mass.csv"
ref_stars_file_johnson = "/Users/nadiablago/Documents/Projects/M101/cats/ref_stars_johnson.csv"

import warnings

def fxn():
    warnings.warn("deprecated", DeprecationWarning)


def get_app_phot(coords, image, plot_only=False, store=True, wcsin="world", fwhm=2, plotdir="."):
    '''
    coords: files: 
    wcsin: can be "world", "logic"
    '''
    # Load packages; splot is in the onedspec package, which is in noao. 
    # The special keyword _doprint=0 turns off displaying the tasks 
    # when loading a package. 
    
    if (not plot_only):
        iraf.noao(_doprint=0)
        iraf.digiphot(_doprint=0)
        iraf.apphot(_doprint=0)
        iraf.unlearn("apphot")

    imdir = os.path.dirname(image)
    imname = os.path.basename(image)
    plotdir = os.path.join(imdir, "photometry")
    
    if not os.path.isdir(plotdir):
        os.makedirs(plotdir)
        
    out_name = os.path.join(plotdir, imname +  ".seq.mag")
    clean_name = os.path.join(plotdir, imname +  ".app.mag")

    
    # Read values from .ec file
    ecfile= image+".ec"
    filter_value=''.join(ecfile).split('.',1)[0]
    
    fwhm_value = fwhm
    
    if (fitsutils.has_par(image, 'FWHM')):
        fwhm_value = fitsutils.get_par(image, 'FWHM')
    airmass_value = fitsutils.get_par(image, 'AIRMASS')
    exptime = fitsutils.get_par(image, 'EXPTIME')
    gain = fitsutils.get_par(image, 'GAIN')

    try:      
        with open(''.join(ecfile),'r') as f:
            for line in f:
                if "airmass" in line:
                    airmass_value = line.split('=',1)[1]
                else:
                    airmass_value = 1
                if "FWHM" in line:
                    print line
                    fwhm_value =  line.split('FWHM=',1)[1]
                    fwhm_value = fwhm_value.rsplit("aperture")[0]
    except:
        pass
    
    print "FWHM", fwhm_value
    aperture_rad = math.ceil(float(fwhm_value)*3)      # Set aperture radius to three times the PSF radius
    sky_rad= math.ceil(float(fwhm_value)*4)
    
    print aperture_rad, sky_rad

    if (not plot_only):

        if os.path.isfile(out_name): os.remove(out_name)
        if os.path.isfile(clean_name): os.remove(clean_name)

        # Check if files in list, otherwise exit
        if not ecfile:
           print "No .ec files in directory, exiting"
           sys.exit()
        
        
   
   
        iraf.noao.digiphot.apphot.qphot(image = image,\
        cbox = 25. ,\
        annulus = sky_rad ,\
        dannulus = 10. ,\
        aperture = str(aperture_rad),\
        coords = coords ,\
        output = out_name ,\
        plotfile = "" ,\
        zmag = 0. ,\
        exposure = "exptime" ,\
        airmass = "airmass" ,\
        filter = "filters" ,\
        obstime = "DATE" ,\
        epadu = gain ,\
        interactive = "no" ,\
        radplots = "yes" ,\
        verbose = "no" ,\
        graphics = "stdgraph" ,\
        display = "stdimage" ,\
        icommands = "" ,\
        wcsin = wcsin,
        wcsout = "logical",
        gcommands = "") 
        
         
        #iraf.noao.digiphot.apphot.phot(image=image, cbox=5., annulus=12.4, dannulus=10., salgori = "centroid", aperture=9.3,wcsin="world",wcsout="tv", interac = "no", coords=coords, output=out_name)
        iraf.txdump(out_name, "id,image,xcenter,ycenter,xshift,yshift,fwhm,msky,stdev,mag,merr", "yes", Stdout=clean_name)
        
    
    ma = np.genfromtxt(clean_name, comments="#", dtype=[("id","<f4"),  ("image","|S20"), ("X","<f4"), ("Y","<f4"), ("Xshift","<f4"), ("Yshift","<f4"),("fwhm","<f4"), ("ph_mag","<f4"), ("stdev","<f4"), ("fit_mag","<f4"), ("fiterr","<f4")])
    if (ma.size > 0):    
        m = ma[~np.isnan(ma["fit_mag"])]
    else:
        print "Only one object found!"
        m = np.array([ma])
        
    hdulist = pf.open(image)
    prihdr = hdulist[0].header
    img = hdulist[0].data * 1.
    nx, ny = img.shape

    
    
    dimX = int(4)
    dimY = int(np.ceil(len(m)*1./4))
    outerrad = sky_rad+10
    cutrad = outerrad + 15
    
    plt.suptitle("FWHM="+str(fwhm_value))
    k = 0
    for i in np.arange(dimX):
        for j in np.arange(dimY):
            if ( k < len(m)):
                ax = plt.subplot2grid((dimX,dimY),(i, j))
                y1, y2, x1, x2 = m[k]["X"]-cutrad, m[k]["X"]+cutrad, m[k]["Y"]-cutrad, m[k]["Y"]+cutrad
                y1, y2, x1, x2 = int(y1), int(y2), int(x1), int(x2)
                try:
                    zmin, zmax = zscale.zscale(img[x1:x2,y1:y2], nsamples=1000, contrast=0.25)
                except:
                    sh= img[x1:x2,y1:y2].shape
                    if sh[0]>0 and sh[1]>0:
                        zmin = np.nanmin(img[x1:x2,y1:y2])
                        zmax = np.nanmax(img[x1:x2,y1:y2])
                        continue
                    else:
                        continue
                ax.imshow(img[x1:x2,y1:y2], aspect="equal", extent=(-cutrad, cutrad, -cutrad, cutrad), origin="lower", cmap=matplotlib.cm.gray_r, interpolation="none", vmin=zmin, vmax=zmax)
                c1 = plt.Circle( (0, 0), edgecolor="r", facecolor="none", radius=5.)
                c2 = plt.Circle( (0, 0), edgecolor="orange", facecolor="none", radius=sky_rad)
                c3 = plt.Circle( (0, 0), edgecolor="yellow", facecolor="none", radius=sky_rad+10)
                plt.gca().add_artist(c1)
                plt.gca().add_artist(c2)
                plt.gca().add_artist(c3)
                ax.set_xticks([])
                ax.set_yticks([])
        
                plt.text(+5, +5, "%d"%m[k]["id"])
                plt.text(-cutrad, -cutrad, "%.2f$\pm$%.2f"%(m[k]["fit_mag"], m[k]["fiterr"]), color="b")
            k = k+1
    
    plt.savefig(os.path.join(plotdir, image + "plot.png"))
    plt.clf()

def get_xy_coords(image, ra, dec):
    '''
    Uses the wcs-rd2xy routine to compute the proper pixel number where the target is.
    Sometime the pywcs does not seem to be providing the correct answer, as it does not seem
    to be using the SIP extension.
    
    '''
    import re
    import subprocess
    cmd = "wcs-rd2xy -w %s -r %.5f -d %.5f"%(image, ra, dec)
    proc = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
    output = proc.stdout.read()    
    print output 
    output = output.split("->")[1]
    
    coords = []
    for s in output.split(","):
        coords.append(float(re.findall("[-+]?\d+[\.]?\d*", s)[0]))
        
    return coords
    
def get_app_phot_target(image, plot_only=False, store=True, wcsin="logical", fwhm=2, box=4):
    '''
    coords: files: 
    wcsin: can be "world", "logic"
    '''
    # Load packages; splot is in the onedspec package, which is in noao. 
    # The special keyword _doprint=0 turns off displaying the tasks 
    # when loading a package. 
    
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fxn()
    if (not plot_only):
        iraf.noao(_doprint=0)
        iraf.digiphot(_doprint=0)
        iraf.apphot(_doprint=0)
        iraf.unlearn("apphot")
    
    #Check that actually the object is within this frame.
    ra, dec = cc.hour2deg(fitsutils.get_par(image, 'OBJRA'), fitsutils.get_par(image, 'OBJDEC'))
    
    impf = pf.open(image)
    wcs = pywcs.WCS(impf[0].header)
    #pra, pdec = wcs.wcs_sky2pix(ra, dec, 1)
    pra, pdec = wcs.wcs_sky2pix(np.array([ra, dec], ndmin=2), 1)[0]

    shape = impf[0].data.shape
    
    if (pra > 0)  and (pra < shape[0]) and (pdec > 0) and (pdec < shape[1]):
        pass
    else:
        #print image, "ERROR! Object coordinates are outside this frame. Skipping any aperture photometry!!"
        #print pra, pdec, shape
        return
    
    
    #Using new method to derive the X, Y pixel coordinates, as pywcs does not seem to be working well.
    pra, pdec = get_xy_coords(image, ra, dec)
        
    imdir = os.path.dirname(image)
    imname = os.path.basename(image)
    plotdir = os.path.join(imdir, "photometry")
    
    if not os.path.isdir(plotdir):
        os.makedirs(plotdir)
        
    out_name = os.path.join(plotdir, imname +  ".seq.mag")
    clean_name = os.path.join(plotdir, imname +  ".objapp.mag")
    
    
    fwhm_value = fwhm
    if (fitsutils.has_par(image, 'FWHM')):
        fwhm_value = fitsutils.get_par(image, 'FWHM')
    airmass_value = fitsutils.get_par(image, 'AIRMASS')
    exptime = fitsutils.get_par(image, 'EXPTIME')
    gain = fitsutils.get_par(image, 'GAIN')
    
    
    #Obtain the fwhm in pixels
    if wcsin == "logical":   
        if (fitsutils.has_par(image, 'SEEPIX')):
            fwhm_value = fitsutils.get_par(image, 'SEEPIX')
        else:
            fwhm_value = fwhm_value / 0.394
    
    #print "FWHM", fwhm_value
    aperture_rad = math.ceil(float(fwhm_value)*1.5)      # Set aperture radius to three times the PSF radius
    sky_rad= math.ceil(float(fwhm_value)*5)
    
    #print aperture_rad, sky_rad

    
    
    print "Saving coodinates for the object in pixels",pra,pdec
    coords = "/tmp/coords.dat"    
    np.savetxt("/tmp/coords.dat", np.array([[pra, pdec]]), fmt="%.4f %.4f")
    
    zmin, zmax = zscale.zscale(impf[0].data)
       
    im = plt.imshow(impf[0].data, vmin=zmin, vmax=zmax, origin="bottom")
    plt.scatter(pra, pdec, marker="o", s=100, facecolor="none")
    if (plot_only): 
        plt.savefig(os.path.join(plotdir, image+".png"))
        plt.clf()
    
    else:

        if os.path.isfile(out_name): os.remove(out_name)
        if os.path.isfile(clean_name): os.remove(clean_name)


        iraf.noao.digiphot.apphot.qphot(image = image,\
        cbox = box ,\
        annulus = sky_rad ,\
        dannulus = 10. ,\
        aperture = str(aperture_rad),\
        coords = coords ,\
        output = out_name ,\
        plotfile = "" ,\
        zmag = 0. ,\
        exposure = "exptime" ,\
        airmass = "airmass" ,\
        filter = "filters" ,\
        obstime = "DATE" ,\
        epadu = gain ,\
        interactive = "no" ,\
        radplots = "yes" ,\
        verbose = "no" ,\
        graphics = "stdgraph" ,\
        display = "stdimage" ,\
        icommands = "" ,\
        wcsin = "logical",
        wcsout = "logical",
        gcommands = "") 


        #iraf.noao.digiphot.apphot.phot(image=image, cbox=5., annulus=12.4, dannulus=10., salgori = "centroid", aperture=9.3,wcsin="world",wcsout="tv", interac = "no", coords=coords, output=out_name)
        iraf.txdump(out_name, "id,image,xcenter,ycenter,xshift,yshift,fwhm,msky,stdev,mag,merr", "yes", Stdout=clean_name)
        
    
        ma = np.genfromtxt(clean_name, comments="#", dtype=[("id","<f4"),  ("image","|S20"), ("X","<f4"), ("Y","<f4"), ("Xshift","<f4"), ("Yshift","<f4"),("fwhm","<f4"), ("ph_mag","<f4"), ("stdev","<f4"), ("fit_mag","<f4"), ("fiterr","<f4")])
        if (ma.size > 0):  
            if (ma.size==1):
                ma = np.array([ma])
            m = ma[~np.isnan(ma["fit_mag"])]
        else:
            print "Only one object found!"
            m = np.array([ma])
            
    
        if (fitsutils.has_par(image, "ZEROPT")):
            band = fitsutils.get_par(image, "filter")
            mag =  ma['fit_mag'][0] + fitsutils.get_par(image, "ZEROPT")
            magerr = np.sqrt(ma['fiterr'][0]**2+ fitsutils.get_par(image, "ZEROPTU")**2)  
	
            if np.isnan(mag):
		mag, magerr = 0, 0
            fitsutils.update_par(image, "APPMAG",mag) 
            fitsutils.update_par(image, "APPMAGER", magerr) 
            print fitsutils.get_par(image, "NAME"), band, ma['fit_mag'][0] + fitsutils.get_par(image, "ZEROPT"), np.sqrt(ma['fiterr'][0]**2+ fitsutils.get_par(image, "ZEROPTU")**2), fwhm_value
        else:
            mag =  ma['fit_mag'][0] 
            magerr = ma['fiterr'][0]  
	
            if np.isnan(mag):
		mag, magerr = 0, 0
            band = fitsutils.get_par(image, "filter")
            fitsutils.update_par(image, "APPMAG", mag )
            fitsutils.update_par(image, "APPMAGER", magerr)
            print fitsutils.get_par(image, "NAME"), band, ma['fit_mag'][0] , ma['fiterr'][0], fwhm_value
                 
        X = int(ma["X"][0])
        Y = int(ma["Y"][0])
        pra = int(pra)
	pdec = int(pdec)
        
        plt.scatter(X, Y, marker="o", s=100, facecolor="none", edgecolor="red")
        plt.colorbar(im)
        plt.savefig(os.path.join(plotdir, image+".png"))
        plt.clf()
        
        zmin, zmax = zscale.zscale(impf[0].data.T[X-50:X+50,Y-50:Y+50].T)
        im = plt.imshow(impf[0].data.T[pra-50:pra+50,pdec-50:pdec+50].T, vmin=zmin, vmax=zmax, interpolation="none", origin="bottom", extent=(-50,50,-50,50))
        c1 = plt.Circle( (pra-X, pdec-Y), edgecolor="k", facecolor="none", radius=aperture_rad, label="Initial position")
        c11 = plt.Circle( (pra-X, pdec-Y), edgecolor="k", facecolor="none", radius=sky_rad)
        c2 = plt.Circle( (0, 0), edgecolor="orange", facecolor="none", radius=aperture_rad, label="Adjusted centroid")
        c22 = plt.Circle( (0, 0), edgecolor="orange", facecolor="none", radius=sky_rad)
        plt.gca().add_artist(c1)
        plt.gca().add_artist(c11)
        plt.gca().add_artist(c2)
        plt.gca().add_artist(c22)
        plt.colorbar(im)
        
        myhandles = []
        markers = ["o", "o"]
        labels = ["Initial position", "Adjusted centroid"]
        cols = ["k", "orange"]
        for i in np.arange(len(markers)):
                myhandles.append(mlines.Line2D([], [], mec=cols[i], mfc="none", marker=markers[i], ls="None", markersize=10, label=labels[i]))
        plt.legend(handles=myhandles, loc="lower left", labelspacing=0.3, fontsize=11, numpoints=1, frameon=False, ncol=5, bbox_to_anchor=(0.0, 0.00), fancybox=False, shadow=True)

        plt.title("MIN: %.0f MAX: %.0f"%(np.nanmin(impf[0].data.T[X-50:X+50,Y-50:Y+50]), np.nanmax(impf[0].data.T[X-50:X+50,Y-50:Y+50])))
        plt.savefig(os.path.join(plotdir, image+"_zoom.png"))
        plt.clf()

 
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=\
        '''

        Runs astrometry.net on the image specified as a parameter and returns 
        the offset needed to be applied in order to center the object coordinates 
        in the reference pixel.
            
        ''', formatter_class=argparse.RawTextHelpFormatter)


    parser.add_argument('reduced', type=str, help='Directory containing the reduced fits for the night.')

    args = parser.parse_args()
    
    reduced = args.reduced
    
    os.chdir(reduced)
    

    for f in glob.glob("*.fits"):
        if(fitsutils.has_par(f, "IMGTYPE") and fitsutils.get_par(f, "IMGTYPE") == "SCIENCE" or fitsutils.get_par(f, "IMGTYPE") == "ACQUISITION"):
		#print f
        	get_app_phot_target(f, box=5)
