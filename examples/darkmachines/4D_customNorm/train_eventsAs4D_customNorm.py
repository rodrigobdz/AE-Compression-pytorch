import sys
BIN = '/afs/cern.ch/work/h/hgupta/public/'
sys.path.append(BIN + 'AE-Compression-pytorch/')
import os.path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pickle
import time
import datetime

import torch
import torch.nn as nn
import torch.utils.data

from torch.utils.data import TensorDataset
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from fastai.callbacks.tracker import SaveModelCallback

import fastai
from fastai import train as tr
from fastai import basic_train, basic_data
from fastai.callbacks import ActivationStats
from fastai import data_block, basic_train, basic_data

from HEPAutoencoders.utils import plot_activations
from HEPAutoencoders.nn_utils import get_data, RMSELoss
from HEPAutoencoders.nn_utils import AE_basic, AE_bn, AE_LeakyReLU, AE_bn_LeakyReLU, AE_big, AE_3D_50, AE_3D_50_bn_drop, AE_3D_50cone, AE_3D_100, AE_3D_100_bn_drop, AE_3D_100cone_bn_drop, AE_3D_200, AE_3D_200_bn_drop, AE_3D_500cone_bn, AE_3D_500cone_bn

import matplotlib as mpl

bs = 8192

if torch.cuda.is_available():
    fastai.torch_core.defaults.device = 'cuda'
    print('Using GPU for training')

save_dict = {}

#filename = BIN + 'phenoML/datasets/processed_njets_10fb.pkl'
#data = pd.read_pickle(filename)
#train, test = train_test_split(data, test_size=0.2, random_state=41)
#train.to_pickle('/afs/cern.ch/work/h/hgupta/public/phenoML/datasets/processed_njets_10fb_train.pkl')
#test.to_pickle('/afs/cern.ch/work/h/hgupta/public/phenoML/datasets/processed_njets_10fb_test.pkl')

train = pd.read_pickle('/afs/cern.ch/work/h/hgupta/public/dark_machines/processed_4D_chan2a_all_events_all_particles_4D_train.pkl')
test = pd.read_pickle('/afs/cern.ch/work/h/hgupta/public/dark_machines/processed_4D_chan2a_all_events_all_particles_4D_test.pkl')

# Basic pre-processing
#train = train.drop(columns='njets')
#test = test.drop(columns='njets')
train = train.astype('float32')
test = test.astype('float32')

# Standard normalise the data
# variables = train.keys()
# x = train[variables].values
# x_scaled = StandardScaler().fit_transform(x)
# train[variables] = x_scaled

# Custom normalization
train['E'] = train['E'] / 1000.0
train['pt'] = train['pt'] / 1000.0
test['E'] = test['E'] / 1000.0
test['pt'] = test['pt'] / 1000.0

train['eta'] = train['eta'] / 5
train['phi'] = train['phi'] / 3
train['E'] = np.log10(train['E']) 
train['pt'] = np.log10(train['pt'])

test['eta'] = test['eta'] / 5
test['phi'] = test['phi'] / 3
test['E'] = np.log10(test['E']) 
test['pt'] = np.log10(test['pt'])

# x = test[variables].values
# x_scaled = StandardScaler().fit_transform(x)
# test[variables] = x_scaled

# Create TensorDatasets
train_ds = TensorDataset(torch.tensor(train.values, dtype=torch.float), torch.tensor(train.values, dtype=torch.float))
valid_ds = TensorDataset(torch.tensor(test.values, dtype=torch.float), torch.tensor(test.values, dtype=torch.float))

# Create DataLoaders
train_dl, valid_dl = get_data(train_ds, valid_ds, bs=bs)

# Return DataBunch
db = basic_data.DataBunch(train_dl, valid_dl)

loss_func = nn.MSELoss()

bn_wd = False  # Don't use weight decay for batchnorm layers
true_wd = True  # wd will be used for all optimizers

def train_model(model, epochs, lr, wd, module_string, ct, path):
    plt.close('all')
    learn = basic_train.Learner(data=db, model=model, loss_func=loss_func, wd=wd, callback_fns=ActivationStats, bn_wd=bn_wd, true_wd=true_wd)
    start = time.perf_counter()
    if ct:
        learn.load(path)
        print('Model loaded: ', path)
    learn.fit_one_cycle(epochs, max_lr=lr, wd=wd, callbacks=[SaveModelCallback(learn, every='improvement', monitor='valid_loss', name='best_%s_bs%s_lr%.0e_wd%.0e' % (module_string, bs, lr, wd))])
    end = time.perf_counter()
    delta_t = end - start
    return learn, delta_t


def get_mod_folder(module_string, lr, pp, wd):
    if pp is None:
        curr_mod_folder = '%s_bs%d_lr%.0e_wd%.0e_ppNA/' % (module_string, bs, lr, wd)
    else:
        curr_mod_folder = '%s_bs%d_lr%.0e_wd%.0e_p%.0e/' % (module_string, bs, lr, wd, pp)
    return curr_mod_folder


def save_plots(learn, module_string, lr, wd, pp):
    # Make and save figures
    curr_mod_folder = get_mod_folder(module_string, lr, pp, wd)
    curr_save_folder = curr_mod_folder
    if not os.path.exists(curr_save_folder):
        os.mkdir(curr_save_folder)

    # Plot losses
    batches = len(learn.recorder.losses)
    epos = len(learn.recorder.val_losses)
    val_iter = (batches / epos) * np.arange(1, epos + 1, 1)
    loss_name = str(loss_func).split("(")[0]
    plt.figure()
    plt.plot(learn.recorder.losses, label='Train')
    plt.plot(val_iter, learn.recorder.val_losses, label='Validation', color='orange')
    plt.yscale(value='log')
    plt.legend()
    plt.ylabel(loss_name)
    plt.xlabel('Batches processed')
    fig_name = 'losses'
    plt.savefig(curr_save_folder + fig_name)
    plt.figure()
    plt.plot(learn.recorder.val_losses, label='Validation', color='orange')
    plt.title('Validation loss')
    plt.legend()
    plt.ylabel(loss_name)
    plt.yscale('log')
    plt.xlabel('Epoch')
    # for i_val, val in enumerate(learn.recorder.val_losses):
    #     plt.text(i_val, val, str(val), horizontalalignment='center')
    fig_name = 'losses_val'
    plt.savefig(curr_save_folder + fig_name + '.png')
    with open(curr_save_folder + 'losses.txt', 'w') as f:
        for i_val, val in enumerate(learn.recorder.val_losses):
            f.write('Epoch %d    Validation %s: %e    Training %s: %e\n' % (i_val, loss_name, val, loss_name, learn.recorder.losses[(i_val + 1) * (int(batches / epos - 1))]))
   
    return curr_mod_folder


def train_and_save(model, epochs, lr, wd, pp, module_string, save_dict, ct, path):
    if pp is None:
        curr_param_string = 'bs%d_lr%.0e_wd%.0e_ppNA' % (bs, lr, wd)
    else:
        curr_param_string = 'bs%d_lr%.0e_wd%.0e_pp%.0e' % (bs, lr, wd, pp)

    learn, delta_t = train_model(model, epochs=epochs, lr=lr, wd=wd, module_string=module_string, ct=ct, path=path)
    time_string = str(datetime.timedelta(seconds=delta_t))
    curr_mod_folder = save_plots(learn, module_string, lr, wd, pp)

    val_losses = learn.recorder.val_losses
    train_losses = learn.recorder.losses
    min_val_loss = np.min(val_losses)
    min_epoch = np.argmin(val_losses)

    save_dict[module_string].update({curr_param_string: {}})
    save_dict[module_string][curr_param_string].update({'val_losses': val_losses, 'train_losses': train_losses, 'hyper_parameter_names': [
        'bs', 'lr', 'wd', 'pp'], 'hyper_parameters': [bs, lr, wd, pp], 'training_time_seconds': delta_t})
    curr_save_folder = get_mod_folder(module_string, lr, pp, wd)
    with open(curr_save_folder + 'save_dict%s.pkl' % curr_param_string, 'wb') as f:
        pickle.dump(save_dict, f, protocol=pickle.HIGHEST_PROTOCOL)
    learn.save(curr_mod_folder.split('/')[0])
    with open(curr_save_folder + 'summary.txt', 'w') as f:
        f.write('%s Minimum validation loss: %e epoch: %d lr: %.1e wd: %.1e p: %s Training time: %s\n' % (module_string, min_val_loss, min_epoch, lr, wd, pp, time_string))


one_epochs = 500
one_lr = 1e-4
one_wd = 1e-2
one_pp = None
one_module = AE_bn_LeakyReLU
continue_training = False
checkpoint_name = 'nn_utils_bs1024_lr1e-04_wd1e-02_ppNA'

def one_run(module, epochs, lr, wd, pp, ct, dim):
    module_string = str(module).split("'")[1].split(".")[1]
    save_dict[module_string] = {}
    if pp is not None:
        print('Training %s with lr=%.1e, p=%.1e, wd=%.1e ...' % (module_string, lr, pp, wd))
        curr_model_p = module(dropout=pp)
        train_and_save(curr_model_p, epochs, lr, wd, pp, module_string, save_dict, ct, checkpoint_name)
        print('...done')
    else:
        print('Training %s with lr=%.1e, p=None, wd=%.1e ...' % (module_string, lr, wd))
        curr_model = module([4, 400, 400, 200, 3, 200, 400, 400, 4])
        train_and_save(curr_model, epochs, lr, wd, pp, module_string, save_dict, ct, checkpoint_name)
        print('...done')

tic = time.time()
one_run(module=one_module, epochs=one_epochs, lr=one_lr, wd=one_wd, pp=one_pp, ct=continue_training, dim=train.shape[-1])
toc = time.time()

time_taken = (toc-tic)/60.0

print('Total time taken: ', time_taken , 'minutes')
print('Time taken per epoch: ', time_taken / one_epochs, 'minutes')
