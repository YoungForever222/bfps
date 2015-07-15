/***********************************************************************
*
*  Copyright 2015 Max Planck Institute for Dynamics and SelfOrganization
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
*     http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
*
* Contact: Cristian.Lalescu@ds.mpg.de
*
************************************************************************/



#ifndef SPLINE_N2

#define SPLINE_N2

void beta_n2_m0(int deriv, double x, double *poly_val);
void beta_n2_m1(int deriv, double x, double *poly_val);
void beta_n2_m2(int deriv, double x, double *poly_val);
void beta_n2_m3(int deriv, double x, double *poly_val);
void beta_n2_m4(int deriv, double x, double *poly_val);

#endif//SPLINE_N2

