#!/usr/bin/env python

import os, sys
import subprocess
import select
import time
import shutil
import pyfits

sys.path.append("/work/podi_prep56")
from podi_definitions import *

from optparse import OptionParser
import scipy.stats
import sitesetup

class ProcessHandler( object ):

    def __init__(self, args, read_timeout=0.1, verbose=True, send_delay=0.0):

        self.proc = subprocess.Popen(
            args,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.stdout_poll = select.poll()
        self.stdout_poll.register(self.proc.stdout, select.POLLIN)

        self.read_timeout = read_timeout
        self.verbose = verbose
        self.send_delay = send_delay

    def read(self, timeout=None):

        retcode = self.proc.poll()
        if (not retcode == None):
            raise Error("Process dead!")
            
        if (timeout == None): timeout=self.read_timeout

        output = []
        start_time = time.time()
        while ((time.time() - start_time) < timeout):
            poll_result = self.stdout_poll.poll(0)

            if (poll_result):
                filedesc, mask = poll_result[0]
                if (mask & select.POLLIN):
                    line = self.proc.stdout.read(1)
                    output.append(line)
            else:
                time.sleep(0.001)

        if (self.verbose):
            sys.stdout.write("".join(output))
        return "".join(output)

    def read_until(self, until_text, timeout=1):
        if (type(until_text) == str):
            until_text = [until_text]
        start_time = time.time()
        full_return = ""
        found = -1
        while(((time.time() - start_time) < timeout or timeout<0) and found<0):
            new_text = self.read()
            full_return += new_text
            for match_id, ut in enumerate(until_text):
                #print ut, "\n", full_return
                if (full_return.find(ut) > 0):
                    found = match_id
                    break
        return full_return, found

    def write(self, text, retry=3):
        retries = 0
        while(retries < retry):
            try:
                self.proc.stdin.write(text)
                break
            except IOError:
                retries += 1
                time.sleep(0.05)
                continue
            except:
                pass
                #print e
        if (self.verbose):
            sys.stdout.write(text)
        time.sleep(self.send_delay)
        return

    def write_and_read(self, text):
        self.write(text)
        return self.read()



class DAOPHOT ( object ):

    def __init__(self, options, fitsfile, threshold, dao_dir=None):

        self.cmd_options = options
        self.detection_threshold = threshold
        self.fitsfile = fitsfile

        self.dao_dir = options.dao_dir if dao_dir is None else dao_dir

        self.daophot_exe = "%s/daophot" % (self.dao_dir)
        self.allstar_exe = "%s/allstar" % (self.dao_dir)
        

        #
        # open FITS file and read some important parameters
        #
        self.hdulist =  pyfits.open(self.fitsfile)

        self.gain = self.hdulist[0].header['GAIN'] if 'GAIN' in self.hdulist[0].header \
                    else 1.5
        self.readnoise = self.hdulist[0].header['RDNOISE'] if 'RDNOISE' in self.hdulist[0].header \
                         else 6.5

        self.files = {}

        self.running = False
        if (not self.running):
            self.start_daophot()


    def start_daophot(self):
        #
        # Start up DAOPhot
        #
        self.daophot = ProcessHandler([self.daophot_exe], verbose=True)

        self.daophot.read()
        # first question in READNOISE
        # Value unacceptable --- please re-enter
        #
        #                        READ NOISE (ADU; 1 frame) = 1.4
        #
        self.daophot.write("%.2f\n" % (self.readnoise))


        self.daophot.read()
        # Value unacceptable --- please re-enter
        #
        #                        GAIN (e-/ADU; 1 frame) = 1.4
        #
        self.daophot.write("%.2f\n" % (self.gain))
        self.daophot.read()

        #
        # Now we are ready for action
        #
        
    def get_file(self, extension):
        return "%s.%s" % (self.fitsfile[:-5], extension)

    def get_process_handler(self):
        return self.daophot


    def wait_for_prompt(self):
        self.daophot.read_until("Command:")


    def attach(self, filename=None):
        
        if (not filename == None):
            self.fitsfile = filename

        self.daophot.write("ATTACH %s\n" % (self.fitsfile))
#        self.daophot.read_until("Input image name:")

#        self.daophot.write("%s\n" % (self.fitsfile))
        self.wait_for_prompt()


    def options(self, **kwargs):

        if (kwargs == None):
            return

        self.daophot.write("OPTION\n")
        self.daophot.read_until("File with parameters (default KEYBOARD INPUT):")

        self.daophot.write("\n")
        self.daophot.read_until("OPT>")

        for key, value in kwargs.iteritems():

            # set options
            self.daophot.write("%s = %.2f\n" % (key, value))
                # readnoise=None,
                # gain=None,
                # fwhm=None,
                # watch=None,
                # psf_radius=None,

            # and wait for new prompt
            self.daophot.read_until("OPT>")

        # empty string takes us back to command prompt
        self.daophot.write("\n")
        self.wait_for_prompt()

    def sky(self):
        self.daophot.write("SKY\n")
        self.wait_for_prompt()


    def find(self, avg=1, sum=1, coo_file=None):

        self.daophot.write("FIND\n")
        #      Sky mode and standard deviation =   -0.036   28.680
        #
        #              Clipped mean and median =    4.045    2.679
        #   Number of pixels used (after clip) = 15,088
        #                       Relative error = 1.14
        #
        #                 Number of frames averaged, summed:    
        self.daophot.read_until("Number of frames averaged, summed:")

        self.daophot.write("%d,%d\n" % (avg, sum))
        #         File for positions (default leo1_nans.coo):

        
        self.daophot.read_until("File for positions")
        if (not coo_file == None):
            # XXXXX
            self.files['coo'] = coo_file
        else:
            self.files['coo'] = self.get_file('coo')

        #coo_file = tmpfile[:-5]+".coo"
        clobberfile(self.files['coo'])
        self.daophot.write("%s\n" % (self.files['coo']))

        #
        # ...
        #
        #                           Are you happy with this? yes
        #
        catdump, found = self.daophot.read_until(["Are you happy with this?"], timeout=-1)
        self.daophot.write("yes\n")

        self.wait_for_prompt()

    def phot(self, ap_file=None, coo_file=None, **kwargs):

        self.daophot.write("PHOT\n")
        #
        #      File with aperture radii (default photo.opt):
        self.daophot.read_until("File with aperture radii (default photo.opt):")


        self.daophot.write("\n")
        #    
        # Error opening input file photo.opt                                              
        #
        #
        #  A1  RADIUS OF APERTURE  1 =     0.00     A2  RADIUS OF APERTURE  2 =     0.00
        #  A3  RADIUS OF APERTURE  3 =     0.00     A4  RADIUS OF APERTURE  4 =     0.00
        #  A5  RADIUS OF APERTURE  5 =     0.00     A6  RADIUS OF APERTURE  6 =     0.00
        #  A7  RADIUS OF APERTURE  7 =     0.00     A8  RADIUS OF APERTURE  8 =     0.00
        #  A9  RADIUS OF APERTURE  9 =     0.00     AA  RADIUS OF APERTURE 10 =     0.00
        #  AB  RADIUS OF APERTURE 11 =     0.00     AC  RADIUS OF APERTURE 12 =     0.00
        #  IS       INNER SKY RADIUS =     0.00     OS       OUTER SKY RADIUS =     0.00
        #
        # PHO> 
        self.daophot.read_until("PHO>")

        #
        # Now parse all options requested by the user
        #
        for key, value in kwargs.iteritems():

            # set options
            self.daophot.write("%s = %.2f\n" % (key, value))

            # and wait for new prompt
            self.daophot.read_until("PHO>")

        #
        # empty string takes us back to command prompt
        #
        self.daophot.write("\n")


        #
        #  A1  RADIUS OF APERTURE  1 =     7.00     A2  RADIUS OF APERTURE  2 =     0.00
        #  A3  RADIUS OF APERTURE  3 =     0.00     A4  RADIUS OF APERTURE  4 =     0.00
        #  A5  RADIUS OF APERTURE  5 =     0.00     A6  RADIUS OF APERTURE  6 =     0.00
        #  A7  RADIUS OF APERTURE  7 =     0.00     A8  RADIUS OF APERTURE  8 =     0.00
        #  A9  RADIUS OF APERTURE  9 =     0.00     AA  RADIUS OF APERTURE 10 =     0.00
        #  AB  RADIUS OF APERTURE 11 =     0.00     AC  RADIUS OF APERTURE 12 =     0.00
        #  IS       INNER SKY RADIUS =    10.00     OS       OUTER SKY RADIUS =    20.00
        #
        #       Input position file (default leo1_nans.coo):
        self.daophot.read_until("Input position file")

        _coo = self.files['coo'] if coo_file == None else coo_file
        self.daophot.write("%s\n" % (_coo))
        #                Output file (default leo1_nans.ap):

        self.daophot.read_until("Output file")
        
        if (not ap_file == None):
            self.files['ap'] = ap_file
        elif 'ap' not in self.files:
            self.files['ap'] = self.get_file("ap")
        clobberfile(self.files['ap'])
        self.daophot.write("%s\n" % (self.files['ap']))

        self.wait_for_prompt()
        

        # daophot.write_and_read("%s\n" % (coo_file))

        # ap_file = tmpfile[:-5]+".ap"
        # clobberfile(ap_file)
        # daophot.write("%s\n" % (ap_file))
        # #
        # # ... lots of photometry coming now ...
        # #
        # phot, found = daophot.read_until(["Command:"], timeout=-1)

    def pick_midrange(self):
        
        with open("default.param", "w") as param:
            print >>param, "\n".join([
                "ALPHAWIN_J2000", "DELTAWIN_J2000",
                "XWIN_IMAGE", "YWIN_IMAGE", 
                "FWHM_IMAGE", "FWHM_WORLD", 
                "BACKGROUND", 
                "FLAGS", "EXT_NUMBER", 
                "MAG_AUTO", "MAGERR_AUTO", 
                "FLUX_MAX", 
                "AWIN_IMAGE", "BWIN_IMAGE", "THETA_IMAGE", 
                "ELONGATION", "ELLIPTICITY", 
                "NUMBER",
                ])
        sexconf = {
            "CATALOG_NAME":      "test.cat",
            "CATALOG_TYPE":      "ASCII_HEAD",
            "PARAMETERS_NAME":   "default.param",
            "DETECT_MINAREA":    "5",
            "DETECT_MAXAREA":    "0",
            "THRESH_TYPE":       "RELATIVE",
            "DETECT_THRESH":     "1.5",
            "ANALYSIS_THRESH":   "1.5",
            "FILTER":            "N",
            "WEIGHT_TYPE":       "NONE",
            "RESCALE_WEIGHTS":   "Y",
            "WEIGHT_IMAGE":      "weight.fits",
            "WEIGHT_GAIN ":      "Y",
            "MAG_ZEROPOINT":     "26.0",
            "GAIN":              "0.0",
            "GAIN_KEY":          "GAIN",
            "CHECKIMAGE_TYPE":   "NONE",
            "VERBOSE_TYPE":      "QUIET",
        }
        options = ""
        for key, value in sexconf.iteritems():
            # print key, value
            options += "-%s %s " % (key, value)

        cmd = "sex %s %s" % (options, self.fitsfile)
        print cmd
        os.system(cmd)
        catalog = numpy.loadtxt("test.cat")
        print catalog.shape

        
        # now select a bunch of stars with the right amount of peak flux, 
        # no flags, and a median fwhm
        no_flags = (catalog[:, 7] == 0)
        peak_flux = numpy.max(catalog[:, 11]) # 450
        good_flux = (catalog[:,11] > 0.2 * peak_flux) & (catalog[:,11] < 0.5*peak_flux)
        catalog = catalog[no_flags & good_flux]
        numpy.savetxt("test2.cat", catalog)

        good_fwhm = numpy.isfinite(catalog[:,4])
        for i in range(3):
            _sigm = scipy.stats.scoreatpercentile(catalog[:,4][good_fwhm], [16,50,84])
            med = _sigm[1]
            sigma = 0.5*(_sigm[2]-_sigm[0])
            print med, sigma, _sigm
            good_fwhm = (catalog[:,4] > (med-3*sigma)) & (catalog[:,4] < (med+3*sigma))

        catalog = catalog[good_fwhm]
        numpy.savetxt("test3.cat", catalog)

        #
        # Now save the source list as daophot-compatible LST file
        #
        self.files['lst'] = self.get_file('lst') #"test.lst" #
        with open(self.files['lst'], "w") as lst:
            print >>lst, """\
 NL    NX    NY  LOWBAD HIGHBAD  THRESH     AP1  PH/ADU  RNOISE    FRAD
  3  1664  1848   -28.4 32766.5  52.390   4.500 4165.08   4.596   6.000
"""
            catalog = catalog[:25]
            catalog_lst = numpy.empty((catalog.shape[0], 6))
            catalog_lst[:,0] = catalog[:,17]
            catalog_lst[:,1:3] = catalog[:,2:4]
            catalog_lst[:,3:5] = catalog[:, 9:11]
            catalog_lst[:,5] = catalog[:, 16]
            numpy.savetxt(lst,
                          catalog_lst,
                          "%d %.3f %.3f %3f %4f %3f")

        print "\n"*10
        
    def pick(self, nstars=15, maglimit=14, lst_file=None, ap_file=None):

        #
        # Now do some PSF modeling
        #
        self.daophot.write("PICK\n")
        #
        #            Input file name (default leo1_nans.ap):
        self.daophot.read_until("Input file name")

        _ap = self.files['ap'] if (ap_file == None) else ap_file
        self.daophot.write("%s\n" % (_ap))
        #       Desired number of stars, faintest magnitude: 

        self.daophot.read_until("Desired number of stars, faintest magnitude:")
        self.daophot.write("%d,%d\n" % (nstars, maglimit))

        #           Output file name (default leo1_nans.lst):
        self.daophot.read_until("Output file name")

        if (not lst_file == None):
            self.files['lst'] = lst_file
        elif (not 'lst' in self.files):
            self.files['lst'] = self.get_file('lst')
        clobberfile(self.files['lst'])

        self.daophot.write("%s\n" % (self.files['lst']))

        self.wait_for_prompt()

        #retstr, found = daophot.read_until(["candidates were found."], timeout=-1)
        #retstr, found = daophot.read_until(["Command:"], timeout=-1)
        #
        #        15 suitable candidates were found.
        #



    def psf(self, interactive=False, ap_file=None, lst_file=None, psf_file=None):

        
        self.daophot.write("PSF\n")
        #  File with aperture results (default leo1_nans.ap):
        self.daophot.read_until("File with aperture results")

        _ap = self.files['ap'] if (ap_file == None) else ap_file
        self.daophot.write("%s\n" % (_ap))

        self.daophot.read_until("File with PSF stars")
        #        File with PSF stars (default leo1_nans.lst): 

        _lst = self.files['lst'] if (lst_file == None) else lst_file
        self.daophot.write("%s\n" % (_lst))

        #           File for the PSF (default leo1_nans.psf):
        self.daophot.read_until("File for the PSF")
        
        if (not psf_file == None):
            self.files['psf'] = psf_file
        elif (not 'psf' in self.files):
            self.files['psf'] = self.get_file('psf')
        clobberfile(self.files['psf'])
        
        self.daophot.write("%s\n" % (self.files['psf']))

        done = False
        valid_psf_model = True
        while (not done):
            retstr, found = self.daophot.read_until(["Use this one?",
                                                     "Try this one anyway?",
                                                     "Failed to converge",
                                                     "File with PSF stars and neighbors"])

            if (found < 0):
                continue
            elif (found == 0):
                #  Use this one? y

                if (interactive):
                    user_input = raw_input("???")
                    if (user_input == ""):
                        user_done = True

                    self.daophot.write("%s\n" % (user_input))
                else:
                    self.daophot.write("yes\n")

            elif (found == 1):
                #  Use this one? y

                if (interactive):
                    user_input = raw_input("???")
                    if (user_input == ""):
                        user_done = True

                    self.daophot.write("%s\n" % (user_input))
                else:
                    self.daophot.write("no\n")

            elif (found == 2):
                # Failed to converge.
                valid_psf_model = False
                done = True

            elif (found == 3):
                done = True
                valid_psf_model = True


        return valid_psf_model

        # user_done = False
        # candidates_checked = 0
        # while (not user_done and candidates_checked < n_psf_candidates):
        #     text = daophot.read()
        #     print text

        #     user_input = raw_input("???")
        #     if (user_input == ""):
        #         user_done = True

        #     candidates_checked += 1

        # # for psf_candidate in range(n_psf_candidates):
        # #     psf = daophot.read_until("Use this one?")
        # #     daophot.write("yes\n")


        # ret, found = daophot.read_until(['Failed to converge.',
        #                                  'Command',
        #                                  '>>'])

        # valid_psf_model = True
        # if (found and ret.find("Failed to converge")):
        #     print "XXXXX\n"*10
        #     valid_psf_model = False



    def exit(self):
        self.daophot.write("EXIT\n")
        self.running = False

    def save_files(self, out_directory):
        if (not os.path.isdir(out_directory)):
            os.mkdir(out_directory)

        # Now move all files used during execution to the 
        # specified output directory
        for ftype in self.files:
            fn = self.files[ftype]
            _, bn = os.path.split(fn)
            try:
                shutil.copyfile(fn, "%s/%s" % (out_directory, bn))
            except:
                pass


class APfile (object):

    def __init__(self, filename):

        self.nl = 0
        self.nx = -1
        self.ny = -1
        self.lowbad = numpy.NaN
        self.highbad = numpy.NaN
        self.thresh = numpy.NaN
        self.ap1 = numpy.NaN
        self.gain = numpy.NaN
        self.readnoise = numpy.NaN

        self.src_stats = None
        self.src_phot = None

        self.column_description = [
            "Star ID number",
            "X coordinate of stellar centroid",
            "Y coordinate of stellar centroid",
            "Estimated modal sky value for the star",
            "Standard deviation of the sky values about the mean",
            "Skewness of the sky values about the mean",
            "magnitude / error in apertures...",
        ]

        self.n_apertures = 1

        self.filename = filename
        ap_return = self.read(self.filename)
        if (ap_return is not None):
            stats, src_stats, src_phot = ap_return
            self.nl = int(stats[0])
            self.nx = int(stats[1])
            self.ny = int(stats[2])
            self.lowbad = stats[3]
            self.highbad = stats[4]
            self.thresh = stats[5]
            self.ap1 = stats[6]
            self.gain = stats[7]
            self.readnoise = stats[8]
            self.fitting_radius = stats[9]

            self.src_stats = src_stats
            self.src_phot = src_phot
            self.n_apertures = numpy.sum(numpy.isfinite(self.src_phot[0,:,0]))

        return

    def read(self, filename):

        with open(filename, "r") as apf:
            header = apf.readline().strip()
            stats_line = apf.readline().strip()
            _ = apf.readline()

            # Read all data and prepare to insert it into the data buffer
            datablock_text = apf.readlines()
            n_blocks = len(datablock_text) / 3


            src_stats = numpy.empty((n_blocks, 6))
            src_phot = numpy.empty((n_blocks, 12, 2))
            src_phot[:,:,:] = numpy.NaN

            stats = numpy.fromstring(stats_line, count=10, sep=' ')
            #print "read a total of %d lines for %d blocks" % (len(datablock_text), len(datablock_text)/3)

            for star_id in range(n_blocks): #len(datablock_text), step=3):
                # print datablock_text[3*star_id+1]
                line1 = numpy.fromstring(datablock_text[3*star_id+1], sep=' ')
                line2 = numpy.fromstring(datablock_text[3 * star_id + 2], sep=' ')
                src_stats[star_id, :3] = line1[:3]
                src_stats[star_id, 3:] = line2[:3]

                n_phot = line1.shape[0]-3
                src_phot[star_id, :n_phot, 0] = line1[3:]
                src_phot[star_id, :n_phot, 1] = line2[3:]

            #print src_stats.shape, src_phot.shape

            return stats, src_stats, src_phot

        return None

    def write(self, filename):

        print "writing AP file to %s" % (filename)
        with open(filename, "w") as ap:
            print >>ap, " NL    NX    NY  LOWBAD HIGHBAD  THRESH     AP1  PH/ADU  RNOISE    FRAD"
            print >>ap, "%3d %5d %5d %7.1f %7.1f %7.3f %7.3f %7.3f %7.3f %7.3f" % (
                self.nl, self.nx, self.ny,
                self.lowbad, self.highbad,
                self.thresh, self.ap1, self.gain, self.readnoise, self.fitting_radius,
            )
            print >>ap

            for src in range(self.src_stats.shape[0]):
                print >>ap
                line1 = numpy.append(self.src_stats[src,0:3], self.src_phot[src,:self.n_apertures,0]).reshape((1,-1))
                line2 = numpy.append(self.src_stats[src,3:6], self.src_phot[src,:self.n_apertures,1]).reshape((1,-1))
                numpy.savetxt(ap, line1, fmt="%7d %8.3f %8.3f"+" %8.3f"*self.n_apertures)
                numpy.savetxt(ap, line2, fmt="%14.3f %5.2f %5.2f %7.4f"+" %8.4f"*(self.n_apertures-1))


        return

    def dump(self):

        # reformat the photometry
        phot = self.src_phot[:, :self.n_apertures, :]
        phot_1d = phot.reshape((-1,self.n_apertures*2))
        #print n_apertures, phot.shape, phot_1d.shape, self.src_stats.shape
        combined = numpy.append(self.src_stats, phot_1d, axis=1)
        #print combined.shape
        print "\n".join(["Column % 2d: %s" % (i+1,s) for i,s in enumerate(self.column_description)])
        numpy.savetxt(sys.stdout, combined)

    def remove_stars(self, star_ids):

        # sort all stars to be removed
        star_ids_sorted = numpy.sort(star_ids)

        # also sort the stars we have in the current catalog
        si = numpy.argsort(self.src_stats[:,0])
        src_stats_sorted = self.src_stats[si]
        src_phot_sorted = self.src_phot[si]

        #
        # Now we have both a sorted list of stars and a list of stars to be removed
        #
        keep_star = numpy.isfinite(src_stats_sorted[:,0])

        i_search = 0
        for remove_id in star_ids_sorted:
            for i in range(i_search, src_stats_sorted.shape[0]):
                if (src_stats_sorted[i,0] == remove_id):
                    keep_star[i] = False
                    i_search = i+1
                    break

        numpy.savetxt("input", src_stats_sorted)
        numpy.savetxt("output", src_stats_sorted[keep_star])

        self.src_stats = src_stats_sorted[keep_star]
        self.src_phot = src_phot_sorted[keep_star]

        return


class ALSfile(object):

    def __init__(self, fn):
        self.filename = fn

        self.nl = 0
        self.nx = -1
        self.ny = -1
        self.lowbad = numpy.NaN
        self.highbad = numpy.NaN
        self.thresh = numpy.NaN
        self.ap1 = numpy.NaN
        self.gain = numpy.NaN
        self.readnoise = numpy.NaN
        self.fiting_radius = numpy.NaN
        self.data = None

        als_return = self.read(self.filename)
        if (als_return is not None):
            stats, data = als_return

            self.nl = stats[0]
            self.nx = stats[1]
            self.ny = stats[2]
            self.lowbad = stats[3]
            self.highbad = stats[4]
            self.thresh = stats[5]
            self.ap1 = stats[6]
            self.gain = stats[7]
            self.readnoise = stats[8]
            self.fitting_radius = stats[9]

            self.data = data

    def read(self, filename):
        with open(filename, "r") as f_als:
            header = f_als.readline()
            stats_line = f_als.readline()
            _ = f_als.readline()
            data = numpy.loadtxt(f_als)

            print header.strip()
            print stats_line.strip()
            print data.shape

            #
            # convert stats from string to numbers
            #
            #         NL  NX   NY   LOWBAD  HIGHBAD  THRESH    AP1  PH/ADU  RNOISE   FRAD
            types = [int, int, int,  float,   float,  float, float,  float,  float, float]
            stats_items = stats_line.split()
            stats = [None] * len(stats_items)
            for i in range(len(stats_items)):
                stats[i] = types[i](stats_items[i])
            return stats, data

        return None

    def write(self, filename):
        pass




class ALLSTAR ( object ):


    def __init__(self, options, fitsfile, 
                 psf_file=None,
                 ap_file=None, 
                 als_file=None, 
                 starsub_file=None,
                 dao_dir=None,
                 **kwargs):

        print "This all ALLSTAR"

        self.cmd_options = options
        self.fitsfile = fitsfile

        self.dao_dir = options.dao_dir if dao_dir is None else dao_dir
        self.allstar_exe = "%s/allstar" % (self.dao_dir)

        self.files = {}
        self.files['psf'] = self.get_file('psf') if psf_file == None else psf_file
        self.files['ap'] = self.get_file('ap') if ap_file == None else ap_file
        self.files['als'] = self.get_file('als') if als_file == None else als_file
        self.files['starsub'] = self.get_file('starsub.fits') if starsub_file == None else starsub_file

        print kwargs

        self.running = False
        if (not self.running):
            self.start_allstar(kwargs)

    def get_file(self, extension):
        return "%s.%s" % (self.fitsfile[:-5], extension)


    def start_allstar(self, kwargs):

        self.allstar = ProcessHandler([self.allstar_exe], verbose=True)
        self.allstar.read_until("OPT>")

        for key, value in kwargs.iteritems():
            self.allstar.write("%s = %.2f\n" % (key, value))
            self.allstar.read_until("OPT>")

        self.allstar.write("\n")

        self.allstar.read_until("Input image name:")
        self.allstar.write("%s\n" % (self.fitsfile))

        self.allstar.read_until("File with the PSF")
        self.allstar.write("%s\n" % (self.files['psf']))

        self.allstar.read_until("Input file")
        self.allstar.write("%s\n" % (self.files['ap']))

        self.allstar.read_until("File for results")
        clobberfile(self.files['als'])
        self.allstar.write("%s\n" % (self.files['als']))

        self.allstar.read_until("Name for subtracted image")
        clobberfile(self.files['starsub'])
        self.allstar.write("%s\n" % (self.files['starsub']))

        self.allstar.read_until(["Finished", "Good bye"], timeout=-1)

    def save_files(self, out_directory):
        if (not os.path.isdir(out_directory)):
            os.mkdir(out_directory)
        # Now move all files used during execution to the 
        # specified output directory
        for ftype in self.files:
            fn = self.files[ftype]
            _, bn = os.path.split(fn)
            try:
                shutil.copyfile(fn, "%s/%s" % (out_directory, bn))
            except:
                pass


    def verify_real_star(self, noise_cutoff=-2, n_max_bad_pixels=2):
        # open the star-subtracted file
        print("Opening star-subtracted file: %s" % (self.files['als']))
        starsub_hdu = pyfits.open(self.files['starsub'])
        starsub = starsub_hdu[0].data
        input_hdu = pyfits.open(self.fitsfile)
        input = input_hdu[0].data

        # load the catalog of all sources computed by allstar
        als = ALSfile(self.files['als'])
        data = als.data

        noise = numpy.sqrt( numpy.fabs(input)*als.gain + als.readnoise**2)
        avg_sky = numpy.median(data[:,5])

        # add some padding to the input image to avoid problems for
        # sources close to any of the edges
        fitting_radius = int(numpy.round(als.fitting_radius,0))
        img_padded = numpy.pad(
            starsub,
            pad_width=int(fitting_radius),
            mode='constant',
            constant_values=numpy.NaN
        )
        noise_padded = numpy.pad(
            noise,
            pad_width=int(fitting_radius),
            mode='constant',
            constant_values=numpy.NaN
        )
        is_star = numpy.isfinite(data[:,0])

        pyfits.PrimaryHDU(data=((img_padded-avg_sky)/noise_padded)[fitting_radius:-fitting_radius, fitting_radius:-fitting_radius]).writeto("s2n.fits", clobber=True)

        for isrc, src in enumerate(als.data):
            center_x = src[1]
            center_y = src[2]
            local_sky = src[5]
            print center_x, center_y, src

            cx = int(numpy.round(center_x,0)) + fitting_radius
            cy = int(numpy.round(center_y, 0)) + fitting_radius

            box = img_padded[cy-fitting_radius:cy+fitting_radius, cx-fitting_radius:cx+fitting_radius]
            good = box[numpy.isfinite(box)]
            if (good.size <= 0):
                is_star[isrc] = False

            noise_box = noise_padded[cy-fitting_radius:cy+fitting_radius, cx-fitting_radius:cx+fitting_radius]
            s2n = (box - local_sky) / noise_box

            bad_pixels = s2n < noise_cutoff
            if (numpy.sum(bad_pixels) > n_max_bad_pixels):
                is_star[isrc] = False

        bad_stars = data[~is_star]
        numpy.savetxt("bad_stars", bad_stars)

        bad_star_ids = data[~is_star][:,0]
        return bad_star_ids

class Daophot( object ):

    def __init__(self, filename=None):
        #
        # Set all values that we will need
        #
        self.filename = filename

        self.phot_params = {
            'IS': 10,
            'OS': 20,
            'A1': 4.5,
            'A2': 5,
        }

        self.pick_params = {
            'nstars': 20,
            'maglimit': 18,
        }

        self.threshold = 3
        self.psf_width = 5
        self.fitting_radius = 5
        self.extra = 5
        self.watch = 0

        self.gain = 1.3
        self.readnoise = 5
        self.prescale = 1.0
        self.add_sky = 0.0

        self.dao = None
        self.allstar = None
        self.dao_dir = sitesetup.dao_dir

        self.output_filename = None

        if (self.filename is not None):
            self.load()
        #
        #
        #
        pass

    def set_gain(self, gain):
        # if (type(gain) == str):
        #     self.gain = hdulist[0].header['GAIN']
        self.gain = gain
        pass

    def set_readnoise(self, readnoise):
        # if (type(self.readnoise) == str):
        #     self.readnoise = hdulist[0].header['RDNOISE']
        self.readnoise = readnoise

    def load(self, filename=None):

        if (filename is not None):
            self.filename = filename

        if (self.output_filename is None):
            self.output_filename = self.filename[:-5]+".daophot_output.fits"

        hdulist = pyfits.open(self.filename)


        #
        # If available, open the weight file, and set all undefined pixels
        # to NaN to properly mask them out.
        #
        weightfile = self.filename[:-5] + ".weight.fits"
        if (os.path.isfile(weightfile)):
            weights_hdu = pyfits.open(weightfile)
            weights = weights_hdu[0].data

            hdulist[0].data[weights <= 0] = numpy.NaN

        #
        # Apply pre-scaling and re-add the background to allow proper
        # noise estimation that we will need for source detection and to
        # yield proper photometric errors.
        #
        hdulist[0].data = (hdulist[0].data * self.prescale) + self.add_sky

        #
        # write the hdulist as a temp-file
        #
        self.tmpfile = "/tmp/pid%d.fits" % (os.getpid())
        hdulist.writeto(self.tmpfile, clobber=True)
        print "tmp-file:", self.tmpfile

        pass

    def set_output(self, output_fn):
        self.output_filename = output_fn

    def write_final_results(self):
        if (self.allstar is None):
            # something went wrong
            return False

        #
        # Open the resulting star-sub file and un-do the scaling we did
        # before the DAOPhot & ALLSTAR runs
        #
        hdulist = pyfits.open(self.allstar.files['starsub'])
        img = hdulist[0].data
        img_corr = (img - self.add_sky) / self.prescale

        # assemble all information to go into the output frame
        out_hdulist = [pyfits.PrimaryHDU()]
        out_hdulist.append(
            pyfits.ImageHDU(data=img_corr, header=hdulist[0].header)
        )

        # write output file
        out_hdulist = pyfits.HDUList(out_hdulist)
        out_hdulist.writeto(self.output_filename, clobber=True)
        return True


    def auto(self):

        # open file and read some parameters
        # self.load()

        # time.sleep(2)

        #
        # Start daophot and read the FITS file.
        #
        self.dao = DAOPHOT(
            options=None, #options,
            fitsfile=self.tmpfile,
            threshold=self.threshold,
            dao_dir=self.dao_dir,
        )

        self.dao.attach(self.tmpfile)

        #
        # set DAOPhot internal parameters
        #
        #psf_width = 25.0
        #fitting_radius = 10.  # 10*psf_width
        self.dao.options(thresh=self.threshold,
                    psf=self.psf_width,
                    fitting=self.fitting_radius,
                    extra=5,
                    watch=0)

        # estimate sky background
        self.dao.sky()

        # find sources; make sure to set the right number of sum/avg samples
        self.dao.find(avg=1)

        # run aperture photometry
        self.dao.phot(
            **self.phot_params
        )
        #    IS=10, OS=20, A1=4.5, A2=5)

        # select appropriate PSF stars
        self.dao.pick_midrange()
        self.dao.pick(**self.pick_params)

            #nstars=25, maglimit=18)

        # estimate PSF
        good_psf = self.dao.psf(interactive=False)

        self.dao.exit()

        outdir = os.getcwd()
        self.dao.save_files(outdir)


        #
        # if we have a well-defined PSF, go on to fit all stars in the frame
        # using ALLSTAR
        #
        if (good_psf):
            # allstar = ALLSTAR(options, tmpfile, FIT=fitting_radius, IS=0, OS=4)
            self.allstar = ALLSTAR(
                None,
                self.tmpfile,
                FIT=self.fitting_radius,
                IS=4,
                OS=40,
                dao_dir=self.dao_dir
            )
            self.allstar.save_files(outdir)

            bad_stars = self.allstar.verify_real_star() #self.allstar.files['starsub'])
            print bad_stars

            print("removing bad stars from AP file")
            ap = APfile(self.dao.files['ap'])
            ap.remove_stars(bad_stars)
            new_ap_fn = self.tmpfile[:-5]+".cleanap"
            print("writing new cleaned input catalog for ALLSTAR to %s" % (new_ap_fn))
            ap.write(new_ap_fn)

            new_als_file = self.tmpfile[:-5]+".cleanals"
            new_starsub_file = self.tmpfile[:-5]+".cleanstarsub.fits"

            print("Re-running ALLSTAR with the cleaned input source catalog")
            self.allstar = ALLSTAR(
                None,
                self.tmpfile,
                FIT=self.fitting_radius,
                IS=4,
                OS=40,
                dao_dir=self.dao_dir,
                ap_file=new_ap_fn,
                als_file=new_als_file,
                starsub_file=new_starsub_file,
            )
            self.allstar.save_files(outdir)

            self.write_final_results()
        else:
            print "Can't run ALLSTAR since we did not derive a converged PSF fit"


    pass

def run_all_steps(options,
                  filename,
                  prescale=1.0, 
                  add_sky=0.,
                  gain=1.3, 
                  readnoise=5.0,
                  ):

    if (options.allstar == ""):
        #filename = cmdline_args[0]
        print("Running DAOPhot on %s" % (filename))

        # open file and read some parameters
        hdulist = pyfits.open(filename)

        if (type(gain) == str):
            gain = hdulist[0].header['GAIN']
        if (type(readnoise) == str):
            readnoise = hdulist[0].header['RDNOISE']

        #
        # If available, open the weight file, and set all undefined pixels
        # to NaN to properly mask them out.
        #
        weightfile = filename[:-5]+".weight.fits"
        if (os.path.isfile(weightfile)):
            weights_hdu = pyfits.open(weightfile)
            weights = weights_hdu[0].data

            hdulist[0].data[weights <= 0] = numpy.NaN

        #
        # Apply pre-scaling and re-add the background to allow proper 
        # noise estimation that we will need for source detection and to
        # yield proper photometric errors.
        #
        hdulist[0].data = (hdulist[0].data * prescale) + add_sky
        
        #
        # write the hdulist as a temp-file
        #
        tmpfile = "/tmp/pid%d.fits" % (os.getpid())
        hdulist.writeto(tmpfile, clobber=True)   
        print "tmp-file:", tmpfile

        #time.sleep(2)

        #
        # Start daophot and read the FITS file.
        #
        dao = DAOPHOT(options=options, 
                      fitsfile=tmpfile, 
                      threshold=options.threshold)

        dao.attach(tmpfile)

        #
        # set DAOPhot internal parameters
        #
        psf_width = 25.0
        fitting_radius = 10. #10*psf_width
        dao.options(thresh=options.threshold,
                    psf=psf_width,
                    fitting=fitting_radius,
                    extra=5,
                    watch=0)

        # estimate sky background
        dao.sky()

        # find sources; make sure to set the right number of sum/avg samples
        dao.find(avg=2)

        # run aperture photometry
        dao.phot(IS=10, OS=20, A1=4.5, A2=5)

        # select appropriate PSF stars
        dao.pick_midrange()
        dao.pick(nstars=25, maglimit=18)

        # estimate PSF
        good_psf = dao.psf(interactive=False)

        dao.exit()
        
        dao.save_files(options.outdir)
    else:
        tmpfile = options.allstar

    #
    # if we have a well-defined PSF, go on to fit all stars in the frame
    # using ALLSTAR
    #
    if (good_psf):
        # allstar = ALLSTAR(options, tmpfile, FIT=fitting_radius, IS=0, OS=4)
        allstar = ALLSTAR(options, tmpfile, FIT=fitting_radius, IS=4, OS=40)
        allstar.save_files(options.outdir)
    else:
        print "Can't run ALLSTAR since we did not derive a converged PSF fit"


if __name__ == "__main__":

    parser = OptionParser()
    parser.add_option("", "--dao", dest="dao_dir",
                      help="Path holding DAOphot executables",
                      default="/home/rkotulla/install/daophot")
    parser.add_option("-t", "--threshold", dest="threshold",
                      help="Detection Threshold",
                      default=10,
                      type=float)
    parser.add_option("-a", "--allstar", dest="allstar",
                      help="ALLSTAR only mode",
                      default="",
                      type=str)
    parser.add_option("-o", "--outdir", dest="outdir",
                      help="Directory for output files",
                      default=".",
                      type=str)
    (options, cmdline_args) = parser.parse_args()

    print options
    print type(options.threshold)
    # sys.exit(0)

    daophot_exe = "%s/daophot" % (options.dao_dir)
    allstar_exe = "%s/allstar" % (options.dao_dir)

    run_all_steps(options=options,
                  filename=cmdline_args[0],
                  prescale=1.0, 
                  add_sky=0.,
                  gain=1.3, 
                  readnoise=5.0,
                  )

    sys.exit(0)

        
    # Shutdown daophot
    daophot.write("EXIT\n")
    daophot.read()


    if (not valid_psf_model):
        sys.exit(0)


