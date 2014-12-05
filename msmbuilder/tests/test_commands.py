from __future__ import print_function, division
import os
import itertools
import tempfile
import shutil
import shlex
import subprocess
import numpy as np
import mdtraj as md
from mdtraj.testing import eq
from mdtraj.testing import get_fn as get_mdtraj_fn

from msmbuilder.utils import load
from msmbuilder.dataset import dataset
from msmbuilder.example_datasets import get_data_home
from msmbuilder.example_datasets.alanine_dipeptide import fetch_alanine_dipeptide

import sklearn.hmm
DATADIR = HMM = None

################################################################################
# Fixtures
################################################################################

def setup_module():
    global DATADIR, HMM
    DATADIR = tempfile.mkdtemp()
    # 4 components and 3 features. Each feature is going to be the x, y, z
    # coordinate of 1 atom
    HMM = sklearn.hmm.GaussianHMM(n_components=4)
    HMM.transmat_ = np.array([[0.9, 0.1, 0.0, 0.0],
                              [0.1, 0.7, 0.2, 0.0],
                              [0.0, 0.1, 0.8, 0.1],
                              [0.0, 0.1, 0.1, 0.8]])
    HMM.means_ = np.array([[-10, -10, -10],
                           [-5,  -5,   -5],
                           [5,    5,    5],
                           [10,  10,   10]])
    HMM.covars_ = np.array([[0.1, 0.1, 0.1],
                            [0.5, 0.5, 0.5],
                            [1, 1, 1],
                            [4, 4, 4]])
    HMM.startprob_ = np.array([1, 1, 1, 1]) / 4.0

    # get a 1 atom topology
    topology = md.load(get_mdtraj_fn('native.pdb')).restrict_atoms([1]).topology

    # generate the trajectories and save them to disk
    for i in range(10):
        d, s = HMM.sample(100)
        t = md.Trajectory(xyz=d.reshape(len(d), 1, 3), topology=topology)
        t.save(os.path.join(DATADIR, 'Trajectory%d.h5' % i))

    fetch_alanine_dipeptide()

def teardown_module():
    shutil.rmtree(DATADIR)


class tempdir(object):
    def __enter__(self):
        self._curdir = os.path.abspath(os.curdir)
        self._tempdir = tempfile.mkdtemp()
        os.chdir(self._tempdir)

    def __exit__(self, *exc_info):
        os.chdir(self._curdir)
        shutil.rmtree(self._tempdir)


def shell(str):
    # Capture stdout
    split = shlex.split(str)
    print(str)
    with open(os.devnull, 'w') as noout:
        assert subprocess.call(split, stdout=noout) == 0

################################################################################
# Tests
################################################################################

def test_atomindices():
    fn = get_mdtraj_fn('2EQQ.pdb')
    t = md.load(fn)
    with tempdir():
        shell('msmb AtomIndices -o all.txt --all -a -p %s' % fn)
        shell('msmb AtomIndices -o all-pairs.txt --all -d -p %s' % fn)
        atoms = np.loadtxt('all.txt', int)
        pairs =  np.loadtxt('all-pairs.txt', int)
        eq(t.n_atoms, len(atoms))
        eq(int(t.n_atoms * (t.n_atoms-1) / 2), len(pairs))

    with tempdir():
        shell('msmb AtomIndices -o heavy.txt --heavy -a -p %s' % fn)
        shell('msmb AtomIndices -o heavy-pairs.txt --heavy -d -p %s' % fn)
        atoms = np.loadtxt('heavy.txt', int)
        pairs = np.loadtxt('heavy-pairs.txt', int)
        assert all(t.topology.atom(i).element.symbol != 'H' for i in atoms)
        assert sum(1 for a in t.topology.atoms if a.element.symbol != 'H') == len(atoms)
        eq(np.array(list(itertools.combinations(atoms, 2))), pairs)
    
    with tempdir():
        shell('msmb AtomIndices -o alpha.txt --alpha -a -p %s' % fn)
        shell('msmb AtomIndices -o alpha-pairs.txt --alpha -d -p %s' % fn)
        atoms = np.loadtxt('alpha.txt', int)
        pairs = np.loadtxt('alpha-pairs.txt', int)
        assert all(t.topology.atom(i).name == 'CA' for i in atoms)
        assert sum(1 for a in t.topology.atoms if a.name == 'CA') == len(atoms)
        eq(np.array(list(itertools.combinations(atoms, 2))), pairs)

    with tempdir():
        shell('msmb AtomIndices -o minimal.txt --minimal -a -p %s' % fn)
        shell('msmb AtomIndices -o minimal-pairs.txt --minimal -d -p %s' % fn)
        atoms = np.loadtxt('minimal.txt', int)
        pairs = np.loadtxt('minimal-pairs.txt', int)
        assert all(t.topology.atom(i).name in ['CA', 'CB', 'C', 'N' , 'O'] for i in atoms)
        eq(np.array(list(itertools.combinations(atoms, 2))), pairs)


def test_superpose_featurizer():
    with tempdir():
        shell('msmb AtomIndices -o all.txt --all -a -p %s/alanine_dipeptide/ala2.pdb' % get_data_home()),
        shell("msmb SuperposeFeaturizer --trjs '{data_home}/alanine_dipeptide/*.dcd'"
              " --out distances --atom_indices all.txt"
              " --reference_traj {data_home}/alanine_dipeptide/ala2.pdb"
              " --top {data_home}/alanine_dipeptide/ala2.pdb".format(
                  data_home=get_data_home()))
        ds = dataset('distances')
        assert len(ds) == 10
        assert ds[0].shape[1] == len(np.loadtxt('all.txt'))
        print(ds.provenance)


def test_atom_pairs_featurizer():
    with tempdir():
        shell('msmb AtomIndices -o all.txt --all -d -p %s/alanine_dipeptide/ala2.pdb' % get_data_home()),
        shell("msmb AtomPairsFeaturizer --trjs '{data_home}/alanine_dipeptide/*.dcd'"
              " --out pairs --pair_indices all.txt"
              " --top {data_home}/alanine_dipeptide/ala2.pdb".format(
                  data_home=get_data_home()))
        ds = dataset('pairs')
        assert len(ds) == 10
        assert ds[0].shape[1] == len(np.loadtxt('all.txt')**2)
        print(ds.provenance)


def test_transform_command_1():
    with tempdir():
        shell("msmb KCenters -i {data_home}/alanine_dipeptide/*.dcd "
              "-o model.pkl --top {data_home}/alanine_dipeptide/ala2.pdb "
              "--metric rmsd".format(data_home=get_data_home()))
        shell("msmb TransformDataset -i {data_home}/alanine_dipeptide/*.dcd "
              "-m model.pkl -t transformed.h5 --top "
              "{data_home}/alanine_dipeptide/ala2.pdb".format(data_home=get_data_home()))

        eq(dataset('transformed.h5')[0], load('model.pkl').labels_[0])


def test_help():
    shell('msmb -h')