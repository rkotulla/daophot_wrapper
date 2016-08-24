#!/usr/bin/env python


import os
import sys
import daophot_wrapper
import pyfits
import numpy



if __name__ == "__main__":

    for fn in sys.argv[1:]

        hdulist = pyfits.open(fn)

        dao = daophot_wrapper.Daophot()
        dao.prescale = 1./hdulist[0].header['NMGY']

        # get average sky value
        sky = numpy.mean(hdulist[2].data.field('ALLSKY'))
        print sky
        dao.add_sky = sky
        dao.gain = 3
        dao.readnoise = 10
        #dao.phot_params['A1'] = 10
        dao.phot_params['IS'] = 20
        dao.phot_params['OS'] = 25
        dao.fitting_radius = 5 #10
        dao.psf_width = 25
        dao.load(fn)

        out_fn = fn[:-5]+".dao.fits"
        dao.set_output(out_fn)
        dao.auto(remove_nonstars=True, dao_intermediate_fn=fn[:-5]+".daoraw.fits")


