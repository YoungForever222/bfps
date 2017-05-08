#ifndef ABSTRACT_PARTICLES_SYSTEM_HPP
#define ABSTRACT_PARTICLES_SYSTEM_HPP

#include <memory>

template <class partsize_t, class real_number>
class abstract_particles_system {
public:
    virtual void compute() = 0;

    virtual void move(const real_number dt) = 0;

    virtual void redistribute() = 0;

    virtual void inc_step_idx() = 0;

    virtual void shift_rhs_vectors() = 0;

    virtual void completeLoop(const real_number dt) = 0;

    virtual const real_number* getParticlesPositions() const = 0;

    virtual const std::unique_ptr<real_number[]>* getParticlesRhs() const = 0;

    virtual const partsize_t* getParticlesIndexes() const = 0;

    virtual partsize_t getLocalNbParticles() const = 0;

    virtual int getNbRhs() const = 0;
};

#endif