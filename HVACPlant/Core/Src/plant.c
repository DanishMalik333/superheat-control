#include "plant.h"

void Plant_Init(Plant_t *plant, double num, double den, double num_d, double y0)
{
  plant->num = num;
  plant->den = den;
  plant->num_d = num_d;
  plant->y_prev = y0;
  plant->u_prev = 0.0;
  plant->d_prev = 0.0;
}

/* Discrete transfer function num / (z - den), ported from the Simulink plant
 * block (0.03572 / (z - 0.998214)), plus a disturbance input d through
 * num_d / (z - den). Difference equation:
 *   y[n] = den * y[n-1] + num * u[n-1] + num_d * d[n-1]
 * Call once per control cycle with the latest controller output u and the
 * ambient deviation d; returns the next simulated process value. ts is
 * implicit in num/den (both were discretized in Simulink at a fixed Ts) —
 * calling this at a different rate than that Ts invalidates the dynamics. */
double Plant_Update(Plant_t *plant, double u, double d)
{
  double y = plant->den * plant->y_prev + plant->num * plant->u_prev + plant->num_d * plant->d_prev;

  plant->y_prev = y;
  plant->u_prev = u;
  plant->d_prev = d;

  return y;
}
