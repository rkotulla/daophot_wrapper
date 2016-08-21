#!/usr/bin/env python


import os
import sys
import daophot_wrapper



if __name__ == "__main__":

    fn = sys.argv[1]


    dao = daophot_wrapper.Daophot(fn)
    dao.auto()
