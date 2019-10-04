#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Oct  4 12:05:31 2019

@author: lagerwer
"""

# Import code
import msdnet
from pathlib import Path

# Define dilations in [1,10] as in paper.
dilations = msdnet.dilations.IncrementDilations(10)

# Create main network object for regression, with 100 layers,
# [1,10] dilations, 1 input channel, 1 output channel, using
# the GPU (set gpu=False to use CPU)
n = msdnet.network.MSDNet(100, dilations, 1, 1, gpu=True)

# Initialize network parameters
n.initialize()

# Define training data
# First, create lists of input files (noisy) and target files (noiseless)
flsin = []
flstg = []
files = ['{:02d}'.format(i + 1) for i in range(21)]
path = '/export/scratch2/lagerwer/data/FleXray/walnuts_10MAY'
dset = 'noisy'
for i in range(1,16):
    flsin.extend(Path(path + '/walnut_{}/{}/tiffs/FDK/'.format(files[i], dset)).glob('*.tiff'))
    flstg.extend(Path(path + '/walnut_{}/{}/tiffs/GS/'.format(files[i], dset)).glob('*.tiff'))
    
flsin = sorted(flsin)
flstg = sorted(flstg)
# Create list of datapoints (i.e. input/target pairs)
dats = []
for i in range(len(flsin)):
    # Create datapoint with file names
    d = msdnet.data.ImageFileDataPoint(str(flsin[i]),str(flstg[i]))
    # Augment data by rotating and flipping
    d_augm = msdnet.data.RotateAndFlipDataPoint(d)
    # Add augmented datapoint to list
    dats.append(d_augm)
# Note: The above can also be achieved using a utility function for such 'simple' cases:
# dats = msdnet.utils.load_simple_data('train/noisy/*.tiff', 'train/noiseless/*.tiff', augment=True)

# Normalize input and output of network to zero mean and unit variance using
# training data images
n.normalizeinout(dats)

# Use image batches of a single image
bprov = msdnet.data.BatchProvider(dats,1)

# Define validation data (not using augmentation)
flsin = []
flstg = []
for i in range(16, 21):
    flsin.extend(Path(path + '/walnut_{}/{}/tiffs/FDK/'.format(files[i], dset)).glob('*.tiff'))
    flstg.extend(Path(path + '/walnut_{}/{}/tiffs/GS/'.format(files[i], dset)).glob('*.tiff'))
    
  
flsin = sorted(flsin)
flstg = sorted(flstg)

datsv = []
for i in range(4, len(flsin), 8):
    d = msdnet.data.ImageFileDataPoint(str(flsin[i]),str(flstg[i]))
    datsv.append(d)
# Note: The above can also be achieved using a utility function for such 'simple' cases:
# datsv = msdnet.utils.load_simple_data('val/noisy/*.tiff', 'val/noiseless/*.tiff', augment=False)

# Validate with Mean-Squared Error
val = msdnet.validate.MSEValidation(datsv)

# Use ADAM training algorithms
t = msdnet.train.AdamAlgorithm(n)

# Log error metrics to console
consolelog = msdnet.loggers.ConsoleLogger()
# Log error metrics to file
filelog = msdnet.loggers.FileLogger('log_regr{}.txt'.format(dset))
# Log typical, worst, and best images to image files
imagelog = msdnet.loggers.ImageLogger('log_regr{}'.format(dset), onlyifbetter=True)

# Train network until program is stopped manually
# Network parameters are saved in regr_params.h5
# Validation is run after every len(datsv) (=25)
# training steps.
msdnet.train.train(n, t, val, bprov, 'regr_params{}.h5'.format(dset),
                   loggers=[consolelog,filelog,imagelog], val_every=len(datsv))

