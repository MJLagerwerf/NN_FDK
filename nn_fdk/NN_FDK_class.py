#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 28 14:51:44 2019

@author: lagerwer
"""


import numpy as np
import ddf_fdk as ddf
import os
import gc
import h5py
import numexpr
import pylab
import time

from . import Network_class as N
from . import TrainingData_class as TDC
from . import NNFDK_astra_backend as NNFDK_astra
from . import support_functions as sup
from . import Preprocess_datasets as PD
# %%
def sigmoid(x):
    '''Sigmoid function'''
    return numexpr.evaluate("1./(1.+exp(-x))")
def hidden_layer(x, y, q, b):
    ''' Perceptron hidden layer'''
    return numexpr.evaluate('y + q * (1 / (1 + exp(-(x - b))))')

def outer_layer(x, b, sc2_1, sc2_2):
    ''' Outer layer'''
    return numexpr.evaluate('2 * (1 / (1 + exp(-(x - b))) - .25) * sc2_1' \
                            '+ sc2_2')
    
# %%
def load_network(path):
    f = h5py.File(path + '.hdf5', 'r')
    l1 = np.asarray(f['l1'])
    l2 = np.asarray(f['l2'])
    sc1 = np.asarray(f['sc1'])
    sc2 = np.asarray(f['sc2'])
    
    f.close()
    return {'l1' : l1, 'l2' : l2, 'sc1' : sc1, 'sc2' : sc2, 'nNodes': 4}
    

# %%
def train_network(nHiddenNodes, nTD, nVD, full_path, name='', retrain=False,
                  save_model_pb=False,
                  **kwargs):
    # Set a path to save the network
    fnNetwork = full_path + 'network_' + str(nHiddenNodes) + name
    # Check how many TD and VD datasets we have
    TD_dn = 'TD'
    VD_dn = 'VD'
    if 'd_fls' in kwargs:
        TD_fls = [full_path + TD_dn + str(i) for i in kwargs['d_fls'][0]] 
        VD_fls = [full_path + VD_dn + str(i) for i in kwargs['d_fls'][1]]
    else:
        TD_fls = [full_path + TD_dn + str(i) for i in range(nTD)]
        if nVD == 0:
            VD_fls = [full_path + VD_dn + str(i) for i in range(nTD)]
        else:
            VD_fls = [full_path + VD_dn + str(i) for i in range(nVD)]
    
    # Open hdf5 file for your network
    # Check if we already have a network trained for this number of nodes
    if os.path.exists(fnNetwork + '.hdf5'):
        f = h5py.File(fnNetwork + '.hdf5', 'r+')
        # Check at which network we are
        nNWs = 1
        while str(nNWs) in f:
            nNWs += 1
        if retrain:
            nNetworks = str(nNWs) + '/'
            f.create_group(nNetworks)
        else:
            nn = str(nNWs - 1) + '/'
            # load old network, get them in numpy arrays
            # TODO: Also load the list of training and validation error
            l1 = np.asarray(f[nn + 'l1'])
            l2 = np.asarray(f[nn + 'l2'])
            sc1 = np.asarray(f[nn + 'sc1'])
            sc2 = np.asarray(f[nn + 'sc2'])
            l_tE = np.asarray(f[nn + 'l_tE']) 
            l_vE = np.asarray(f[nn + 'l_vE'])
            # return old network
            print('Loaded old network, network has', str(nHiddenNodes),
                  'hidden nodes')
            f.close()

            return {'l1' : l1, 'l2' : l2, 'sc1' : sc1, 'sc2' : sc2,
                    'nNodes' : nHiddenNodes, 'nNW' : nNWs - 1, 
                    'l_tE' : l_tE, 'l_vE' : l_vE}

    # We have no network trained with this number of nodes
    else:
        # Create a hdf5 file for networks with this number of nodes
        f = h5py.File(fnNetwork + '.hdf5', 'w')
        f.attrs['nNodes'] = nHiddenNodes
        nNetworks = str(1) + '/'
        f.create_group(nNetworks)
        nNWs = 1

    
    # Put everything a the correct classes
    trainData = TDC.MATTrainingData(TD_fls, dataname=TD_dn)
    valData = TDC.MATTrainingData(VD_fls, dataname=VD_dn)
    NW_obj = N.Network(nHiddenNodes, trainData, valData)
    # Train a network
    print('Training new network, network has', str(nHiddenNodes),
      'hidden nodes')
    NW_obj.train(save_model_pb)

    # Save the number of datasets used for training/validation
    f[nNetworks].attrs['nTD'] = nTD
    f[nNetworks].attrs['nVD'] = nVD
    # Save the training MSE and validation MSE
    f[nNetworks].attrs['T_MSE'] = NW_obj.trErr
    f[nNetworks].attrs['V_MSE'] = NW_obj.valErr
    # Save the network parameters
    f.create_dataset(nNetworks + 'l1', data=NW_obj.l1)
    f.create_dataset(nNetworks + 'l2', data=NW_obj.l2)
    # Fix the scaling operators
    sc1 = 1 / (NW_obj.minmax[1] - NW_obj.minmax[0])
    sc1 = np.concatenate(([sc1,], [NW_obj.minmax[0] * sc1,]), 0)
    sc2 = np.array([NW_obj.minmax[3] - NW_obj.minmax[2], NW_obj.minmax[2]])
    lst_valError = NW_obj.lst_valError
    lst_traError = NW_obj.lst_traError
    f.create_dataset(nNetworks + 'l_vE', data=lst_valError)
    f.create_dataset(nNetworks + 'l_tE', data=lst_traError)
    # Save the scaling operators
    f.create_dataset(nNetworks + 'sc1', data=sc1)
    f.create_dataset(nNetworks + 'sc2', data=sc2)
    f.close()
    del trainData.normalized, valData.normalized
    gc.collect()
    for it in range(nTD):
        os.remove(trainData.fn[it])
    for iv in range(nVD):
        os.remove(valData.fn[iv])
    return {'l1' : NW_obj.l1, 'l2' : NW_obj.l2, 'sc1' : sc1, 'sc2' : sc2,
            'nNodes' : nHiddenNodes, 'nNW' : nNWs, 'l_vE' : lst_valError,
            'l_tE': lst_traError}

# %%

class NNFDK_class(ddf.algorithm_class.algorithm_class):
    def __init__(self, CT_obj, nTrain, nTD, nVal, nVD, Exp_bin, Exp_op,
                 bin_param, dset=None,
                 base_path='/export/scratch2/lagerwer/data/NNFDK/'):
        self.CT_obj = CT_obj
        self.method = 'NN-FDK'
        self.Exp_bin = Exp_bin
        self.Exp_op = Exp_op
        self.bin_param = bin_param
        self.nTrain = nTrain
        self.nTD = nTD
        self.nVal = nVal
        self.nVD = nVD
        self.dset = dset
        self.base_path = base_path
        if self.CT_obj.phantom.data_type == 'simulated':
            self.data_path, self.full_path = sup.make_map_path(self.CT_obj.pix,
                                                     self.CT_obj.phantom.PH,
                                                     self.CT_obj.angles,
                                                     self.CT_obj.src_rad,
                                                     self.CT_obj.noise,
                                                     self.nTrain, self.nTD,
                                                     self.nVal, self.nVD,
                                                     self.Exp_bin,
                                                     self.bin_param,
                                                     base_path=self.base_path)
        else:
            self.data_path, self.full_path = sup.make_map_path_RD(self.dset,
                                                self.CT_obj.phantom.ang_freq,
                                                self.nTrain, self.nTD,
                                                self.nVal, self.nVD,
                                                base_path=self.base_path)


    def train(self, nHiddenNodes, name='', retrain=False, DS_list=False, 
              preprocess=True, save_model_pb=False, **kwargs):
        tt = time.time()
        if preprocess:
            PD.Preprocess_Data(self.CT_obj.pix, self.data_path, self.nTrain,
                               self.nTD, self.nVal, self.nVD, DS_list=DS_list,
                               **kwargs)

        t = time.time()
        print('It took', t - tt, 'seconds to preprocess the data')
        if hasattr(self, 'network'):
            self.network += [train_network(nHiddenNodes, self.nTD, self.nVD,
                                           self.full_path, name, retrain,
                                           save_model_pb,
                                           **kwargs)]
        else:
            self.network = [train_network(nHiddenNodes, self.nTD, self.nVD,
                                          self.full_path, name, retrain,
                                          save_model_pb,
                                          **kwargs)]
        self.train_time = time.time() - t

    def do(self, node_output=False, nwNumber=-1, compute_results=True,
           measures=['MSE', 'MAE', 'SSIM'], astra=True, NW_path=None):
        t = time.time()
        if NW_path is None:
            NW = self.network[nwNumber] # To improve readability
        else:
            NW = load_network(NW_path)
        if astra:
            if node_output:
                rec, h_e, self.node_out_axis = NNFDK_astra.NNFDK_astra(
                                                self.CT_obj.g, NW,
                                                self.CT_obj.geometry,
                                                self.CT_obj.reco_space,
                                                self.CT_obj.w_detu,
                                                self.Exp_op, node_output)
            else:
                rec, h_e, = NNFDK_astra.NNFDK_astra(self.CT_obj.g, NW,
                                                    self.CT_obj.geometry,
                                                    self.CT_obj.reco_space,
                                                    self.CT_obj.w_detu,
                                                    self.Exp_op, node_output)
        else:
            # Take the network requested
            F = self.CT_obj.reco_space.zero()
            mid = np.size(F, 0) // 2
            # Set a container list for the learned filters
            h_e = []
            if node_output:
                self.node_out_axis = []
            for i in range(NW['nNodes']):
                # h_i = self.network['l1'][:-1, i], b_i = self.network['l1'][-1, i]
                h = NW['l1'][:-1, i] * 2 * NW['sc1'][0, :]
                h_e += [h]
                b = NW['l1'][-1, i] + np.sum(NW['l1'][:-1, i]) + 2 * np.dot(
                                NW['l1'][:-1, i], NW['sc1'][1, :])
                # q_i = self.network['l2'][i]
                FDK = self.CT_obj.FDK_bin_nn(h)
                F = hidden_layer(FDK, F, NW['l2'][i], b)
                if node_output:
                    FDK = hidden_layer(FDK, 0, NW['l2'][i], b)
                    self.node_out_axis += [[FDK[:, :, mid], FDK[:, mid, :],
                                           FDK[mid, :, :]]]
            # Make a numpy array of the filter list
            h_e = np.asarray(h_e)
            # b_o = self.network['l2'][-1]
            rec = outer_layer(F, NW['l2'][-1], NW['sc2'][0], NW['sc2'][1])
        t_rec = time.time() - t
        if compute_results:
            self.comp_results(rec, measures, h_e,
                              'HiddenNodes' + str(NW['nNodes']), t_rec)
        else:
            return rec

    def show_filters(self, nwNumber=-1, fontsize=30):
        h_e = self.results.var[nwNumber]
        fig = pylab.figure(figsize=[15, 13])
        for i in range(self.network[nwNumber]['nNodes']):
            h = self.Exp_op(h_e[i, :])
            hf = np.real(np.asarray(self.CT_obj.pd_FFT(h)))
            pylab.plot(hf, label='Node ' + str(i), lw=3)

        pylab.title('Fourier transformed filter', fontsize=fontsize)
        pylab.ylabel('$\hat{h}(\omega)$', fontsize=fontsize)
        pylab.xlabel('$\omega$', fontsize=fontsize)
        fig.show()

    # ! ! ! only can show the output of the last one ! ! !
    def show_node_output(self, nwNumber=-1, clim=None, fontsize=20):
        if not hasattr(self, 'node_out_axis'):
            raise ValueError('Did not save the node output, redo the ' + \
                             'reconstruction with node_output=True.')
        space = self.CT_obj.reco_space
        for i in range(self.network[nwNumber]['nNodes']):
            xy = self.node_out_axis[3 * i]
            xz = self.node_out_axis[3 * i + 1]
            yz = self.node_out_axis[3 * i + 2]
            fig, (ax1, ax2, ax3) = pylab.subplots(1, 3, figsize=[20, 6])
            fig.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.1)
            ima = ax1.imshow(np.rot90(xy), clim=clim, extent=[space.min_pt[0],
                             space.max_pt[0],space.min_pt[1], space.max_pt[1]])
            fig.colorbar(ima, ax=(ax1))
            ax1.set_xticks([],[])
            ax1.set_yticks([],[])
            ax1.set_xlabel('x', fontsize=fontsize)
            ax1.set_ylabel('y', fontsize=fontsize)
            ima = ax2.imshow(np.rot90(xz), clim=clim, extent=[space.min_pt[0],
                             space.max_pt[0],space.min_pt[2], space.max_pt[2]])
            fig.colorbar(ima, ax=(ax2))
            ax2.set_xticks([],[])
            ax2.set_yticks([],[])
            ax2.set_xlabel('x', fontsize=fontsize)
            ax2.set_ylabel('z', fontsize=fontsize)
            ima = ax3.imshow(np.rot90(yz), clim=clim, extent=[space.min_pt[1],
                             space.max_pt[1],space.min_pt[2], space.max_pt[2]])
            ax3.set_xlabel('y', fontsize=fontsize)
            ax3.set_ylabel('z', fontsize=fontsize)
            ax3.set_xticks([],[])
            ax3.set_yticks([],[])
            fig.colorbar(ima, ax=(ax3))
    
            fig.suptitle('Output of node ' + str(i), fontsize=fontsize+2)
            fig.show()


    def show_TrVaErr(self, nwNumber=-1):
        print('{:20}'.format('Training error: ') + '{:.4e}'.format(
                self.network[nwNumber]['l_tE'][-1]))
        print('{:20}'.format('Validation error: ') + '{:.4e}'.format(
                self.network[nwNumber]['l_vE'][-1]))
