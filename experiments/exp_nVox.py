#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Aug 15 10:33:37 2019

@author: lagerwer
"""

import numpy as np
import ddf_fdk as ddf
ddf.import_astra_GPU()
import nn_fdk as nn
import h5py
import time
import pylab
import os
import gc

from sacred.observers import FileStorageObserver
from sacred import Experiment
from os import environ
name_exp = 'nVox'
ex = Experiment(name_exp, ingredients=[])

FSpath = '/export/scratch2/lagerwer/NNFDK_results/' + name_exp
ex.observers.append(FileStorageObserver.create(FSpath))
#url=mongo_url, db_name='sacred'))
# %%
@ex.config
def cfg():
    it_i = 1
    it_j = 0
    pix = 256
    # Specific phantom
    phantom = 'Fourshape_test'
    # Number of angles
    angles = 16
    # Source radius
    src_rad = 10
    # Noise specifics
    I0 = 2 ** 10
    noise = None #['Poisson', I0]
    
    # Load data?
    f_load_path = None
    g_load_path = None
    # Should we retrain the networks?
    retrain = True
    # Total number of voxels used for training
    nVox = [1e4, 1e5, 1e6, 1e7, 1e8]
    nD = 10
    # Number of voxels used for training, number of datasets used for training
    nTrain = nVox[it_i]
    nTD = nD
    # Number of voxels used for validation, number of datasets used for validation
    nVal = nVox[it_i]
    nVD = nD
    nNodes = 4
    nTests = 10
    bpath = '/export/scratch3/lagerwer/data/NNFDK/'

    # Specifics for the expansion operator
    Exp_bin = 'linear'
    bin_param = 2
    specifics = 'nVox{:.0f}'.format(nVox[it_i])
    filts = ['Hann']

# %%
@ex.capture
def create_datasets(pix, phantom, angles, src_rad, noise, nTD, nVD, Exp_bin,
                    bin_param, nTests, bpath):
    nn.Create_TrainingValidationData(pix, phantom, angles, src_rad, noise,
                                 Exp_bin, bin_param, nTD + nVD, 
                                 base_path=bpath)

        
@ex.capture
def CT(pix, phantom, angles, src_rad, noise, nTrain, nTD, nVal, nVD,
              Exp_bin, bin_param, f_load_path, g_load_path, bpath):
    
    voxels = [pix, pix, pix]
    det_rad = 0
    if g_load_path is not None:
        if f_load_path is not None:
            data_obj = ddf.phantom(voxels, phantom, angles, noise, src_rad,
                                   det_rad, load_data_g=g_load_path,
                                   load_data_f=f_load_path)
        else:
            data_obj = ddf.phantom(voxels, phantom, angles, noise, src_rad,
                               det_rad, load_data_g=g_load_path)
            
    else:
        data_obj = ddf.phantom(voxels, phantom, angles, noise, src_rad,
                                   det_rad)

    CT_obj = ddf.CCB_CT(data_obj)
    CT_obj.init_algo()
    spf_space, Exp_op = ddf.support_functions.ExpOp_builder(bin_param,
                                                         CT_obj.filter_space,
                                                         interp=Exp_bin)
    # Create the FDK binned operator
#    CT_obj.FDK_bin_nn = CT_obj.FDK_op * Exp_op

    # Create the NN-FDK object
    CT_obj.NNFDK = nn.NNFDK_class(CT_obj, nTrain, nTD, nVal, nVD, Exp_bin,
                                   Exp_op, bin_param, base_path=bpath)
    CT_obj.rec_methods += [CT_obj.NNFDK]
    return CT_obj

# %%
@ex.capture
def make_map_path(pix, phantom, angles, src_rad, noise, nTrain, nTD, nVal, nVD,
              Exp_bin, bin_param, bpath):
    data_path, full_path = nn.make_map_path(pix, phantom, angles, src_rad,
                                             noise, nTrain, nTD, nVal, nVD,
                                             Exp_bin, bin_param, bpath)
    return data_path, full_path

@ex.capture
def save_and_add_artifact(path, arr):
    np.save(path, arr)
    ex.add_artifact(path)

@ex.capture
def save_network(case, full_path, NW_path):
    NW_full = h5py.File(full_path + NW_path, 'r')
    NW = h5py.File(case.WV_path + NW_path, 'w')

    NW_full.copy(str(case.NNFDK.network[-1]['nNW']), NW, name='NW')
    NW_full.close()
    NW.close()
    ex.add_artifact(case.WV_path + NW_path)
    
@ex.capture
def save_table(case, WV_path):
    case.table()
    latex_table = open(WV_path + '_latex_table.txt', 'w')
    latex_table.write(case.table_latex)
    latex_table.close()
    ex.add_artifact(WV_path + '_latex_table.txt')

@ex.capture
def log_variables(results, Q, RT):
    Q = np.append(Q, results.Q, axis=0)
    RT = np.append(RT, results.rec_time)
    return Q, RT
    
# %%
@ex.automain
def main(it_i, retrain, nNodes, nTests, nD, filts, specifics):
    t = time.time()
    Q = np.zeros((0, 3))
    RT = np.zeros((0))
    
    create_datasets()
    # Create a test dataset
    t0 = time.time()
    print('It took', (t0 - t) / 60, 'minutes to finish creating the datasets')
    
    if it_i == 0:
        case = CT()
    else:
        case = CT(g_load_path=f"{FSpath}/1/nVox10000_g.npy")
    # Create the paths where the objects are saved
    data_path, full_path = make_map_path()
    WV_path = case.WV_path + specifics
    save_and_add_artifact(WV_path + '_g.npy', case.g)

    t1 = time.time()
    print('Finished setting up the inverse problem. Took:', (t1 - t0) / 60,
          'minutes')

    TT = np.zeros(nTests)
    for i in range(nTests):
        case.NNFDK.train(nNodes, name='_' + str(i), retrain=retrain)
        TT[i] = case.NNFDK.train_time
        save_network(case, full_path, 'network_' + str(nNodes) + '_' + str(i) +
                     '.hdf5')
        
        case.NNFDK.do()
        save_and_add_artifact(WV_path + '_NNFDK'+  str(nNodes) + '_' + str(i) + 
                               '_rec.npy', case.NNFDK.results.rec_axis[-1])
    

    save_and_add_artifact(WV_path + '_TT.npy', TT)
    Q, RT = log_variables(case.NNFDK.results, Q, RT)
    
    save_and_add_artifact(WV_path + '_Q.npy', Q)
    save_and_add_artifact(WV_path + '_RT.npy', RT)
    t2 = time.time()
    print('Finished NNFDKs. Took:', (t2 - t1) / 60, 'minutes')
    save_table(case, WV_path)

    
    case = None
    gc.collect()
    return Q

