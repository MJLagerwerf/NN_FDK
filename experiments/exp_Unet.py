#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 26 13:13:20 2019

@author: lagerwer
"""

import numpy as np
import ddf_fdk as ddf
import nn_fdk as nn
import time
import pylab
t = time.time()

ddf.import_astra_GPU()
from sacred.observers import FileStorageObserver
from sacred import Experiment
from os import environ
name_exp = 'Unet'
ex = Experiment(name_exp, ingredients=[])

FSpath = '/export/scratch2/lagerwer/NNFDK_results/' + name_exp
ex.observers.append(FileStorageObserver.create(FSpath))

# %%
@ex.config
def cfg():
    phantom = 'Fourshape_test'
    nTD = 1
    nVD = None
    epochs = 1000
# %%
    
@ex.automain
def main(phantom, nTD, nVD, train, epochs):
    pix = 1024
    # Specific phantom
    
    if phantom == 'Fourshape_test':
        PH = '4S'
        src_rad = 10
        noise = ['Poisson', 2 ** 8]
    elif phantom == 'Defrise':
        PH = 'DF'
        src_rad = 2
        noise = None
    
    # Number of angles
    angles = 360
    # Source radius
    det_rad = 0
    # Noise specifics
    
    # Number of voxels used for training, number of datasets used for training
    nTrain = 1e6
    # Number of voxels used for validation, number of datasets used for validation
    nVal = 1e6
    
    # Specifics for the expansion operator
    Exp_bin = 'linear'
    bin_param = 2
    bpath = '/bigstore/lagerwer/data/NNFDK/'
    
    NL

    # %%
    t1 = time.time()
    nn.Create_TrainingValidationData(pix, phantom, angles, src_rad, noise,
                                     Exp_bin, bin_param, nTD + nVD,
                                     base_path=bpath)
    print('Creating training and validation datasets took', time.time() - t1,
          'seconds')
    
    # %% Create a test phantom
    voxels = [pix, pix, pix]
    # Create a data object
    t2 = time.time()
    data_obj = ddf.phantom(voxels, phantom, angles, noise, src_rad, det_rad)#,
    #                       compute_xHQ=True)
    print('Making phantom and mask took', time.time() -t2, 'seconds')
    # The amount of projection angles in the measurements
    # Source to center of rotation radius
    
    t3 = time.time()
    # %% Create the circular cone beam CT class
    case = ddf.CCB_CT(data_obj)#, angles, src_rad, det_rad, noise)
    print('Making data and operators took', time.time()-t3, 'seconds')
    # Initialize the algorithms (FDK, SIRT)
    t4 = time.time()
    case.init_algo()
    
    # %% Create NN-FDK algorithm setup
    # Create binned filter space and expansion operator
    spf_space, Exp_op = ddf.support_functions.ExpOp_builder(bin_param,
                                                    NL
     case.filter_space,
                                                         interp=Exp_bin)
    # Create the FDK binned operator
    case.FDK_bin_nn = case.FDK_op * Exp_op
    
    # Create the NN-FDK object
    case.NNFDK = nn.NNFDK_class(case, nTrain, nTD, nVal, nVD, Exp_bin, Exp_op,
                                 bin_param, base_path=bpath)
    case.rec_methods += [case.NNFDK]
    print('Initializing algorithms took', time.time() - t4, 'seconds')
    
    # %%

    case.FDK.do('Hann')
    case.NNFDK.train(4)
    case.NNFDK.do()
    # %%
    case.Unet = nn.Unet_class(case, case.NNFDK.data_path)
    case.rec_methods += [case.Unet]
    
    l_tr, l_v = nn.Preprocess_datasets.random_lists(nTD, nVD)

    list_tr = list(l_tr)
    
    print('training')
    case.Unet.train(list_tr, epochs=epochs)
    
    case.Unet.do()
    # %%
    print('MSD rec time:', case.MSD.results.rec_time[0])
    print('NNFDK rec time:', case.NNFDK.results.rec_time[0])
    print('FDK rec time:', case.FDK.results.rec_time[0])
    # %%
    save_path = '/bigstore/lagerwer/NNFDK_results/figures/'
    pylab.close('all')
    case.table()
    case.show_phantom()
    case.Unet.show(save_name=f'{save_path}Unet_{PH}_nTD{nTD}_nVD{nVD}')
    case.NNFDK.show(save_name=f'{save_path}NNFDK_{PH}_nTD{nTD}_nVD{nVD}')
    case.FDK.show(save_name=f'{save_path}FDK_{PH}_nTD{nTD}_nVD{nVD}')
    return    