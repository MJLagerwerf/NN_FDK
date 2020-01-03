#!/usr/bin/bash
# limit numper of OpenMP threads
# export OMP_NUM_THREADS=16
# set astra gpu index: 0-3
# export CUDA_VISIBLE_DEVICES=0,1


for i in {0..4}
do
    python SV_var.py -p -F \
    /export/scratch2/lagerwer/NNFDK_results/SV_var_1024 with it_i=$i pix=1024 nTD=1 nVD=0
done

for i in {0..5}
do
    python NOI_var.py -p -F \
    /export/scratch2/lagerwer/NNFDK_results/NOI_var_1024 with it_i=$i pix=1024 nTD=1 nVD=0
done

for i in 2 3 5 7.5 10
do
    python exp_cone_angle.py -p with src_rad=$i pix=1024 nTD=1 nVD=0
done
