#######################################################################
#                                                                     #
#  Copyright 2015 Max Planck Institute                                #
#                 for Dynamics and Self-Organization                  #
#                                                                     #
#  This file is part of bfps.                                         #
#                                                                     #
#  bfps is free software: you can redistribute it and/or modify       #
#  it under the terms of the GNU General Public License as published  #
#  by the Free Software Foundation, either version 3 of the License,  #
#  or (at your option) any later version.                             #
#                                                                     #
#  bfps is distributed in the hope that it will be useful,            #
#  but WITHOUT ANY WARRANTY; without even the implied warranty of     #
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the      #
#  GNU General Public License for more details.                       #
#                                                                     #
#  You should have received a copy of the GNU General Public License  #
#  along with bfps.  If not, see <http://www.gnu.org/licenses/>       #
#                                                                     #
# Contact: Cristian.Lalescu@ds.mpg.de                                 #
#                                                                     #
#######################################################################



import sys
import os
import numpy as np
import h5py
import argparse

import bfps
import bfps.tools
from bfps._code import _code
from bfps._fluid_base import _fluid_particle_base

class NSVorticityEquation(_fluid_particle_base):
    def __init__(
            self,
            name = 'NSVorticityEquation-v' + bfps.__version__,
            work_dir = './',
            simname = 'test',
            fluid_precision = 'single',
            fftw_plan_rigor = 'FFTW_MEASURE',
            use_fftw_wisdom = True):
        """
            This code uses checkpoints for DNS restarts, and it can be stopped
            by creating the file "stop_<simname>" in the working directory.
            For postprocessing of field snapshots, consider creating a separate
            HDF5 file (from the python wrapper) which contains links to all the
            different snapshots.
        """
        self.fftw_plan_rigor = fftw_plan_rigor
        _fluid_particle_base.__init__(
                self,
                name = name + '-' + fluid_precision,
                work_dir = work_dir,
                simname = simname,
                dtype = fluid_precision,
                use_fftw_wisdom = use_fftw_wisdom)
        self.parameters['nu'] = float(0.1)
        self.parameters['fmode'] = 1
        self.parameters['famplitude'] = float(0.5)
        self.parameters['fk0'] = float(2.0)
        self.parameters['fk1'] = float(4.0)
        self.parameters['forcing_type'] = 'linear'
        self.parameters['histogram_bins'] = int(256)
        self.parameters['max_velocity_estimate'] = float(1)
        self.parameters['max_vorticity_estimate'] = float(1)
        self.parameters['checkpoints_per_file'] = int(1)
        self.file_datasets_grow = """
                //begincpp
                hid_t group;
                group = H5Gopen(stat_file, "/statistics", H5P_DEFAULT);
                H5Ovisit(group, H5_INDEX_NAME, H5_ITER_NATIVE, grow_statistics_dataset, NULL);
                H5Gclose(group);
                //endcpp
                """
        self.style = {}
        self.statistics = {}
        self.fluid_output = """
                fs->io_checkpoint(false);
                """
        # vorticity_equation specific things
        self.includes += '#include "vorticity_equation.hpp"\n'
        self.store_kspace = """
                //begincpp
                if (myrank == 0 && iteration == 0)
                {
                    TIMEZONE("fluid_base::store_kspace");
                    hsize_t dims[4];
                    hid_t space, dset;
                    // store kspace information
                    dset = H5Dopen(stat_file, "/kspace/kshell", H5P_DEFAULT);
                    space = H5Dget_space(dset);
                    H5Sget_simple_extent_dims(space, dims, NULL);
                    H5Sclose(space);
                    if (fs->kk->nshells != dims[0])
                    {
                        DEBUG_MSG(
                            "ERROR: computed nshells %d not equal to data file nshells %d\\n",
                            fs->kk->nshells, dims[0]);
                    }
                    H5Dwrite(dset, H5T_NATIVE_DOUBLE, H5S_ALL, H5S_ALL, H5P_DEFAULT, &fs->kk->kshell.front());
                    H5Dclose(dset);
                    dset = H5Dopen(stat_file, "/kspace/nshell", H5P_DEFAULT);
                    H5Dwrite(dset, H5T_NATIVE_INT64, H5S_ALL, H5S_ALL, H5P_DEFAULT, &fs->kk->nshell.front());
                    H5Dclose(dset);
                    dset = H5Dopen(stat_file, "/kspace/kM", H5P_DEFAULT);
                    H5Dwrite(dset, H5T_NATIVE_DOUBLE, H5S_ALL, H5S_ALL, H5P_DEFAULT, &fs->kk->kM);
                    H5Dclose(dset);
                    dset = H5Dopen(stat_file, "/kspace/dk", H5P_DEFAULT);
                    H5Dwrite(dset, H5T_NATIVE_DOUBLE, H5S_ALL, H5S_ALL, H5P_DEFAULT, &fs->kk->dk);
                    H5Dclose(dset);
                }
                //endcpp
                """
        return None
    def add_particles(
            self,
            integration_steps = 2,
            neighbours = 1,
            smoothness = 1):
        assert(integration_steps > 0 and integration_steps < 6)
        self.particle_species = 1
        self.parameters['tracers0_integration_steps'] = int(integration_steps)
        self.parameters['tracers0_neighbours'] = int(neighbours)
        self.parameters['tracers0_smoothness'] = int(smoothness)
        self.parameters['tracers0_interpolator'] = 'spline'
        self.particle_includes += """
                #include "particles/particles_system_builder.hpp"
                #include "particles/particles_output_hdf5.hpp"
                """
        ## initialize
        self.particle_start += """
            DEBUG_MSG(
                    "current fname is %s\\n and iteration is %d",
                    fs->get_current_fname().c_str(),
                    fs->iteration);
            std::unique_ptr<abstract_particles_system<long long int, double>> ps = particles_system_builder(
                    fs->cvelocity,              // (field object)
                    fs->kk,                     // (kspace object, contains dkx, dky, dkz)
                    tracers0_integration_steps, // to check coherency between parameters and hdf input file (nb rhs)
                    (long long int)nparticles,                 // to check coherency between parameters and hdf input file
                    fs->get_current_fname(),    // particles input filename
                    std::string("/tracers0/state/") + std::to_string(fs->iteration), // dataset name for initial input
                    std::string("/tracers0/rhs/")  + std::to_string(fs->iteration), // dataset name for initial input
                    tracers0_neighbours,        // parameter (interpolation no neighbours)
                    tracers0_smoothness,        // parameter
                    MPI_COMM_WORLD,
                    fs->iteration+1);
            particles_output_hdf5<long long int, double,3,3> particles_output_writer_mpi(
                        MPI_COMM_WORLD,
                        "tracers0",
                        nparticles,
                        tracers0_integration_steps);
                    """
        self.particle_loop += """
                fs->compute_velocity(fs->cvorticity);
                fs->cvelocity->ift();
                ps->completeLoop(dt);
                """
        self.particle_output = """
                {
                    particles_output_writer_mpi.open_file(fs->get_current_fname());
                    particles_output_writer_mpi.save(ps->getParticlesPositions(),
                                                     ps->getParticlesRhs(),
                                                     ps->getParticlesIndexes(),
                                                     ps->getLocalNbParticles(),
                                                     fs->iteration);
                    particles_output_writer_mpi.close_file();
                }
                           """
        self.particle_end += 'ps.release();\n'
        return None
    def create_stat_output(
            self,
            dset_name,
            data_buffer,
            data_type = 'H5T_NATIVE_DOUBLE',
            size_setup = None,
            close_spaces = True):
        new_stat_output_txt = 'Cdset = H5Dopen(stat_file, "{0}", H5P_DEFAULT);\n'.format(dset_name)
        if not type(size_setup) == type(None):
            new_stat_output_txt += (
                    size_setup +
                    'wspace = H5Dget_space(Cdset);\n' +
                    'ndims = H5Sget_simple_extent_dims(wspace, dims, NULL);\n' +
                    'mspace = H5Screate_simple(ndims, count, NULL);\n' +
                    'H5Sselect_hyperslab(wspace, H5S_SELECT_SET, offset, NULL, count, NULL);\n')
        new_stat_output_txt += ('H5Dwrite(Cdset, {0}, mspace, wspace, H5P_DEFAULT, {1});\n' +
                                'H5Dclose(Cdset);\n').format(data_type, data_buffer)
        if close_spaces:
            new_stat_output_txt += ('H5Sclose(mspace);\n' +
                                    'H5Sclose(wspace);\n')
        return new_stat_output_txt
    def write_fluid_stats(self):
        self.fluid_includes += '#include <cmath>\n'
        self.fluid_includes += '#include "fftw_tools.hpp"\n'
        self.stat_src += """
                //begincpp
                hid_t stat_group;
                if (myrank == 0)
                    stat_group = H5Gopen(stat_file, "statistics", H5P_DEFAULT);
                fs->compute_velocity(fs->cvorticity);
                *tmp_vec_field = fs->cvelocity->get_cdata();
                tmp_vec_field->compute_stats(
                    fs->kk,
                    stat_group,
                    "velocity",
                    fs->iteration / niter_stat,
                    max_velocity_estimate/sqrt(3));
                //endcpp
                """
        self.stat_src += """
                //begincpp
                *tmp_vec_field = fs->cvorticity->get_cdata();
                tmp_vec_field->compute_stats(
                    fs->kk,
                    stat_group,
                    "vorticity",
                    fs->iteration / niter_stat,
                    max_vorticity_estimate/sqrt(3));
                //endcpp
                """
        self.stat_src += """
                //begincpp
                if (myrank == 0)
                    H5Gclose(stat_group);
                if (myrank == 0)
                {{
                    hid_t Cdset, wspace, mspace;
                    int ndims;
                    hsize_t count[4], offset[4], dims[4];
                    offset[0] = fs->iteration/niter_stat;
                    offset[1] = 0;
                    offset[2] = 0;
                    offset[3] = 0;
                //endcpp
                """.format(self.C_dtype)
        if self.dtype == np.float32:
            field_H5T = 'H5T_NATIVE_FLOAT'
        elif self.dtype == np.float64:
            field_H5T = 'H5T_NATIVE_DOUBLE'
        self.stat_src += self.create_stat_output(
                '/statistics/xlines/velocity',
                'fs->rvelocity->get_rdata()',
                data_type = field_H5T,
                size_setup = """
                    count[0] = 1;
                    count[1] = nx;
                    count[2] = 3;
                    """,
                close_spaces = False)
        self.stat_src += self.create_stat_output(
                '/statistics/xlines/vorticity',
                'fs->rvorticity->get_rdata()',
                data_type = field_H5T)
        self.stat_src += '}\n'
        ## checkpoint
        self.stat_src += """
                //begincpp
                if (myrank == 0)
                {
                    std::string fname = (
                        std::string("stop_") +
                        std::string(simname));
                    {
                        struct stat file_buffer;
                        stop_code_now = (stat(fname.c_str(), &file_buffer) == 0);
                    }
                }
                MPI_Bcast(&stop_code_now, 1, MPI_C_BOOL, 0, MPI_COMM_WORLD);
                //endcpp
                """
        return None
    def fill_up_fluid_code(self):
        self.fluid_includes += '#include <cstring>\n'
        self.fluid_variables += (
                'vorticity_equation<{0}, FFTW> *fs;\n'.format(self.C_dtype) +
                'field<{0}, FFTW, THREE> *tmp_vec_field;\n'.format(self.C_dtype) +
                'field<{0}, FFTW, ONE> *tmp_scal_field;\n'.format(self.C_dtype))
        self.fluid_definitions += """
                    typedef struct {{
                        {0} re;
                        {0} im;
                    }} tmp_complex_type;
                    """.format(self.C_dtype)
        self.write_fluid_stats()
        if self.dtype == np.float32:
            field_H5T = 'H5T_NATIVE_FLOAT'
        elif self.dtype == np.float64:
            field_H5T = 'H5T_NATIVE_DOUBLE'
        self.variables += 'int checkpoint;\n'
        self.variables += 'bool stop_code_now;\n'
        self.read_checkpoint = """
                //begincpp
                if (myrank == 0)
                {
                    hid_t dset = H5Dopen(stat_file, "checkpoint", H5P_DEFAULT);
                    H5Dread(
                        dset,
                        H5T_NATIVE_INT,
                        H5S_ALL,
                        H5S_ALL,
                        H5P_DEFAULT,
                        &checkpoint);
                    H5Dclose(dset);
                }
                MPI_Bcast(&checkpoint, 1, MPI_INT, 0, MPI_COMM_WORLD);
                fs->checkpoint = checkpoint;
                //endcpp
        """
        self.store_checkpoint = """
                //begincpp
                checkpoint = fs->checkpoint;
                if (myrank == 0)
                {
                    hid_t dset = H5Dopen(stat_file, "checkpoint", H5P_DEFAULT);
                    H5Dwrite(
                        dset,
                        H5T_NATIVE_INT,
                        H5S_ALL,
                        H5S_ALL,
                        H5P_DEFAULT,
                        &checkpoint);
                    H5Dclose(dset);
                }
                //endcpp
        """
        self.fluid_start += """
                //begincpp
                char fname[512];
                fs = new vorticity_equation<{0}, FFTW>(
                        simname,
                        nx, ny, nz,
                        dkx, dky, dkz,
                        {1});
                tmp_vec_field = new field<{0}, FFTW, THREE>(
                        nx, ny, nz,
                        MPI_COMM_WORLD,
                        {1});
                tmp_scal_field = new field<{0}, FFTW, ONE>(
                        nx, ny, nz,
                        MPI_COMM_WORLD,
                        {1});
                fs->checkpoints_per_file = checkpoints_per_file;
                fs->nu = nu;
                fs->fmode = fmode;
                fs->famplitude = famplitude;
                fs->fk0 = fk0;
                fs->fk1 = fk1;
                strncpy(fs->forcing_type, forcing_type, 128);
                fs->iteration = iteration;
                {2}
                fs->cvorticity->real_space_representation = false;
                fs->io_checkpoint();
                //endcpp
                """.format(
                        self.C_dtype,
                        self.fftw_plan_rigor,
                        self.read_checkpoint)
        self.fluid_start += self.store_kspace
        self.fluid_start += 'stop_code_now = false;\n'
        self.fluid_loop = 'fs->step(dt);\n'
        self.fluid_loop += ('if (fs->iteration % niter_out == 0)\n{\n' +
                            self.fluid_output +
                            self.particle_output +
                            self.store_checkpoint +
                            '\n}\n' +
                            'if (stop_code_now){\n' +
                            'iteration = fs->iteration;\n' +
                            'break;\n}\n')
        self.fluid_end = ('if (fs->iteration % niter_out != 0)\n{\n' +
                          self.fluid_output +
                          self.particle_output +
                          self.store_checkpoint +
                          'DEBUG_MSG("checkpoint value is %d\\n", checkpoint);\n' +
                          '\n}\n' +
                          'delete fs;\n' +
                          'delete tmp_vec_field;\n' +
                          'delete tmp_scal_field;\n')
        return None
    def get_postprocess_file_name(self):
        return os.path.join(self.work_dir, self.simname + '_postprocess.h5')
    def get_postprocess_file(self):
        return h5py.File(self.get_postprocess_file_name(), 'r')
    def compute_statistics(self, iter0 = 0, iter1 = None):
        """Run basic postprocessing on raw data.
        The energy spectrum :math:`E(t, k)` and the enstrophy spectrum
        :math:`\\frac{1}{2}\omega^2(t, k)` are computed from the

        .. math::

            \sum_{k \\leq \\|\\mathbf{k}\\| \\leq k+dk}\\hat{u_i} \\hat{u_j}^*, \\hskip .5cm
            \sum_{k \\leq \\|\\mathbf{k}\\| \\leq k+dk}\\hat{\omega_i} \\hat{\\omega_j}^*

        tensors, and the enstrophy spectrum is also used to
        compute the dissipation :math:`\\varepsilon(t)`.
        These basic quantities are stored in a newly created HDF5 file,
        ``simname_postprocess.h5``.
        """
        if len(list(self.statistics.keys())) > 0:
            return None
        self.read_parameters()
        with self.get_data_file() as data_file:
            if 'moments' not in data_file['statistics'].keys():
                return None
            iter0 = min((data_file['statistics/moments/velocity'].shape[0] *
                         self.parameters['niter_stat']-1),
                        iter0)
            if type(iter1) == type(None):
                iter1 = data_file['iteration'].value
            else:
                iter1 = min(data_file['iteration'].value, iter1)
            ii0 = iter0 // self.parameters['niter_stat']
            ii1 = iter1 // self.parameters['niter_stat']
            self.statistics['kshell'] = data_file['kspace/kshell'].value
            self.statistics['kM'] = data_file['kspace/kM'].value
            self.statistics['dk'] = data_file['kspace/dk'].value
            computation_needed = True
            pp_file = h5py.File(self.get_postprocess_file_name(), 'a')
            if 'ii0' in pp_file.keys():
                computation_needed =  not (ii0 == pp_file['ii0'].value and
                                           ii1 == pp_file['ii1'].value)
                if computation_needed:
                    for k in pp_file.keys():
                        del pp_file[k]
            if computation_needed:
                pp_file['iter0'] = iter0
                pp_file['iter1'] = iter1
                pp_file['ii0'] = ii0
                pp_file['ii1'] = ii1
                pp_file['t'] = (self.parameters['dt']*
                                self.parameters['niter_stat']*
                                (np.arange(ii0, ii1+1).astype(np.float)))
                pp_file['energy(t, k)'] = (
                    data_file['statistics/spectra/velocity_velocity'][ii0:ii1+1, :, 0, 0] +
                    data_file['statistics/spectra/velocity_velocity'][ii0:ii1+1, :, 1, 1] +
                    data_file['statistics/spectra/velocity_velocity'][ii0:ii1+1, :, 2, 2])/2
                pp_file['enstrophy(t, k)'] = (
                    data_file['statistics/spectra/vorticity_vorticity'][ii0:ii1+1, :, 0, 0] +
                    data_file['statistics/spectra/vorticity_vorticity'][ii0:ii1+1, :, 1, 1] +
                    data_file['statistics/spectra/vorticity_vorticity'][ii0:ii1+1, :, 2, 2])/2
                pp_file['vel_max(t)'] = data_file['statistics/moments/velocity']  [ii0:ii1+1, 9, 3]
                pp_file['renergy(t)'] = data_file['statistics/moments/velocity'][ii0:ii1+1, 2, 3]/2
            for k in ['t',
                      'energy(t, k)',
                      'enstrophy(t, k)',
                      'vel_max(t)',
                      'renergy(t)']:
                if k in pp_file.keys():
                    self.statistics[k] = pp_file[k].value
            self.compute_time_averages()
        return None
    def compute_time_averages(self):
        """Compute easy stats.

        Further computation of statistics based on the contents of
        ``simname_postprocess.h5``.
        Standard quantities are as follows
        (consistent with [Ishihara]_):

        .. math::

            U_{\\textrm{int}}(t) = \\sqrt{\\frac{2E(t)}{3}}, \\hskip .5cm
            L_{\\textrm{int}}(t) = \\frac{\pi}{2U_{int}^2(t)} \\int \\frac{dk}{k} E(t, k), \\hskip .5cm
            T_{\\textrm{int}}(t) =
            \\frac{L_{\\textrm{int}}(t)}{U_{\\textrm{int}}(t)}

            \\eta_K = \\left(\\frac{\\nu^3}{\\varepsilon}\\right)^{1/4}, \\hskip .5cm
            \\tau_K = \\left(\\frac{\\nu}{\\varepsilon}\\right)^{1/2}, \\hskip .5cm
            \\lambda = \\sqrt{\\frac{15 \\nu U_{\\textrm{int}}^2}{\\varepsilon}}

            Re = \\frac{U_{\\textrm{int}} L_{\\textrm{int}}}{\\nu}, \\hskip
            .5cm
            R_{\\lambda} = \\frac{U_{\\textrm{int}} \\lambda}{\\nu}

        .. [Ishihara] T. Ishihara et al,
                      *Small-scale statistics in high-resolution direct numerical
                      simulation of turbulence: Reynolds number dependence of
                      one-point velocity gradient statistics*.
                      J. Fluid Mech.,
                      **592**, 335-366, 2007
        """
        for key in ['energy', 'enstrophy']:
            self.statistics[key + '(t)'] = (self.statistics['dk'] *
                                            np.sum(self.statistics[key + '(t, k)'], axis = 1))
        self.statistics['Uint(t)'] = np.sqrt(2*self.statistics['energy(t)'] / 3)
        self.statistics['Lint(t)'] = ((self.statistics['dk']*np.pi /
                                       (2*self.statistics['Uint(t)']**2)) *
                                      np.nansum(self.statistics['energy(t, k)'] /
                                                self.statistics['kshell'][None, :], axis = 1))
        for key in ['energy',
                    'enstrophy',
                    'vel_max',
                    'Uint',
                    'Lint']:
            if key + '(t)' in self.statistics.keys():
                self.statistics[key] = np.average(self.statistics[key + '(t)'], axis = 0)
        for suffix in ['', '(t)']:
            self.statistics['diss'    + suffix] = (self.parameters['nu'] *
                                                   self.statistics['enstrophy' + suffix]*2)
            self.statistics['etaK'    + suffix] = (self.parameters['nu']**3 /
                                                   self.statistics['diss' + suffix])**.25
            self.statistics['tauK'    + suffix] =  (self.parameters['nu'] /
                                                    self.statistics['diss' + suffix])**.5
            self.statistics['Re' + suffix] = (self.statistics['Uint' + suffix] *
                                              self.statistics['Lint' + suffix] /
                                              self.parameters['nu'])
            self.statistics['lambda' + suffix] = (15 * self.parameters['nu'] *
                                                  self.statistics['Uint' + suffix]**2 /
                                                  self.statistics['diss' + suffix])**.5
            self.statistics['Rlambda' + suffix] = (self.statistics['Uint' + suffix] *
                                                   self.statistics['lambda' + suffix] /
                                                   self.parameters['nu'])
            self.statistics['kMeta' + suffix] = (self.statistics['kM'] *
                                                 self.statistics['etaK' + suffix])
            if self.parameters['dealias_type'] == 1:
                self.statistics['kMeta' + suffix] *= 0.8
        self.statistics['Tint'] = self.statistics['Lint'] / self.statistics['Uint']
        self.statistics['Taylor_microscale'] = self.statistics['lambda']
        return None
    def set_plt_style(
            self,
            style = {'dashes' : (None, None)}):
        self.style.update(style)
        return None
    def convert_complex_from_binary(
            self,
            field_name = 'vorticity',
            iteration = 0,
            file_name = None):
        """read the Fourier representation of a vector field.

        Read the binary file containing iteration ``iteration`` of the
        field ``field_name``, and write it in a ``.h5`` file.
        """
        data = np.memmap(
                os.path.join(self.work_dir,
                             self.simname + '_{0}_i{1:0>5x}'.format('c' + field_name, iteration)),
                dtype = self.ctype,
                mode = 'r',
                shape = (self.parameters['ny'],
                         self.parameters['nz'],
                         self.parameters['nx']//2+1,
                         3))
        if type(file_name) == type(None):
            file_name = self.simname + '_{0}_i{1:0>5x}.h5'.format('c' + field_name, iteration)
            file_name = os.path.join(self.work_dir, file_name)
        f = h5py.File(file_name, 'a')
        f[field_name + '/complex/{0}'.format(iteration)] = data
        f.close()
        return None
    def write_par(
            self,
            iter0 = 0,
            particle_ic = None):
        _fluid_particle_base.write_par(self, iter0 = iter0)
        with h5py.File(self.get_data_file_name(), 'r+') as ofile:
            kspace = self.get_kspace()
            nshells = kspace['nshell'].shape[0]
            vec_stat_datasets = ['velocity', 'vorticity']
            scal_stat_datasets = []
            for k in vec_stat_datasets:
                time_chunk = 2**20//(8*3*self.parameters['nx']) # FIXME: use proper size of self.dtype
                time_chunk = max(time_chunk, 1)
                ofile.create_dataset('statistics/xlines/' + k,
                                     (1, self.parameters['nx'], 3),
                                     chunks = (time_chunk, self.parameters['nx'], 3),
                                     maxshape = (None, self.parameters['nx'], 3),
                                     dtype = self.dtype)
            for k in vec_stat_datasets:
                time_chunk = 2**20//(8*3*3*nshells)
                time_chunk = max(time_chunk, 1)
                ofile.create_dataset('statistics/spectra/' + k + '_' + k,
                                     (1, nshells, 3, 3),
                                     chunks = (time_chunk, nshells, 3, 3),
                                     maxshape = (None, nshells, 3, 3),
                                     dtype = np.float64)
                time_chunk = 2**20//(8*4*10)
                time_chunk = max(time_chunk, 1)
                a = ofile.create_dataset('statistics/moments/' + k,
                                     (1, 10, 4),
                                     chunks = (time_chunk, 10, 4),
                                     maxshape = (None, 10, 4),
                                     dtype = np.float64)
                time_chunk = 2**20//(8*4*self.parameters['histogram_bins'])
                time_chunk = max(time_chunk, 1)
                ofile.create_dataset('statistics/histograms/' + k,
                                     (1,
                                      self.parameters['histogram_bins'],
                                      4),
                                     chunks = (time_chunk,
                                               self.parameters['histogram_bins'],
                                               4),
                                     maxshape = (None,
                                                 self.parameters['histogram_bins'],
                                                 4),
                                     dtype = np.int64)
            ofile['checkpoint'] = int(0)
        if self.particle_species == 0:
            return None

        if type(particle_ic) == type(None):
            pbase_shape = (self.parameters['nparticles'],)
            number_of_particles = self.parameters['nparticles']
        else:
            pbase_shape = particle_ic.shape[:-1]
            assert(particle_ic.shape[-1] == 3)
            number_of_particles = 1
            for val in pbase_shape[1:]:
                number_of_particles *= val
        with h5py.File(self.get_checkpoint_0_fname(), 'a') as ofile:
            s = 0
            ofile.create_group('tracers{0}'.format(s))
            ofile.create_group('tracers{0}/rhs'.format(s))
            ofile.create_group('tracers{0}/state'.format(s))
            ofile['tracers{0}/rhs'.format(s)].create_dataset(
                    '0',
                    shape = (
                        (self.parameters['tracers{0}_integration_steps'.format(s)],) +
                        pbase_shape +
                        (3,)),
                    dtype = np.float)
            ofile['tracers{0}/state'.format(s)].create_dataset(
                    '0',
                    shape = (
                        pbase_shape +
                        (3,)),
                    dtype = np.float)
        return None
    def specific_parser_arguments(
            self,
            parser):
        _fluid_particle_base.specific_parser_arguments(self, parser)
        parser.add_argument(
                '--src-wd',
                type = str,
                dest = 'src_work_dir',
                default = '')
        parser.add_argument(
                '--src-simname',
                type = str,
                dest = 'src_simname',
                default = '')
        parser.add_argument(
                '--src-iteration',
                type = int,
                dest = 'src_iteration',
                default = 0)
        parser.add_argument(
               '--njobs',
               type = int, dest = 'njobs',
               default = 1)
        parser.add_argument(
               '--kMeta',
               type = float,
               dest = 'kMeta',
               default = 2.0)
        parser.add_argument(
               '--dtfactor',
               type = float,
               dest = 'dtfactor',
               default = 0.5,
               help = 'dt is computed as DTFACTOR / N')
        parser.add_argument(
               '--particle-rand-seed',
               type = int,
               dest = 'particle_rand_seed',
               default = None)
        parser.add_argument(
               '--pclouds',
               type = int,
               dest = 'pclouds',
               default = 1,
               help = ('number of particle clouds. Particle "clouds" '
                       'consist of particles distributed according to '
                       'pcloud-type.'))
        parser.add_argument(
                '--pcloud-type',
                choices = ['random-cube',
                           'regular-cube'],
                dest = 'pcloud_type',
                default = 'random-cube')
        parser.add_argument(
               '--particle-cloud-size',
               type = float,
               dest = 'particle_cloud_size',
               default = 2*np.pi)
        parser.add_argument(
                '--neighbours',
                type = int,
                dest = 'neighbours',
                default = 1)
        parser.add_argument(
                '--smoothness',
                type = int,
                dest = 'smoothness',
                default = 1)
        return None
    def prepare_launch(
            self,
            args = []):
        """Set up reasonable parameters.

        With the default Lundgren forcing applied in the band [2, 4],
        we can estimate the dissipation, therefore we can estimate
        :math:`k_M \\eta_K` and constrain the viscosity.

        In brief, the command line parameter :math:`k_M \\eta_K` is
        used in the following formula for :math:`\\nu` (:math:`N` is the
        number of real space grid points per coordinate):

        .. math::

            \\nu = \\left(\\frac{2 k_M \\eta_K}{N} \\right)^{4/3}

        With this choice, the average dissipation :math:`\\varepsilon`
        will be close to 0.4, and the integral scale velocity will be
        close to 0.77, yielding the approximate value for the Taylor
        microscale and corresponding Reynolds number:

        .. math::

            \\lambda \\approx 4.75\\left(\\frac{2 k_M \\eta_K}{N} \\right)^{4/6}, \\hskip .5in
            R_\\lambda \\approx 3.7 \\left(\\frac{N}{2 k_M \\eta_K} \\right)^{4/6}

        """
        opt = _code.prepare_launch(self, args = args)
        self.parameters['nu'] = (opt.kMeta * 2 / opt.n)**(4./3)
        self.parameters['dt'] = (opt.dtfactor / opt.n)
        # custom famplitude for 288 and 576
        if opt.n == 288:
            self.parameters['famplitude'] = 0.45
        elif opt.n == 576:
            self.parameters['famplitude'] = 0.47
        if ((self.parameters['niter_todo'] % self.parameters['niter_out']) != 0):
            self.parameters['niter_out'] = self.parameters['niter_todo']
        if len(opt.src_work_dir) == 0:
            opt.src_work_dir = os.path.realpath(opt.work_dir)
        self.pars_from_namespace(opt)
        return opt
    def launch(
            self,
            args = [],
            **kwargs):
        opt = self.prepare_launch(args = args)
        if type(opt.nparticles) != type(None):
            if opt.nparticles > 0:
                self.name += '-particles'
                self.add_particles(
                    integration_steps = 4,
                    neighbours = opt.neighbours,
                    smoothness = opt.smoothness)
        self.fill_up_fluid_code()
        self.finalize_code()
        self.launch_jobs(opt = opt, **kwargs)
        return None
    def get_checkpoint_0_fname(self):
        return os.path.join(
                    self.work_dir,
                    self.simname + '_checkpoint_0.h5')
    def generate_tracer_state(
            self,
            rseed = None,
            iteration = 0,
            species = 0,
            write_to_file = False,
            ncomponents = 3,
            testing = False,
            data = None):
        if (type(data) == type(None)):
            if not type(rseed) == type(None):
                np.random.seed(rseed)
            #point with problems: 5.37632864e+00,   6.10414710e+00,   6.25256493e+00]
            data = np.zeros(self.parameters['nparticles']*ncomponents).reshape(-1, ncomponents)
            data[:, :3] = np.random.random((self.parameters['nparticles'], 3))*2*np.pi
        if testing:
            #data[0] = np.array([3.26434, 4.24418, 3.12157])
            data[:] = np.array([ 0.72086101,  2.59043666,  6.27501953])
        with h5py.File(self.get_checkpoint_0_fname(), 'a') as data_file:
            data_file['tracers{0}/state/0'.format(species)][:] = data
        if write_to_file:
            data.tofile(
                    os.path.join(
                        self.work_dir,
                        "tracers{0}_state_i{1:0>5x}".format(species, iteration)))
        return data
    def launch_jobs(
            self,
            opt = None,
            particle_initial_condition = None):
        if not os.path.exists(os.path.join(self.work_dir, self.simname + '.h5')):
            # take care of fields' initial condition
            if not os.path.exists(self.get_checkpoint_0_fname()):
                f = h5py.File(self.get_checkpoint_0_fname(), 'w')
                if len(opt.src_simname) > 0:
                    source_cp = 0
                    src_file = 'not_a_file'
                    while True:
                        src_file = os.path.join(
                            os.path.realpath(opt.src_work_dir),
                            opt.src_simname + '_checkpoint_{0}.h5'.format(source_cp))
                        f0 = h5py.File(src_file, 'r')
                        if '{0}'.format(opt.src_iteration) in f0['vorticity/complex'].keys():
                            f0.close()
                            break
                        source_cp += 1
                    f['vorticity/complex/{0}'.format(0)] = h5py.ExternalLink(
                            src_file,
                            'vorticity/complex/{0}'.format(opt.src_iteration))
                else:
                    data = self.generate_vector_field(
                           write_to_file = False,
                           spectra_slope = 2.0,
                           amplitude = 0.05)
                    f['vorticity/complex/{0}'.format(0)] = data
                f.close()
            # take care of particles' initial condition
            if opt.pclouds > 1:
                np.random.seed(opt.particle_rand_seed)
                if opt.pcloud_type == 'random-cube':
                    particle_initial_condition = (
                        np.random.random((opt.pclouds, 1, 3))*2*np.pi +
                        np.random.random((1, self.parameters['nparticles'], 3))*opt.particle_cloud_size)
                elif opt.pcloud_type == 'regular-cube':
                    onedarray = np.linspace(
                            -opt.particle_cloud_size/2,
                            opt.particle_cloud_size/2,
                            self.parameters['nparticles'])
                    particle_initial_condition = np.zeros(
                            (opt.pclouds,
                             self.parameters['nparticles'],
                             self.parameters['nparticles'],
                             self.parameters['nparticles'], 3),
                            dtype = np.float64)
                    particle_initial_condition[:] = \
                        np.random.random((opt.pclouds, 1, 1, 1, 3))*2*np.pi
                    particle_initial_condition[..., 0] += onedarray[None, None, None, :]
                    particle_initial_condition[..., 1] += onedarray[None, None, :, None]
                    particle_initial_condition[..., 2] += onedarray[None, :, None, None]
            self.write_par(
                    particle_ic = particle_initial_condition)
            if self.parameters['nparticles'] > 0:
                data = self.generate_tracer_state(
                        species = 0,
                        rseed = opt.particle_rand_seed,
                        data = particle_initial_condition)
                for s in range(1, self.particle_species):
                    self.generate_tracer_state(species = s, data = data)
        self.run(
                nb_processes = opt.nb_processes,
                nb_threads_per_process = opt.nb_threads_per_process,
                njobs = opt.njobs,
                hours = opt.minutes // 60,
                minutes = opt.minutes % 60,
                no_submit = opt.no_submit)
        return None

if __name__ == '__main__':
    pass

