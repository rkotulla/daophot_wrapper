# daophot_wrapper

This is a small python wrapper around the DAOPhot package written by Peter Stetson. It runs all the usual steps from source detection (find), aperture photometry (phot), PSF template generation (pick & psf) to the final global PSf fitting and luminosity estiamtion using allstar.
Stars suitable to contribute to the PSF template are automatically selected by pre-generating a source-extractor catalog isolate reasonably bright but unsaturated stars via their known positions, peak intensitities and FWHM values.
