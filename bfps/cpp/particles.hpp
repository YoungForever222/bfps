/**********************************************************************
*                                                                     *
*  Copyright 2015 Max Planck Institute                                *
*                 for Dynamics and Self-Organization                  *
*                                                                     *
*  This file is part of bfps.                                         *
*                                                                     *
*  bfps is free software: you can redistribute it and/or modify       *
*  it under the terms of the GNU General Public License as published  *
*  by the Free Software Foundation, either version 3 of the License,  *
*  or (at your option) any later version.                             *
*                                                                     *
*  bfps is distributed in the hope that it will be useful,            *
*  but WITHOUT ANY WARRANTY; without even the implied warranty of     *
*  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the      *
*  GNU General Public License for more details.                       *
*                                                                     *
*  You should have received a copy of the GNU General Public License  *
*  along with bfps.  If not, see <http://www.gnu.org/licenses/>       *
*                                                                     *
* Contact: Cristian.Lalescu@ds.mpg.de                                 *
*                                                                     *
**********************************************************************/



#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <hdf5.h>
#include "base.hpp"
#include "particles_base.hpp"
#include "fluid_solver_base.hpp"
#include "interpolator_base.hpp"

#ifndef PARTICLES

#define PARTICLES

template <int particle_type, class rnumber, int interp_neighbours>
class particles
{
    public:
        int myrank, nprocs;
        MPI_Comm comm;
        rnumber *data;

        /* state will generally hold all the information about the particles.
         * in the beginning, we will only need to solve 3D ODEs, but I figured
         * a general ncomponents is better, since we may change our minds.
         * */
        double *state;
        double *rhs[6];
        int nparticles;
        int ncomponents;
        int array_size;
        int integration_steps;
        int traj_skip;
        interpolator_base<rnumber, interp_neighbours> *vel;

        /* simulation parameters */
        char name[256];
        int iteration;
        double dt;

        /* methods */

        /* constructor and destructor.
         * allocate and deallocate:
         *  this->state
         *  this->rhs
         * */
        particles(
                const char *NAME,
                interpolator_base<rnumber, interp_neighbours> *FIELD,
                const int NPARTICLES,
                const int TRAJ_SKIP,
                const int INTEGRATION_STEPS = 2);
        ~particles();

        void get_rhs(
                double *__restrict__ x,
                double *__restrict__ rhs);

        /* input/output */
        void read(const hid_t data_file_id);
        void write(const hid_t data_file_id, const char *dset_name, const double *data);
        void write(const hid_t data_file_id, const bool write_rhs = true);

        /* solvers */
        void step();
        void roll_rhs();
        void AdamsBashforth(const int nsteps);
};

#endif//PARTICLES

