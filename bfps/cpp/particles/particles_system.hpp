#ifndef PARTICLES_SYSTEM_HPP
#define PARTICLES_SYSTEM_HPP

#include <array>

#include "abstract_particles_system.hpp"
#include "particles_output_hdf5.hpp"
#include "particles_output_mpiio.hpp"
#include "particles_field_computer.hpp"
#include "field_accessor.hpp"
#include "abstract_particles_input.hpp"
#include "particles_adams_bashforth.hpp"
#include "scope_timer.hpp"

template <class real_number, class field_rnumber, class interpolator_class, int interp_neighbours>
class particles_system : public abstract_particles_system<real_number> {
    MPI_Comm mpi_com;

    const std::pair<int,int> current_partition_interval;
    const int partition_interval_size;

    field_accessor<field_rnumber> field;

    interpolator_class interpolator;

    particles_field_computer<real_number, interpolator_class, field_accessor<field_rnumber>, interp_neighbours, particles_adams_bashforth<real_number, 3,3>> computer;

    std::unique_ptr<int[]> current_my_nb_particles_per_partition;
    std::unique_ptr<int[]> current_offset_particles_for_partition;

    const std::array<real_number,3> spatial_box_width;
    const std::array<real_number,3> spatial_partition_width;
    const real_number my_spatial_low_limit;
    const real_number my_spatial_up_limit;

    std::unique_ptr<real_number[]> my_particles_positions;
    std::unique_ptr<int[]> my_particles_positions_indexes;
    int my_nb_particles;
    std::vector<std::unique_ptr<real_number[]>> my_particles_rhs;

    int step_idx;

public:
    particles_system(const std::array<size_t,3>& field_grid_dim, const std::array<real_number,3>& in_spatial_box_width,
                     const std::array<real_number,3>& in_spatial_partition_width,
                     const real_number in_my_spatial_low_limit, const real_number in_my_spatial_up_limit,
                     const field_rnumber* in_field_data, const std::array<size_t,3>& in_local_field_dims,
                     const std::array<size_t,3>& in_local_field_offset,
                     const std::array<size_t,3>& in_field_memory_dims,
                     MPI_Comm in_mpi_com)
        : mpi_com(in_mpi_com),
          current_partition_interval({in_local_field_offset[IDX_Z], in_local_field_offset[IDX_Z] + in_local_field_dims[IDX_Z]}),
          partition_interval_size(current_partition_interval.second - current_partition_interval.first),
          field(in_field_data, in_local_field_dims, in_local_field_offset, in_field_memory_dims),
          interpolator(),
          computer(in_mpi_com, field_grid_dim, current_partition_interval,
                   interpolator, field, in_spatial_box_width, in_spatial_partition_width,
                   in_my_spatial_low_limit, in_my_spatial_up_limit),
          spatial_box_width(in_spatial_box_width), spatial_partition_width(in_spatial_partition_width),
          my_spatial_low_limit(in_my_spatial_low_limit), my_spatial_up_limit(in_my_spatial_up_limit),
          my_nb_particles(0), step_idx(1){

        current_my_nb_particles_per_partition.reset(new int[partition_interval_size]);
        current_offset_particles_for_partition.reset(new int[partition_interval_size+1]);
    }

    ~particles_system(){
    }

    void init(abstract_particles_input<real_number>& particles_input){
        TIMEZONE("particles_system::init");

        my_particles_positions = particles_input.getMyParticles();
        my_particles_positions_indexes = particles_input.getMyParticlesIndexes();
        my_particles_rhs = particles_input.getMyRhs();
        my_nb_particles = particles_input.getLocalNbParticles();

        for(int idx_part = 0 ; idx_part < my_nb_particles ; ++idx_part){ // TODO remove me
            assert(my_particles_positions[idx_part*3+IDX_Z] >= my_spatial_low_limit);
            assert(my_particles_positions[idx_part*3+IDX_Z] < my_spatial_up_limit);
        }

        particles_utils::partition_extra_z<3>(&my_particles_positions[0], my_nb_particles, partition_interval_size,
                                              current_my_nb_particles_per_partition.get(), current_offset_particles_for_partition.get(),
        [&](const int idxPartition){
            const real_number limitPartition = (idxPartition+1)*spatial_partition_width[IDX_Z] + my_spatial_low_limit;
            return limitPartition;
        },
        [&](const int idx1, const int idx2){
            std::swap(my_particles_positions_indexes[idx1], my_particles_positions_indexes[idx2]);
            for(int idx_rhs = 0 ; idx_rhs < int(my_particles_rhs.size()) ; ++idx_rhs){
                for(int idx_val = 0 ; idx_val < 3 ; ++idx_val){
                    std::swap(my_particles_rhs[idx_rhs][idx1*3 + idx_val],
                              my_particles_rhs[idx_rhs][idx2*3 + idx_val]);
                }
            }
        });

        {// TODO remove
            for(int idxPartition = 0 ; idxPartition < partition_interval_size ; ++idxPartition){
                assert(current_my_nb_particles_per_partition[idxPartition] ==
                       current_offset_particles_for_partition[idxPartition+1] - current_offset_particles_for_partition[idxPartition]);
                const real_number limitPartition = (idxPartition+1)*spatial_partition_width[IDX_Z] + my_spatial_low_limit;
                for(int idx = 0 ; idx < current_offset_particles_for_partition[idxPartition+1] ; ++idx){
                    assert(my_particles_positions[idx*3+IDX_Z] < limitPartition);
                }
                for(int idx = current_offset_particles_for_partition[idxPartition+1] ; idx < my_nb_particles ; ++idx){
                    assert(my_particles_positions[idx*3+IDX_Z] >= limitPartition);
                }
            }
        }
    }


    void compute() final {
        TIMEZONE("particles_system::compute");
        computer.compute_distr(current_my_nb_particles_per_partition.get(),
                               my_particles_positions.get(),
                               my_particles_rhs.front().get(),
                               interp_neighbours);
    }

    void move(const real_number dt) final {
        TIMEZONE("particles_system::move");
        computer.move_particles(my_particles_positions.get(), my_nb_particles,
                                my_particles_rhs.data(), std::min(step_idx,int(my_particles_rhs.size())),
                                dt);
    }

    void redistribute() final {
        TIMEZONE("particles_system::redistribute");
        computer.redistribute(current_my_nb_particles_per_partition.get(),
                              &my_nb_particles,
                              &my_particles_positions,
                              my_particles_rhs.data(), my_particles_rhs.size(),
                              &my_particles_positions_indexes,
                              my_spatial_low_limit,
                              my_spatial_up_limit,
                              spatial_partition_width[IDX_Z]);
    }

    void inc_step_idx() final {
        step_idx += 1;
    }

    void shift_rhs_vectors() final {
        if(my_particles_rhs.size()){
            std::unique_ptr<real_number[]> next_current(std::move(my_particles_rhs.back()));
            for(int idx_rhs = my_particles_rhs.size()-1 ; idx_rhs > 0 ; --idx_rhs){
                my_particles_rhs[idx_rhs] = std::move(my_particles_rhs[idx_rhs-1]);
            }
            my_particles_rhs[0] = std::move(next_current);
            particles_utils::memzero(my_particles_rhs[0], 3*my_nb_particles);
        }
    }

    void completeLoop(const real_number dt) final {
        TIMEZONE("particles_system::completeLoop");
        compute();
        move(dt);
        redistribute();
        inc_step_idx();
        shift_rhs_vectors();
    }

    const real_number* getParticlesPositions() const final {
        return my_particles_positions.get();
    }

    const std::unique_ptr<real_number[]>* getParticlesRhs() const final {
        return my_particles_rhs.data();
    }

    const int* getParticlesIndexes() const final {
        return my_particles_positions_indexes.get();
    }

    int getLocalNbParticles() const final {
        return my_nb_particles;
    }

    int getNbRhs() const final {
        return int(my_particles_rhs.size());
    }

    void checkNan() const { // TODO remove
        for(int idx_part = 0 ; idx_part < my_nb_particles ; ++idx_part){ // TODO remove me
            assert(std::isnan(my_particles_positions[idx_part*3+IDX_X]) == false);
            assert(std::isnan(my_particles_positions[idx_part*3+IDX_Y]) == false);
            assert(std::isnan(my_particles_positions[idx_part*3+IDX_Z]) == false);

            for(int idx_rhs = 0 ; idx_rhs < my_particles_rhs.size() ; ++idx_rhs){
                assert(std::isnan(my_particles_rhs[idx_rhs][idx_part*3+IDX_X]) == false);
                assert(std::isnan(my_particles_rhs[idx_rhs][idx_part*3+IDX_Y]) == false);
                assert(std::isnan(my_particles_rhs[idx_rhs][idx_part*3+IDX_Z]) == false);
            }
        }
    }
};


#endif
