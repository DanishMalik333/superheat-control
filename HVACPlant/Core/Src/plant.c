#include "plant.h"

void Plant_Init(Plant_t *plant, double num, double den, double y0)
{
  plant->num = num;
  plant->den = den;
  plant->y_prev = y0;
  plant->u_prev = 0.0;
}

/* Discrete transfer function num / (z - den), ported from the Simulink plant
 * block (0.03572 / (z - 0.998214)). Difference equation:
 *   y[n] = den * y[n-1] + num * u[n-1]
 * Call once per control cycle with the latest controller output u; returns
 * the next simulated process value. ts is implicit in num/den (both were
 * discretized in Simulink at a fixed Ts) — calling this at a different rate
 * than that Ts invalidates the dynamics. */
double Plant_Update(Plant_t *plant, double u)
{
  double y = plant->den * plant->y_prev + plant->num * plant->u_prev;

  plant->y_prev = y;
  plant->u_prev = u;

  return y;
}
