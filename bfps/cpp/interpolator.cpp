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



#include "interpolator.hpp"

template <class rnumber, int interp_neighbours>
interpolator<rnumber, interp_neighbours>::interpolator(
        fluid_solver_base<rnumber> *fs,
        base_polynomial_values BETA_POLYS)
{
    int tdims[4];
    this->unbuffered_descriptor = fs->rd;
    this->buffer_size = (interp_neighbours+1)*this->unbuffered_descriptor->slice_size;
    this->compute_beta = BETA_POLYS;
    tdims[0] = (interp_neighbours+1)*2*this->unbuffered_descriptor->nprocs + this->unbuffered_descriptor->sizes[0];
    tdims[1] = this->unbuffered_descriptor->sizes[1];
    tdims[2] = this->unbuffered_descriptor->sizes[2];
    tdims[3] = this->unbuffered_descriptor->sizes[3];
    this->descriptor = new field_descriptor<rnumber>(
            4, tdims,
            this->unbuffered_descriptor->mpi_dtype,
            this->unbuffered_descriptor->comm);
    this->f0 = new rnumber[this->descriptor->local_size];
    this->f1 = new rnumber[this->descriptor->local_size];
    this->temp = this->f1 + this->buffer_size;
}

template <class rnumber, int interp_neighbours>
interpolator<rnumber, interp_neighbours>::~interpolator()
{
    delete[] this->f0;
    delete[] this->f1;
    delete this->descriptor;
}

template <class rnumber, int interp_neighbours>
int interpolator<rnumber, interp_neighbours>::read_rFFTW(void *void_src)
{
    /* first, roll fields */
    rnumber *tmp = this->f0;
    this->f0 = this->f1;
    this->f1 = tmp;
    this->temp = this->f0 + this->buffer_size;
    /* now do regular things */
    rnumber *src = (rnumber*)void_src;
    rnumber *dst = this->f1;
    /* do big copy of middle stuff */
    clip_zero_padding<rnumber>(this->unbuffered_descriptor, src, 3);
    std::copy(src,
              src + this->unbuffered_descriptor->local_size,
              dst + this->buffer_size);
    MPI_Datatype MPI_RNUM = (sizeof(rnumber) == 4) ? MPI_FLOAT : MPI_DOUBLE;
    int rsrc;
    /* get upper slices */
    for (int rdst = 0; rdst < this->unbuffered_descriptor->nprocs; rdst++)
    {
        rsrc = this->unbuffered_descriptor->rank[(this->unbuffered_descriptor->all_start0[rdst] +
                                           this->unbuffered_descriptor->all_size0[rdst]) %
                                           this->unbuffered_descriptor->sizes[0]];
        if (this->unbuffered_descriptor->myrank == rsrc)
            MPI_Send(
                    src,
                    this->buffer_size,
                    MPI_RNUM,
                    rdst,
                    2*(rsrc*this->unbuffered_descriptor->nprocs + rdst),
                    this->descriptor->comm);
        if (this->unbuffered_descriptor->myrank == rdst)
            MPI_Recv(
                    dst + this->buffer_size + this->unbuffered_descriptor->local_size,
                    this->buffer_size,
                    MPI_RNUM,
                    rsrc,
                    2*(rsrc*this->unbuffered_descriptor->nprocs + rdst),
                    this->descriptor->comm,
                    MPI_STATUS_IGNORE);
    }
    /* get lower slices */
    for (int rdst = 0; rdst < this->unbuffered_descriptor->nprocs; rdst++)
    {
        rsrc = this->unbuffered_descriptor->rank[MOD(this->unbuffered_descriptor->all_start0[rdst] - 1,
                                              this->unbuffered_descriptor->sizes[0])];
        if (this->unbuffered_descriptor->myrank == rsrc)
            MPI_Send(
                    src + this->unbuffered_descriptor->local_size - this->buffer_size,
                    this->buffer_size,
                    MPI_RNUM,
                    rdst,
                    2*(rsrc*this->unbuffered_descriptor->nprocs + rdst)+1,
                    this->unbuffered_descriptor->comm);
        if (this->unbuffered_descriptor->myrank == rdst)
            MPI_Recv(
                    dst,
                    this->buffer_size,
                    MPI_RNUM,
                    rsrc,
                    2*(rsrc*this->unbuffered_descriptor->nprocs + rdst)+1,
                    this->unbuffered_descriptor->comm,
                    MPI_STATUS_IGNORE);
    }
    return EXIT_SUCCESS;
}

template <class rnumber, int interp_neighbours>
void interpolator<rnumber, interp_neighbours>::operator()(
        double t,
        int *xg,
        double *xx,
        double *dest,
        int *deriv)
{
    double bx[interp_neighbours*2+2], by[interp_neighbours*2+2], bz[interp_neighbours*2+2];
    if (deriv == NULL)
    {
        this->compute_beta(0, xx[0], bx);
        this->compute_beta(0, xx[1], by);
        this->compute_beta(0, xx[2], bz);
    }
    else
    {
        this->compute_beta(deriv[0], xx[0], bx);
        this->compute_beta(deriv[1], xx[1], by);
        this->compute_beta(deriv[2], xx[2], bz);
    }
    std::fill_n(dest, 3, 0);
    rnumber *ff0 = this->f0 + this->buffer_size;
    rnumber *ff1 = this->f1 + this->buffer_size;
    for (int iz = -interp_neighbours; iz <= interp_neighbours+1; iz++)
    for (int iy = -interp_neighbours; iy <= interp_neighbours+1; iy++)
    for (int ix = -interp_neighbours; ix <= interp_neighbours+1; ix++)
        for (int c=0; c<3; c++)
        {
            ptrdiff_t tindex = ((ptrdiff_t(    xg[2]+iz                             ) *this->descriptor->sizes[1] +
                                 ptrdiff_t(MOD(xg[1]+iy, this->descriptor->sizes[1])))*this->descriptor->sizes[2] +
                                 ptrdiff_t(MOD(xg[0]+ix, this->descriptor->sizes[2])))*3+c;
            dest[c] += (ff0[tindex]*(1-t) + t*ff1[tindex])*(bz[iz+interp_neighbours]*by[iy+interp_neighbours]*bx[ix+interp_neighbours]);
        }
}

template class interpolator<float, 1>;
template class interpolator<float, 2>;
template class interpolator<float, 3>;
template class interpolator<float, 4>;
template class interpolator<float, 5>;
template class interpolator<float, 6>;
template class interpolator<double, 1>;
template class interpolator<double, 2>;
template class interpolator<double, 3>;
template class interpolator<double, 4>;
template class interpolator<double, 5>;
template class interpolator<double, 6>;
