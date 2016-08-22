#!/usr/bin/env  python

import daophot_wrapper
import sys
import os

if __name__ == "__main__":
    fn = sys.argv[1]
    if (os.path.isfile(fn)):
        ap = daophot_wrapper.APfile(fn)
        ap.dump()
