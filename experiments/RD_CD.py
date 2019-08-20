#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu May  9 15:02:43 2019

@author: lagerwer
"""

from sacred import Experiment
from sacred.observers import FileStorageObserver
import numpy as np
import ddf_fdk as ddf
import nn_fdk as nn
import time


# %%
ex = Experiment()

@ex.config
def cfg():
    dsets = 'tubeV2'
    path = '/export/scratch2/lagerwer/data/FleXray/Walnuts/'
    sc = 1
    Exp_bin = 'linear'
    bin_param = 2
    it_i = 18


# %%
@ex.capture
def load_and_preprocess(path, dset, sc, redo):
    dataset = ddf.load_and_preprocess_real_data(path, dset, sc, redo=redo)
    meta = ddf.load_meta(path + dset + '/', sc)
    return dataset, meta

@ex.capture
def Create_dataset(dataset, meta, ang_freq, Exp_bin, bin_param):
    pix_size = meta['pix_size']
    src_rad = meta['s2o']
    det_rad = meta['o2d']   
    return nn.Create_dataset_ASTRA_real(dataset, pix_size, src_rad, det_rad, 
                              ang_freq, Exp_bin, bin_param)
    
# %%
@ex.automain
def main(it_i, path, dsets, ang_freqs, sc):

    case = f'Walnut{it_i}/'

    if sc == 1:
        scaling = ''
    else:
        scaling = '_sc' + str(sc)
            
#     Do the low dose case
    t = time.time()
    ang_freq = 1
    dataset, meta = load_and_preprocess(path + case, dsets[1], redo=False)
    B = Create_dataset(dataset, meta, ang_freq)
    save_path = f'{path}NNFDK/{dsets}{scaling}'
    np.save(f'{save_path}/Dataset{it_i-1}', B)
    print(f'Finished creating Dataset{it_i-1}_{dsets}{scaling}',
          time.time() - t, 'seconds')

    return case

