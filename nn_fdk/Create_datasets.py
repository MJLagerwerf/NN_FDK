#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 28 14:53:22 2019

@author: lagerwer
"""
import numpy as np
import odl
import ddf_fdk as ddf
import astra
import imageio as io
import os
from tqdm import tqdm

from . import support_functions as sup
# %%
def make_hann_filt(voxels, w_detu):
    rs_detu = int(2 ** (np.ceil(np.log2(voxels[0] * 2)) + 1))
    filt = np.real(np.fft.rfft(ddf.ramp_filt(rs_detu)))
    freq = 2 * np.arange(len(filt))/(rs_detu)
    filt = filt * (np.cos(freq * np.pi / 2) ** 2)  / 2 / w_detu
#    filt = filt / 2 / w_detu
    return filt


def Create_dataset_ASTRA_sim(pix, phantom, angles, src_rad, noise, Exp_bin,
                         bin_param, **kwargs):
    if phantom == 'Defrise':
        phantom = 'Defrise random'
    if phantom == 'Fourshape_test':
        phantom = 'Fourshape'

    if 'MaxVoxDataset' in kwargs:
        MaxVoxDataset = kwargs['MaxVoxDataset']
        
    else:
        MaxVoxDataset = np.max([int(pix ** 3 * 0.005), 1 * 10 ** 6])

    # The size of the measured objects in voxels
    voxels = [pix, pix, pix]
    dpix = [voxels[0] * 2, voxels[1]]
    u, v = dpix
    # ! ! ! This will lead to some problems later on ! ! !
    det_rad = 0
    data_obj = ddf.phantom(voxels, phantom, angles, noise, src_rad, det_rad,
                           compute_xHQ=True)
    WV_obj = ddf.support_functions.working_var_map()
    WV_path = WV_obj.WV_path
    data_obj.make_mask(WV_path)
    Smat = Make_Smat(voxels, MaxVoxDataset, WV_path)
    # %% saving tiffs for CNNs
    w_du = data_obj.w_detu
    filt = make_hann_filt(voxels, w_du)
    xFDK = ddf.FDK_ODL_astra_backend.FDK_astra(data_obj.g, filt,
                                               data_obj.geometry, 
                                               data_obj.reco_space, None)

    # %% Create geometry
    # Make a circular scanning geometry
    minvox = data_obj.reco_space.min_pt[0]
    maxvox = data_obj.reco_space.max_pt[0]
    vox = np.shape(data_obj.reco_space)[0]
    vol_geom = astra.create_vol_geom(vox, vox, vox, minvox, maxvox, minvox,
                                     maxvox, minvox, maxvox)

    ang = np.linspace((1 / angles) * np.pi, (2 + 1 / angles) * np.pi, angles,
                  False)
    w_du, w_dv = 2 * data_obj.geometry.detector.partition.max_pt / [u, v]
    proj_geom = astra.create_proj_geom('cone', w_dv, w_du, v, u,
                                       ang, data_obj.geometry.src_radius,
                                       data_obj.geometry.det_radius)
    filter_part = odl.uniform_partition(-data_obj.detecsize[0],
                                        data_obj.detecsize[0], u)

    filter_space = odl.uniform_discr_frompartition(filter_part, dtype='float64')
    spf_space, Exp_op = ddf.support_functions.ExpOp_builder(bin_param,
                                                         filter_space,
                                                         interp=Exp_bin)
    nParam = np.size(spf_space)

    fullFilterSize = int(2 ** (np.ceil(np.log2(dpix[0])) + 1))
    halfFilterSize = fullFilterSize // 2 + 1

    Resize_Op = odl.ResizingOperator(Exp_op.range, ran_shp=(fullFilterSize,))
    # %% Create forward and backward projector
#    project_id = astra.create_projector('cuda3d', proj_geom, vol_geom)
#    W = astra.OpTomo(project_id)


    # %% Create data
    proj_data = np.transpose(np.asarray(data_obj.g), (2, 0, 1)).copy()
#    W.FP(np.transpose(np.asarray(data_obj.f), (2, 1, 0)))
    
    # ! ! ! wat is deze? ! ! !
    # if noise is not None:
    #     g = add_poisson_noise(proj_data, noise[1])
    # else:
    g = proj_data

    proj_id = astra.data3d.link('-sino', proj_geom, g)


    rec = np.zeros(astra.geom_size(vol_geom), dtype=np.float32)
    rec_id = astra.data3d.link('-vol', vol_geom, rec)

    B = np.zeros((MaxVoxDataset, nParam + 1))

    # %% Make the matrix columns of the matrix B
    for nP in range(nParam):
        unit_vec = spf_space.zero()
        unit_vec[nP] = 1
        filt = Exp_op(unit_vec)

        rs_filt = Resize_Op(filt)

        f_filt = np.real(np.fft.rfft(np.fft.ifftshift(rs_filt)))
        filter2d = np.zeros((angles, halfFilterSize))
        for i in range(angles):
            filter2d[i, :] = f_filt * 4 * w_du

        # %% Make a filter geometry
        filter_geom = astra.create_proj_geom('parallel', w_du,  halfFilterSize,
                                             np.zeros((angles)))

        filter_id = astra.data2d.create('-sino', filter_geom, filter2d)
        #

        cfg = astra.astra_dict('FDK_CUDA')
        cfg['ReconstructionDataId'] = rec_id
        cfg['ProjectionDataId'] = proj_id
        cfg['option'] = { 'FilterSinogramId': filter_id }
        # Create the algorithm object from the configuration structure
        alg_id = astra.algorithm.create(cfg)

        # %%
        astra.algorithm.run(alg_id)
        rec = np.transpose(rec, (2, 1, 0))
        B[:, nP] = rec[Smat]
    # %%
    # Clean up. Note that GPU memory is tied up in the algorithm object,
    # and main RAM in the data objects.
    B[:, -1] = data_obj.xHQ[Smat]
#    B[:, -1] = data_obj.f[Smat]
    astra.algorithm.delete(alg_id)
    astra.data3d.delete(rec_id)
    astra.data3d.delete(proj_id)
    return B, data_obj.xHQ, xFDK


# %%
def Create_dataset(pix, phantom, angles, src_rad, noise, Exp_bin, bin_param):
    if phantom == 'Defrise':
        phantom = 'Defrise random'
    if phantom == 'Fourshape_test':
        phantom = 'Fourshape'
    # Maximum number of voxels considered per dataset
    MaxVoxDataset = np.max([int(pix ** 3 * 0.005), 1 * 10 ** 6])

    # The size of the measured objects in voxels
    voxels = [pix, pix, pix]
    data_obj = ddf.phantom(voxels, phantom)
    det_rad = 0

    case = ddf.CCB_CT(data_obj, angles, src_rad, det_rad, noise)
    # Initialize the algorithms (FDK, SIRT)
    case.init_algo()
    # Create a binned filter space and a expansion operator
    spf_space, Exp_op = ddf.support_functions.ExpOp_builder(bin_param,
                                                         case.filter_space,
                                                         interp=Exp_bin)
    # Create FDK operator that takes binned filters
    FDK_bin_nn = case.FDK_op * Exp_op

    # Create a sampling operator
    S = SamplingOp(case.reco_space, MaxVoxDataset, case.WV_path)


    # Create the Operator related to the learning matrix
    B = S * FDK_bin_nn
    # Compute the learning matrix
    Bmat = odl.operator.oputils.matrix_representation(B)

    # Create the target data
    v_gt = np.asarray(S(case.phantom.f))
    Data = np.concatenate((Bmat, v_gt[:, None]), 1)

    return Data

# %%
class SamplingOp(odl.Operator):
    def __init__(self, dom, MaxVoxDataset, WV_path):
        # checks to make sure there is a mask?
        mask = np.load(WV_path + 'mask.npy')
        size_reco = np.size(dom)
        shape_reco = np.shape(dom)
        coords = np.arange(size_reco).reshape(shape_reco)[np.where(mask)]
        picks = list(np.random.choice(coords, size=MaxVoxDataset,
                                      replace=False))
        self.Smat = np.zeros(size_reco, dtype=bool)
        self.Smat[picks] = True
        self.Smat = self.Smat.reshape(shape_reco)
        self.size = np.sum(self.Smat)
        ran = odl.rn(self.size)
        odl.Operator.__init__(self, domain=dom, range=ran, linear=True)

    def _call(self, x):
        return x[self.Smat]
    
    
# %%
def add_poisson_noise(g, I_0, seed=None):
    seed_old = np.random.get_state()
    np.random.seed(seed=seed)
    data = g.copy()
    Iclean = (I_0 * np.exp(-data))
    data = None
    Inoise = np.random.poisson(Iclean)
    Iclean = None
    np.random.set_state(seed_old)
    return  -np.log(Inoise / I_0).astype('float32')


# %%
def Make_Smat(voxels, MaxVoxDataset, WV_path, shape='mat', **kwargs):
    if 'seed' in kwargs:
        seed_old = np.random.get_state()
        np.random.seed(seed=kwargs['seed'])
    if 'real_data' in kwargs:
        mask = np.load(kwargs['real_data'])
    else:
        mask = np.load(WV_path + 'mask.npy')
    size_reco = np.multiply.reduce(voxels)
    shape_reco = voxels
    coords = np.arange(size_reco).reshape(voxels)[np.where(mask)]
    picks = list(np.random.choice(coords, size=MaxVoxDataset,
                                  replace=False))
    Smat = np.zeros(size_reco, dtype=bool)
    Smat[picks] = True
    if shape == 'mat': 
        Smat = Smat.reshape(shape_reco)
    elif shape == 'vec':
        pass
    if 'seed' in kwargs:
        np.random.set_state(seed_old)
    return Smat

# %%
def Create_dataset_ASTRA_real(dataset, pix_size, src_rad, det_rad, ang_freq,
                         Exp_bin, bin_param, vox=None, vecs=None):
    
    # ! ! ! We overide 'vox' and 'vecs' later on
    # The size of the measured objects in voxels
    data_obj = ddf.real_data(dataset, pix_size, src_rad, det_rad, ang_freq,
                             vox=vox, vecs=vecs)
    g = np.ascontiguousarray(np.transpose(np.asarray(data_obj.g.copy()),
                                          (2, 0, 1)), dtype=np.float32)
    v, ang, u = g.shape
    if vox is None:
        voxels = data_obj.voxels
        
    else:
        voxels = [vox, vox, vox]
    

    MaxVoxDataset = np.max([int(voxels[0] ** 3 * 0.005), 5 * 10 ** 6])

    Smat = Make_Smat(voxels, MaxVoxDataset, '', real_data=dataset['mask'])


    # %% Create geometry
    geom = data_obj.geometry
    w_du = data_obj.pix_size
    dpix = [u, v]
    
    minvox = data_obj.reco_space.min_pt[0]
    maxvox = data_obj.reco_space.max_pt[0]
    vox = np.shape(data_obj.reco_space)[0]
    vol_geom = astra.create_vol_geom(vox, vox, vox, minvox, maxvox, minvox,
                                     maxvox, minvox, maxvox)


    # Build a vecs vector from the geometry, or load it
    if type(geom) == np.ndarray:
        vecs = geom
        proj_geom = astra.create_proj_geom('cone_vec', v, u, vecs)
    elif type(geom) == odl.tomo.geometry.conebeam.ConeFlatGeometry:
        angles = np.linspace((1 / ang) * np.pi, (2 + 1 / ang) * np.pi,
                          ang, False)
        w_du, w_dv = 2 * data_obj.geometry.detector.partition.max_pt / [u, v]
        proj_geom = astra.create_proj_geom('cone', w_dv, w_du, v, u,
                                           angles, data_obj.geometry.src_radius,
                                           data_obj.geometry.det_radius)
    
    
    
    filter_part = odl.uniform_partition(-data_obj.detecsize[0],
                                        data_obj.detecsize[0], dpix[0])

    filter_space = odl.uniform_discr_frompartition(filter_part,
                                                   dtype='float64')
    spf_space, Exp_op = ddf.ExpOp_builder(bin_param, filter_space,
                                                        interp=Exp_bin)

    nParam = np.size(spf_space)

    fullFilterSize = int(2 ** (np.ceil(np.log2(dpix[0])) + 1))
    halfFilterSize = fullFilterSize // 2 + 1

    Resize_Op = odl.ResizingOperator(Exp_op.range, ran_shp=(fullFilterSize,))
    # %% Create projection and reconstion objects
    proj_id = astra.data3d.link('-proj3d', proj_geom, g)

    rec = np.zeros(astra.geom_size(vol_geom), dtype=np.float32)
    rec_id = astra.data3d.link('-vol', vol_geom, rec)

    B = np.zeros((MaxVoxDataset, nParam + 1))

    # %% Make the matrix columns of the matrix B
    for nP in range(nParam):
        unit_vec = spf_space.zero()
        unit_vec[nP] = 1
        filt = Exp_op(unit_vec)

        rs_filt = Resize_Op(filt)

        f_filt = np.real(np.fft.rfft(np.fft.ifftshift(rs_filt)))
        filter2d = np.zeros((ang, halfFilterSize))
        for i in range(ang):
            filter2d[i, :] = f_filt * 4 * w_du

        # %% Make a filter geometry
        filter_geom = astra.create_proj_geom('parallel', w_du,  halfFilterSize,
                                             np.zeros(ang))
        filter_id = astra.data2d.create('-sino', filter_geom, filter2d)
        #

        cfg = astra.astra_dict('FDK_CUDA')
        cfg['ReconstructionDataId'] = rec_id
        cfg['ProjectionDataId'] = proj_id
        cfg['option'] = { 'FilterSinogramId': filter_id }
        # Create the algorithm object from the configuration structure
        alg_id = astra.algorithm.create(cfg)

        # %%
        astra.algorithm.run(alg_id)
        rec = np.transpose(rec, (2, 1, 0))
        B[:, nP] = rec[Smat]
    # %%
    # Clean up. Note that GPU memory is tied up in the algorithm object,
    # and main RAM in the data objects.
    B[:, -1] = data_obj.f[Smat]
    astra.algorithm.delete(alg_id)
    astra.data3d.delete(rec_id)
    astra.data3d.delete(proj_id)
    return B