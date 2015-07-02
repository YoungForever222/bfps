########################################################################
#
#  Copyright 2015 Max Planck Institute for Dynamics and SelfOrganization
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Contact: Cristian.Lalescu@ds.mpg.de
#
########################################################################



from base import base
import subprocess


class code(base):
    def __init__(self):
        super(code, self).__init__()
        self.includes = """
                //begincpp
                #include "base.hpp"
                #include "fluid_solver.hpp"
                #include <iostream>
                #include <fftw3-mpi.h>
                //endcpp
                """
        self.variables = 'int myrank, nprocs;\n'
        self.variables += 'int iter0;\n'
        self.variables += 'char simname[256];\n'
        self.definitions = ''
        self.main_start ="""
                //begincpp
                int main(int argc, char *argv[])
                {
                    MPI_Init(&argc, &argv);
                    MPI_Comm_rank(MPI_COMM_WORLD, &myrank);
                    MPI_Comm_size(MPI_COMM_WORLD, &nprocs);
                    if (argc != 3)
                    {
                        std::cerr << "Wrong number of command line arguments. Stopping." << std::endl;
                        MPI_Finalize();
                        return EXIT_SUCCESS;
                    }
                    else
                    {
                        strcpy(simname, argv[1]);
                        iter0 = atoi(argv[2]);
                        std::cerr << "myrank = " << myrank << ", simulation name is " << simname << std::endl;
                    }
                    read_parameters();
                //endcpp
                """
        self.main_end = """
                //begincpp
                    // clean up
                    fftwf_mpi_cleanup();
                    fftw_mpi_cleanup();
                    MPI_Finalize();
                    return EXIT_SUCCESS;
                }
                //endcpp
                """
        return None
    def write_src(self):
        with open('src/' + self.name + '.cpp', 'w') as outfile:
            outfile.write(self.includes)
            outfile.write(self.variables)
            outfile.write(self.definitions)
            outfile.write(self.main_start)
            outfile.write(self.main)
            outfile.write(self.main_end)
        return None
    def run(self,
            ncpu = 2,
            simname = 'test',
            iter0 = 0):
        # compile code and run
        if subprocess.call(['make', self.name + '.elf']) == 0:
            subprocess.call(['time',
                             'mpirun',
                             '-np',
                             '{0}'.format(ncpu),
                             './' + self.name + '.elf',
                             simname,
                             '{0}'.format(iter0)])
        return None

